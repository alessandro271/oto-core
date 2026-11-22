// L'import d'un document OpenAPI : des candidats pour une définition Custom API, jamais enregistrés tels quels. Copie de
// `oto/connectors/custom_api/openapi.py`, jouée sur les mêmes cas communs (`connectors/_cases/custom_api.yaml`).
//
// `fromOpenApi(document, options)` prend OpenAPI 3.0 ou 3.1, ou Swagger 2.0 (un texte JSON ou YAML, ou l'objet déjà lu),
// 5 Mo et 100 opérations au plus, et rend `{ connector, deduced, problems, candidates, skipped }`, comme le côté Python.
// Le paquet reste sans dépendance : le validateur JSON Schema arrive en paramètre (`compile`, comme pour `validate`), et
// le lecteur YAML aussi (`yaml`) ; un texte qui n'est pas du JSON, sans lecteur YAML, est refusé, jamais deviné. La
// lecture par adresse (`read_url` côté Python) reste à l'hôte, qui garde ses propres adresses.
//
// Le profil hôte (`./host`) lit les mêmes opérations par le même parcours (`walk`, `parts`).

import { FORBIDDEN_HEADERS, MAX_FUNCTIONS, type SchemaCompiler } from "./profile"
import { COOKIE_PARAMETER, propose, type Deduced } from "./openapi-connector"
import { RefRefused, exampleOf, inline, resolve } from "./openapi-refs"
import { classOf, confirmation, cut, identifier, length } from "./naming"
import { ARGUMENT_NAME_COLLISION, EXAMPLE_MISSING, SCHEMA_INVALID, problem, type Problem } from "./problems"
import { isObject, repr } from "./rules"

type Json = any

export const MAX_BYTES = 5 * 1024 * 1024
const METHODS = ["get", "post", "put", "patch", "delete"]
const PATH_ITEM_KEYS = ["parameters", "summary", "description", "servers", "$ref"]
const MAX_DESCRIPTION = 1000
const PLACEHOLDER = /\{([^{}]*)\}/g
export const NOT_A_DOCUMENT = "openapi_not_a_document"
export const TOO_LARGE = "openapi_too_large"
export const METHOD_NOT_SUPPORTED = "openapi_method_not_supported"
export const BODY_NOT_JSON = "openapi_body_not_json"
export const BODY_NOT_OBJECT = "openapi_body_not_object"
export const NAME_COLLISION = "openapi_name_collision"
export const TOO_MANY_OPERATIONS = "openapi_too_many_operations"

/** Ce que l'import reçoit de l'hôte : le validateur JSON Schema, et, pour lire un texte YAML, le lecteur YAML. */
export type ImportOptions = { readonly compile: SchemaCompiler; readonly yaml?: (text: string) => unknown }

