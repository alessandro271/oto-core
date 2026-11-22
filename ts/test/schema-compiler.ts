// Ce que l'hôte passe au module Custom API dans les tests : Ajv comme validateur JSON Schema (2020-12, sans juger
// `format`, le mot `personal` connu), et le lecteur YAML lu comme `yaml.safe_load` côté Python.
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js"
import { parse } from "yaml"
import type { SchemaCompiler } from "../src/custom-api"
import type { JsonSchema } from "../src/types"

// Comme `yaml.safe_load` côté Python : clés de fusion, ancres sans plafond (les descriptions en usent) ; le schéma
// « core » de YAML 1.2, car celui de YAML 1.1 lirait `y` et `n` en booléens, ce que PyYAML ne fait pas.
export const read = (text: string) => parse(text, { schema: "core", merge: true, maxAliasCount: -1 })

const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true })
ajv.addKeyword({ keyword: "personal", schemaType: "boolean" })
const compiled = new WeakMap<object, ValidateFunction>()

export const compile: SchemaCompiler = (schema: JsonSchema) => {
  let check = compiled.get(schema)
  if (check === undefined) {
    check = ajv.compile(schema)
    compiled.set(schema, check)
  }
  const run = check
  return (value) => (run(value) ? [] : [...(run.errors ?? [])])
}

type Change = { path: string; value?: unknown; remove?: boolean }

/** Le document après ses changements : chaque chemin à points, posé (`value`) ou retiré (`remove`). */
export function changed(document: unknown, changes: readonly Change[]): unknown {
  const out = structuredClone(document)
  for (const change of changes) {
    const parts = change.path.split(".")
    const last = parts.pop() as string
    let node: any = out
    for (const part of parts) node = node[Array.isArray(node) ? Number(part) : part]
    const key = Array.isArray(node) ? Number(last) : last
    if (change.remove) {
      if (Array.isArray(node)) node.splice(key as number, 1)
      else delete node[key]
    } else node[key] = structuredClone(change.value)
  }
  return out
}
