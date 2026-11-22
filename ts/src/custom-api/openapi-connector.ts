// Le bloc `connector` que propose un document OpenAPI : copie de `oto/connectors/custom_api/openapi_connector.py`. Nom,
// libellé, adresse, authentification et table d'erreurs standard, chaque valeur dite déduite, chaque valeur qu'il ne sait
// pas proposer nommée comme un problème.
//
// - `base_url` : le premier serveur, absolu et en https (Swagger 2.0 : `https` parmi `schemes`, `host` et `basePath`) ;
//   un serveur à variables n'est pas proposé (`openapi_server_variables` : une définition n'a pas de réglages) ;
// - `auth` : le schéma que le document exige d'abord (`security`), sinon le premier qu'il déclare (`http bearer`,
//   `apiKey`, `http basic`, flux `clientCredentials`, flux `authorizationCode`) ; `openIdConnect` n'est pas suivi
//   (`openapi_openid_connect`), une clé en cookie n'est pas envoyée (`openapi_cookie_parameter`).

import { internalHost } from "./address"
import { standardErrors } from "./errors"
import { cut, identifier } from "./naming"
import { AUTH_NOT_SUPPORTED, BASE_URL_INTERNAL, BASE_URL_NOT_HTTPS, SCHEMA_INVALID, problem, type Problem } from "./problems"
import { PREFIX } from "./profile"
import { isObject, repr } from "./rules"

type Json = any

export const SERVER_VARIABLES = "openapi_server_variables"
export const OPENID_CONNECT = "openapi_openid_connect"
export const COOKIE_PARAMETER = "openapi_cookie_parameter"
const TOKEN = [{ name: "token", label: "API key", secret: true }]
const BASIC = [
  { name: "username", label: "Username", secret: false },
  { name: "password", label: "Password", secret: true },
]
const CLIENT = [
  { name: "client_id", label: "Client ID", secret: false },
  { name: "client_secret", label: "Client secret", secret: true },
]

export type Deduced = { path: string; value: Json; why: string }

/** `url` sans sa barre finale quand c'est une adresse https absolue vers un hôte public ; un problème sinon. */
function https(url: Json, at: string, problems: Problem<string>[]): string | null {
  if (typeof url !== "string" || !url) return null
  if (url.includes("{")) {
    problems.push(problem(SERVER_VARIABLES, at, `${repr(url)} has variables, which a definition has not: write the address yourself`))
    return null
  }
  let parsed: URL | null = null
  try {
    parsed = new URL(url)
  } catch {
    parsed = null
  }
  if (parsed === null || parsed.protocol !== "https:") {
    problems.push(problem(BASE_URL_NOT_HTTPS, at, `${repr(url)} is not an absolute https address: write it yourself`))
    return null
  }
  if (!parsed.hostname || internalHost(parsed.hostname)) {
    problems.push(problem(BASE_URL_INTERNAL, at, `${repr(url)} does not name a public host`))
    return null
  }
  return url.replace(/\/+$/, "")
}

function server(document: Json, problems: Problem<string>[]): string | null {
  if ("swagger" in document) {
    const schemes = document.schemes || ["https"]
    if (!document.host || !schemes.includes("https")) {
      problems.push(problem(BASE_URL_NOT_HTTPS, "connector.base_url", "the document names no https host: write the address yourself"))
      return null
    }
    return https(`https://${document.host}${document.basePath || ""}`, "connector.base_url", problems)
  }
  const servers = document.servers
  const first = Array.isArray(servers) && servers.length && isObject(servers[0]) ? servers[0] : {}
  if (!first.url) {
    problems.push(problem(BASE_URL_NOT_HTTPS, "connector.base_url", "the document names no server: write the address yourself"))
    return null
  }
  return https(first.url, "connector.base_url", problems)
}

function schemes(document: Json): { [name: string]: Json } {
  if ("swagger" in document) return document.securityDefinitions || {}
  return (document.components || {}).securitySchemes || {}
}

function chosen(document: Json): [string, Json] | null {
  const declared = Object.entries(schemes(document)).filter(([, s]) => isObject(s))
  const byName = new Map(declared)
  for (const requirement of document.security || [])
    for (const name of isObject(requirement) ? Object.keys(requirement) : []) if (byName.has(name)) return [name, byName.get(name)]
  return declared[0] ?? null
}

