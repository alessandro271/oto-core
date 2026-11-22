// La table d'erreurs standard d'une Custom API, copie de `oto/connectors/custom_api/errors.py` : ce que proposent l'import
// OpenAPI et le profil hôte, écrit en clair dans la définition (docs/conception/signal-de-refus.md pour le sens).
//
// Un 401 marque le compte (`credential_rejected`) quand le compte a un credential à refuser. Sans authentification
// (`none`), rien ne marque ; ni sous le jeton de l'hôte (`host_delegated`), qui n'a pas de compte : la personne se
// reconnecte.

type ErrorEntry = {
  status: number | number[]
  code: string
  retryable: boolean
  message: string
  marks_account?: "credential_rejected"
}

/** La table d'un outil nommé `label`, authentifié par `authKind`. */
export function standardErrors(label: string, authKind: string): ErrorEntry[] {
  const unauthorized: ErrorEntry = {
    status: 401,
    code: "unauthorized",
    retryable: false,
    message: `${label} refuses the credential of this account: it must be set again.`,
  }
  if (authKind === "oauth2_user") {
    unauthorized.code = "authorization_expired"
    unauthorized.marks_account = "credential_rejected"
    unauthorized.message = `${label} no longer accepts this authorization: the person must connect again.`
  } else if (authKind === "host_delegated") {
    unauthorized.code = "authorization_expired"
    unauthorized.message = `${label} no longer accepts this person's authorization: they must connect again.`
  } else if (authKind !== "none") unauthorized.marks_account = "credential_rejected"
  else unauthorized.message = `${label} requires an authentication this definition does not declare.`
  return [
    { status: [400, 422], code: "invalid_request", retryable: false, message: `${label} rejected the request: check the arguments.` },
    unauthorized,
    {
      status: 403,
      code: "forbidden",
      retryable: false,
      message: `${label} refused: this account lacks the right for this object or action.`,
    },
    { status: 404, code: "not_found", retryable: false, message: `${label} object not found.` },
    { status: 429, code: "rate_limited", retryable: true, message: `${label} rate limit reached: retry later.` },
    {
      status: [500, 502, 503, 504],
      code: "upstream_unavailable",
      retryable: true,
      message: `${label} is temporarily unavailable: retry later.`,
    },
  ]
}
