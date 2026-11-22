// Les noms du format, tirés de noms qu'une API ou une personne a écrits : la copie TypeScript de
// `oto/connectors/custom_api/naming.py` (snake_case, la classe qu'un verbe implique).

export const MAX_NAME = 63

/** Les `n` premiers caractères d'un texte, comptés comme Python les compte (points de code). */
export function cut(text: string, n: number): string {
  const chars = Array.from(text)
  return chars.length <= n ? text : chars.slice(0, n).join("")
}

/** Le nombre de caractères d'un texte, compté comme Python le compte. */
export const length = (text: string): number => Array.from(text).length

/** `organizationId` → `organization_id`, `page[size]` → `page_size`, `HTTPServer` → `http_server` ; `""` quand il ne
 * reste ni lettre ni chiffre. */
export function snakeCase(text: string): string {
  const s = (text || "")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase()
  return cut(s, MAX_NAME).replace(/_+$/, "")
}

/** Un nom du format (`^[a-z][a-z0-9_]*$`) tiré de `text` : son snake_case, `prefix` devant quand il est vide ou ne
 * commence pas par une lettre. */
export function identifier(text: string, prefix: string): string {
  let s = snakeCase(text)
  if (!s || !/^[a-z]/.test(s)) s = `${prefix}_${s}`.replace(/_+$/, "")
  return cut(s, MAX_NAME).replace(/_+$/, "")
}

/** Ce qu'un verbe implique, dit comme déduit : GET lit, POST, PUT et PATCH écrivent, DELETE détruit et se confirme. */
export function classOf(method: string): { class: "read" | "write" | "sensitive"; effect?: "destroy" } {
  const verb = method.toUpperCase()
  if (verb === "GET") return { class: "read" }
  if (verb === "DELETE") return { class: "sensitive", effect: "destroy" }
  return { class: "write" }
}

export function confirmation(method: string, path: string): { summary: string } {
  return { summary: `${method.toUpperCase()} ${path}: irreversible.` }
}