/** Un document qui n'en est pas un, ou trop lourd. */
export class OpenAPIRefused extends Error {
  readonly code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

/** Une opération que le format ne sait pas dire, avec son code. */
export class Skip extends Error {
  readonly code: string
  readonly reason: string
  constructor(code: string, reason: string) {
    super(reason)
    this.code = code
    this.reason = reason
  }
}

export type Skipped = { path: string; method: string; code: string; reason: string }

/** Le document comme un objet : un texte JSON ou YAML, ou déjà lu ; `OpenAPIRefused` quand il n'en est pas un. */
export function parse(document: unknown, yaml?: (text: string) => unknown): Json {
  if (typeof document === "string" || document instanceof Uint8Array) {
    const raw = typeof document === "string" ? new TextEncoder().encode(document) : document
    if (raw.length > MAX_BYTES) throw new OpenAPIRefused(TOO_LARGE, `the document weighs more than ${MAX_BYTES / (1024 * 1024)} MB`)
    const text = typeof document === "string" ? document : new TextDecoder().decode(document)
    try {
      document = JSON.parse(text)
    } catch {
      if (yaml === undefined) throw new OpenAPIRefused(NOT_A_DOCUMENT, "not JSON, and no YAML reader was given")
      try {
        document = yaml(text)
      } catch (error) {
        throw new OpenAPIRefused(NOT_A_DOCUMENT, `neither JSON nor YAML: ${(error as Error).message}`)
      }
    }
  }
  if (!isObject(document)) throw new OpenAPIRefused(NOT_A_DOCUMENT, "the document is not an object")
  if (!(String(document.openapi ?? "").startsWith("3") || String(document.swagger ?? "") === "2.0"))
    throw new OpenAPIRefused(NOT_A_DOCUMENT, "neither OpenAPI 3 (openapi: 3.x) nor Swagger 2.0 (swagger: '2.0')")
  return document
}

/** Les paramètres d'une opération, ceux de son chemin compris, ceux de l'opération l'emportant à même place et nom. */
function parameters(document: Json, item: Json, operation: Json): Json[] {
  const found = new Map<string, Json>()
  for (const node of [...(item.parameters || []), ...(operation.parameters || [])]) {
    const [parameter] = resolve(document, node)
    if (isObject(parameter) && parameter.name) found.set(JSON.stringify([parameter.in ?? null, parameter.name]), parameter)
  }
  return [...found.values()]
}

const SWAGGER_SCHEMA_KEYS = ["type", "format", "enum", "items", "minimum", "maximum", "pattern", "minLength", "maxLength", "default"]

function parameterSchema(document: Json, parameter: Json, swagger: boolean): Json {
  let schema: Json = swagger
    ? Object.fromEntries(SWAGGER_SCHEMA_KEYS.filter((k) => k in parameter).map((k) => [k, parameter[k]]))
    : inline(document, parameter.schema || {})
  const description = parameter.description
  if (typeof description === "string" && description.trim()) schema = { ...schema, description: cut(description.trim(), MAX_DESCRIPTION) }
  return schema
}

/** Un corps `allOf` en un seul objet : les propriétés et exigences de ses parties ; fermé quand chacune l'est. */
function merged(parts: Json[]): Json {
  const out: Json = { type: "object", properties: {}, required: [] }
  for (const part of parts) {
    Object.assign(out.properties, part.properties || {})
    out.required.push(...(part.required || []))
  }
  if (parts.length && parts.every((part) => part.additionalProperties === false)) out.additionalProperties = false
  return out
}

/** Le schéma objet JSON du corps et son exemple, `[null, null]` sans corps ; `Skip` sinon. */
function body(document: Json, operation: Json, params: Json[], swagger: boolean): [Json | null, Json] {
  let holder: Json = null
  let schema: Json
  if (swagger) {
    if (params.some((p) => p.in === "formData")) throw new Skip(BODY_NOT_JSON, "the body is a form")
    const declared = params.find((p) => p.in === "body")
    if (declared === undefined) return [null, null]
    schema = declared.schema
    holder = declared.schema
  } else {
    const [requestBody] = resolve(document, operation.requestBody)
    if (!requestBody || (isObject(requestBody) && !Object.keys(requestBody).length)) return [null, null]
    const content = requestBody.content || {}
    const media = Object.keys(content).find((m) => m.split(";")[0]?.trim() === "application/json" || m.endsWith("+json"))
    if (media === undefined) throw new Skip(BODY_NOT_JSON, `the body is ${Object.keys(content).join(", ") || "without content"}, not JSON`)
    holder = content[media]
    schema = (content[media] || {}).schema
  }
  const raw = schema || {}
  let inlined = inline(document, raw)
  if (isObject(inlined) && Array.isArray(inlined.allOf) && inlined.allOf.length) inlined = merged(inlined.allOf)
  if (
    !isObject(inlined) ||
    (inlined.type ?? "object") !== "object" ||
    !isObject(inlined.properties) ||
    "oneOf" in inlined ||
    "anyOf" in inlined
  )
    throw new Skip(BODY_NOT_OBJECT, "the body is not a JSON object with declared properties")
  const [found, example] = holder !== null && holder !== undefined ? exampleOf(document, holder) : [false, null]
  return [inlined, found ? example : propertyExamples(document, raw)]
}

/** L'exemple qu'un objet de corps donne par les exemples de ses propriétés, quand il n'en donne pas. */
function propertyExamples(document: Json, schema: Json): Json {
  const [found] = resolve(document, schema)
  const out: Json = {}
  for (const [name, sub] of Object.entries((found || {}).properties || {})) {
    const [has, value] = exampleOf(document, sub)
    if (has) out[name] = value
  }
  return Object.keys(out).length ? out : null
}

/** Ce que donne une opération avant qu'un profil la nomme (la classe `Parts` côté Python). */
export type Parts = {
  path: string
  method: string
  operation: Json
  properties: { [name: string]: Json }
  required: string[]
  places: { query: { [api: string]: string }; headers: { [api: string]: string }; body: { [api: string]: string } }
  example: { [name: string]: Json }
  deduced: Deduced[]
  /** Chaque nom côté API et son argument. */
  arguments: { [api: string]: string }
  /** Le schéma du corps JSON, `null` sans corps. */
  body: Json | null
  /** Les paramètres de query laissés de côté (`leaveOut`), par nom. */
  leftOut: { [api: string]: Json }
}

/** Les parties d'une opération ; les paramètres de query nommés dans `leaveOut` ne sont pas des arguments et sont rendus
 * à part. `Skip` ou `RefRefused` quand le format ne sait pas dire l'opération. */
export function parts(document: Json, path: string, method: string, item: Json, operation: Json, leaveOut: readonly string[] = []): Parts {
  const swagger = "swagger" in document
  const deduced: Deduced[] = []
  const properties: { [name: string]: Json } = {}
  const required: string[] = []
  const places: Parts["places"] = { query: {}, headers: {}, body: {} }
  const renamed = new Map<string, string>()
  const example: { [name: string]: Json } = {}
  const args: { [api: string]: string } = {}
  const leftOut: { [api: string]: Json } = {}

  const argument = (apiName: string, schema: Json, isRequired: boolean): string => {
    const name = identifier(apiName, "arg")
    if (name in properties) throw new Skip(ARGUMENT_NAME_COLLISION, `two arguments become ${repr(name)}`)
    properties[name] = schema
    args[apiName] = name
    if (isRequired) required.push(name)
    return name
  }

  const params = parameters(document, item, operation)
  for (const parameter of params) {
    const where = parameter.in
    const apiName: string = parameter.name
    if (where === "body" || where === "formData") continue
    if (where === "cookie") {
      if (parameter.required) throw new Skip(COOKIE_PARAMETER, `the cookie ${repr(apiName)} is required`)
      deduced.push({ path: `cookie.${apiName}`, value: null, why: "an optional cookie is left out" })
      continue
    }
    if (where === "header" && FORBIDDEN_HEADERS.includes(String(apiName).toLowerCase())) {
      deduced.push({ path: `header.${apiName}`, value: null, why: "the authentication sends it, from the account" })
      continue
    }
    if (!["path", "query", "header"].includes(where)) throw new Skip(SCHEMA_INVALID, `the parameter ${repr(apiName)} is in ${repr(where)}`)
    if (where === "query" && leaveOut.includes(apiName)) {
      leftOut[apiName] = parameter
      continue
    }
    const name = argument(apiName, parameterSchema(document, parameter, swagger), where === "path" || Boolean(parameter.required))
    if (where === "path") renamed.set(apiName, name)
    else places[where === "header" ? "headers" : "query"][apiName] = name
    const [found, value] = exampleOf(document, parameter)
    if (found) example[name] = value
  }
  const [schema, bodyExample] = body(document, operation, params, swagger)
  if (schema !== null) {
    const bodyRequired = new Set(schema.required || [])
    for (const [apiName, sub] of Object.entries(schema.properties)) {
      places.body[apiName] = argument(apiName, sub, bodyRequired.has(apiName))
      if (isObject(bodyExample) && apiName in bodyExample) example[places.body[apiName] as string] = bodyExample[apiName]
    }
  }
  for (const [, apiName = ""] of path.matchAll(PLACEHOLDER)) {
    if (!renamed.has(apiName)) {
      const name = argument(apiName, { type: "string" }, true)
      renamed.set(apiName, name)
      deduced.push({ path: `input.${name}`, value: { type: "string" }, why: "the path cites it, the document does not declare it" })
    }
  }
  for (const [apiName, name] of renamed) path = path.replaceAll(`{${apiName}}`, `{${name}}`)
  return { path, method, operation, properties, required, places, example, deduced, arguments: args, body: schema, leftOut }
}

function examplesOf(schema: Json, example: Json, deduced: Deduced[], problems: Problem<string>[], compile: SchemaCompiler): Json[] {
  if (Object.keys(example).length && compile(schema)(example).length === 0) {
    deduced.push({ path: "examples", value: example, why: "the document's example, which the input accepts" })
    return [{ title: "From the document", input: example }]
  }
  if (!schema.required) {
    deduced.push({ path: "examples", value: {}, why: "no required argument: the empty call is its example" })
    return [{ title: "Without arguments", input: {} }]
  }
  problems.push(problem(EXAMPLE_MISSING, "examples", "no example the input accepts: write one before saving"))
  return []
}

/** Un candidat de l'import Custom API : sa fonction nommée et classée d'après le document, ses problèmes. */
function candidate(document: Json, path: string, method: string, item: Json, operation: Json, compile: SchemaCompiler): Json {
  const found = parts(document, path, method, item, operation)
  const { properties, required, places, example, deduced } = found
  path = found.path
  const problems: Problem<string>[] = []
  let name: string
  if (typeof operation.operationId === "string" && operation.operationId.trim()) name = identifier(operation.operationId, "op")
  else {
    const segments = path.split("/").filter((part) => part && !part.startsWith("{"))
    name = identifier(`${method}_${segments.join("_") || "root"}`, "op")
    deduced.push({ path: "name", value: name, why: "the operation has no operationId" })
  }
  const texts = [operation.summary, operation.description].filter((t) => typeof t === "string" && t.trim()).map((t: string) => t.trim())
  let description = [...new Set(texts)].join(" — ") || `${method.toUpperCase()} ${path}`
  if (length(description) > MAX_DESCRIPTION) description = cut(description, MAX_DESCRIPTION - 1).trimEnd() + "…"
  const fn: Json = { name, ...classOf(method) }
  deduced.push({ path: "class", value: fn.class, why: `from the verb ${method.toUpperCase()}` })
  if (fn.class === "sensitive") fn.confirm = confirmation(method, path)
  fn.description = description
  fn.input = { type: "object", additionalProperties: false, properties }
  if (required.length) fn.input.required = [...new Set(required)]
  const examples = examplesOf(fn.input, example, deduced, problems, compile)
  if (examples.length) fn.examples = examples
  const call: Json = { method: method.toUpperCase(), path }
  for (const [where, table] of Object.entries(places)) if (Object.keys(table).length) call[where] = table
  fn.call = call
  return { function: fn, deduced, problems }
}

/** `build(path, method, item, operation)` appliqué à chaque opération du document, `MAX_FUNCTIONS` au plus, dans l'ordre :
 * ce qu'il a construit, et les opérations écartées (`method` vaut `*` pour un chemin entier). */
export function walk<T>(document: Json, build: (path: string, method: string, item: Json, operation: Json) => T): [T[], Skipped[]] {
  const built: T[] = []
  const skipped: Skipped[] = []
  for (const [path, node] of Object.entries(document.paths || {})) {
    let item: Json
    try {
      ;[item] = resolve(document, node)
    } catch (refused) {
      if (!(refused instanceof RefRefused)) throw refused
      skipped.push({ path, method: "*", code: refused.code, reason: refused.reason })
      continue
    }
    for (const [method, operation] of Object.entries(isObject(item) ? item : {})) {
      if (PATH_ITEM_KEYS.includes(method) || method.startsWith("x-")) continue
      const entry = { path, method: method.toUpperCase() }
      if (!METHODS.includes(method)) {
        skipped.push({ ...entry, code: METHOD_NOT_SUPPORTED, reason: `${method.toUpperCase()} is not supported` })
        continue
      }
      if (built.length >= MAX_FUNCTIONS) {
        skipped.push({ ...entry, code: TOO_MANY_OPERATIONS, reason: `beyond ${MAX_FUNCTIONS} operations` })
        continue
      }
      try {
        built.push(build(path, method, item, isObject(operation) ? operation : {}))
      } catch (refused) {
        if (!(refused instanceof Skip || refused instanceof RefRefused)) throw refused
        skipped.push({ ...entry, code: refused.code, reason: refused.reason })
      }
    }
  }
  return [built, skipped]
}

/** Des candidats pour une définition Custom API (en-tête du module). */
export function fromOpenApi(document: unknown, options: ImportOptions): Json {
  const doc = parse(document, options.yaml)
  const [connector, connectorDeduced, connectorProblems] = propose(doc)
  const [candidates, skipped] = walk(doc, (path, method, item, operation) => candidate(doc, path, method, item, operation, options.compile))
  const names = new Set<string>()
  for (const c of candidates) {
    const fn = c.function
    if (names.has(fn.name)) {
      const base: string = fn.name
      let n = 2
      while (names.has(`${base.slice(0, 58)}_${n}`)) n += 1
      fn.name = `${base.slice(0, 58)}_${n}`
      c.problems.push(problem(NAME_COLLISION, "name", `${repr(base)} is taken: ${repr(fn.name)} is proposed, to confirm`))
    }
    names.add(fn.name)
  }
  return { connector, deduced: connectorDeduced, problems: connectorProblems, candidates, skipped }
}