function oauth2(scheme: Json, swagger: boolean, problems: Problem<string>[]): [Json | null, Json[]] {
  let flowName: string | undefined
  let flow: Json
  if (swagger) {
    const flows: { [k: string]: string } = { application: "clientCredentials", accessCode: "authorizationCode" }
    flowName = flows[scheme.flow]
    flow = flowName ? scheme : {}
  } else {
    const all = scheme.flows || {}
    flowName = ["clientCredentials", "authorizationCode"].find((f) => f in all)
    flow = (flowName && all[flowName]) || {}
  }
  const scopes = Object.keys(flow.scopes || {})
  if (flowName === "clientCredentials") {
    const auth: Json = {
      kind: "oauth2_client_credentials",
      token_url: https(flow.tokenUrl, "connector.auth.token_url", problems),
      token_request: "form",
      client_auth: "body",
      client_id: "client_id",
      client_secret: "client_secret",
    }
    if (scopes.length) auth.scope = scopes.join(" ")
    return [auth, CLIENT]
  }
  if (flowName === "authorizationCode") {
    const auth: Json = {
      kind: "oauth2_user",
      authorize_url: https(flow.authorizationUrl, "connector.auth.authorize_url", problems),
      token_url: https(flow.tokenUrl, "connector.auth.token_url", problems),
      client_auth: "body",
      refresh: "refresh_token",
      rotates: false,
    }
    if (scopes.length) auth.scopes = scopes
    problems.push(
      problem(SCHEMA_INVALID, "connector.auth.identity", "who consented is read after the consent: choose the function or address that names them"),
    )
    return [auth, []]
  }
  problems.push(problem(AUTH_NOT_SUPPORTED, "connector.auth", "the document's OAuth flows are neither clientCredentials nor authorizationCode"))
  return [null, []]
}

function authOf(document: Json, problems: Problem<string>[], deduced: Deduced[]): [Json, Json[]] {
  const found = chosen(document)
  if (found === null) {
    deduced.push({ path: "connector.auth", value: "none", why: "the document declares no security scheme" })
    return [{ kind: "none" }, []]
  }
  const [name, scheme] = found
  const kind = scheme.type
  const httpScheme = String(scheme.scheme ?? "").toLowerCase()
  let auth: Json | null = null
  let credential: Json[] = []
  if (kind === "http" && httpScheme === "bearer") [auth, credential] = [{ kind: "bearer", token: "token" }, TOKEN]
  else if ((kind === "http" && httpScheme === "basic") || kind === "basic")
    [auth, credential] = [{ kind: "basic", username: "username", password: "password" }, BASIC]
  else if (kind === "apiKey" && (scheme.in === "header" || scheme.in === "query"))
    [auth, credential] = [{ kind: "api_key", in: scheme.in, name: scheme.name, key: "token" }, TOKEN]
  else if (kind === "apiKey") problems.push(problem(COOKIE_PARAMETER, "connector.auth", `the scheme ${repr(name)} sends its key in a cookie`))
  else if (kind === "oauth2") [auth, credential] = oauth2(scheme, "swagger" in document, problems)
  else if (kind === "openIdConnect")
    problems.push(
      problem(
        OPENID_CONNECT,
        "connector.auth",
        `the scheme ${repr(name)} is OpenID Connect discovery, which is not followed: describe its OAuth flow yourself`,
      ),
    )
  else problems.push(problem(AUTH_NOT_SUPPORTED, "connector.auth", `the scheme ${repr(name)} (${kind}) is not supported`))
  if (auth === null) return [{ kind: "none" }, []]
  auth = Object.fromEntries(Object.entries(auth).filter(([, v]) => v !== null && v !== undefined))
  deduced.push({ path: "connector.auth", value: auth.kind, why: `from the security scheme ${repr(name)}` })
  return [auth, credential]
}

/** `[connector, deduced, problems]` : le bloc que propose le document, jamais enregistré tel quel. */
export function propose(document: Json): [Json, Deduced[], Problem<string>[]] {
  const problems: Problem<string>[] = []
  const deduced: Deduced[] = []
  const info = isObject(document.info) ? document.info : {}
  const label = cut(String(info.title || "Custom API").trim(), 80)
  const name = PREFIX + identifier(label, "api")
  const connector: Json = { name, label, namespace: name, version: "1.0.0", api_version: String(info.version || "unspecified") }
  deduced.push({ path: "connector.name", value: name, why: `the reserved prefix and the title ${repr(label)}` })
  const baseUrl = server(document, problems)
  if (baseUrl) {
    connector.base_url = baseUrl
    deduced.push({ path: "connector.base_url", value: baseUrl, why: "the document's server" })
  }
  const [auth, credential] = authOf(document, problems, deduced)
  connector.auth = auth
  if (credential.length) connector.credential = credential
  connector.modes = auth.kind === "oauth2_user" ? ["byo_user"] : ["byo_user", "byo_org"]
  connector.errors = standardErrors(label, auth.kind)
  deduced.push({ path: "connector.errors", value: connector.errors.map((e: Json) => e.code), why: "the standard error table" })
  return [connector, deduced, problems]
}
