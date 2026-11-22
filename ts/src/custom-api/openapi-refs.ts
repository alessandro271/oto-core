// Les références et les schémas d'un document OpenAPI, lus comme des données : copie de
// `oto/connectors/custom_api/openapi_refs.py`. Une `$ref` locale se suit sur 8 niveaux au plus ; toute autre est refusée
// par son nom, jamais remplacée par un schéma vide en silence.
//
// `inline(document, node)` rend le nœud, chaque `$ref` remplacée par sa cible, écrit en JSON Schema 2020-12 :
// `nullable: true` (OpenAPI 3.0) devient un type `null`, et les mots d'OpenAPI qui ne sont pas du JSON Schema (`example`,
// `discriminator`, `xml`, `externalDocs`, `x-…`) partent. `RefRefused` nomme ce qui l'arrête : `openapi_ref_external`,
// `openapi_ref_too_deep` (un cycle compris), `openapi_ref_missing`.

import { isObject, repr } from "./rules"

type Json = any

export const MAX_REF_DEPTH = 8
export const REF_EXTERNAL = "openapi_ref_external"
export const REF_TOO_DEEP = "openapi_ref_too_deep"
export const REF_MISSING = "openapi_ref_missing"
/** Les mots d'un schéma OpenAPI que JSON Schema 2020-12 n'a pas. */
const NOT_JSON_SCHEMA = ["nullable", "example", "discriminator", "xml", "externalDocs"]

export class RefRefused extends Error {
  readonly code: string
  readonly reason: string
  constructor(code: string, ref: unknown, reason: string) {
    super(`${repr(ref)}: ${reason}`)
    this.code = code
    this.reason = `$ref ${repr(ref)}: ${reason}`
  }
}

/** Le nœud où mène une chaîne de références, et la profondeur atteinte. */
export function resolve(document: Json, node: Json, depth = 0): [Json, number] {
  while (isObject(node) && "$ref" in node) {
    const ref = node.$ref
    if (typeof ref !== "string" || !ref.startsWith("#/"))
      throw new RefRefused(REF_EXTERNAL, ref, "only references inside the document are followed")
    if (depth >= MAX_REF_DEPTH)
      throw new RefRefused(REF_TOO_DEEP, ref, `more than ${MAX_REF_DEPTH} references followed one inside the other`)
    let target: Json = document
    for (const raw of ref.slice(2).split("/")) {
      const part = raw.replaceAll("~1", "/").replaceAll("~0", "~")
      if (isObject(target) && part in target) target = target[part]
      else if (Array.isArray(target) && /^\d+$/.test(part) && Number(part) < target.length) target = target[Number(part)]
      else throw new RefRefused(REF_MISSING, ref, "the document has nothing there")
    }
    node = target
    depth += 1
  }
  return [node, depth]
}

function withNull(schema: { [key: string]: Json }): Json {
  const kind = schema.type
  if (typeof kind === "string") schema.type = [kind, "null"]
  else if (Array.isArray(kind) && !kind.includes("null")) schema.type = [...kind, "null"]
  return schema
}

/** `node`, ses références remplacées, en JSON Schema 2020-12. */
export function inline(document: Json, node: Json, depth = 0): Json {
  const [found, reached] = resolve(document, node, depth)
  if (Array.isArray(found)) return found.map((item) => inline(document, item, reached))
  if (!isObject(found)) return found
  const out: { [key: string]: Json } = {}
  for (const [key, value] of Object.entries(found)) {
    if (NOT_JSON_SCHEMA.includes(key) || key.startsWith("x-")) continue
    if (key === "examples" && !Array.isArray(value)) continue
    if (["enum", "const", "default", "examples"].includes(key)) out[key] = value
    else if (key === "properties" && isObject(value))
      out[key] = Object.fromEntries(Object.entries(value).map(([name, sub]) => [name, inline(document, sub, reached)]))
    else out[key] = inline(document, value, reached)
  }
  return found.nullable === true ? withNull(out) : out
}

/** L'exemple que porte un paramètre, un type de média ou un schéma (`example`, ou le premier de `examples`), en
 * `[trouvé, valeur]`. */
export function exampleOf(document: Json, holder: Json): [boolean, Json] {
  const [found] = resolve(document, holder)
  if (!isObject(found)) return [false, null]
  if ("example" in found) return [true, found.example]
  const examples = found.examples
  if (isObject(examples) && Object.keys(examples).length) {
    const [first] = resolve(document, Object.values(examples)[0])
    if (isObject(first) && "value" in first) return [true, first.value]
  }
  if (Array.isArray(examples) && examples.length) return [true, examples[0]]
  if (isObject(found.schema)) return exampleOf(document, found.schema)
  return [false, null]
}
