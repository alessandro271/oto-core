"""Custom API: an organisation describes a tool the catalogue does not have, and its agents call its actions by name
(docs/conception/custom-api.md).

A definition IS a `connector.yaml` of the format, restricted by a closed profile, kept as JSON by the host. This
package holds what both hosts share, pure, without I/O except `openapi.read_url`:

- `validate(document) -> list[Problem]`: every problem of a definition, each with its `custom_api_*` code (`profile`);
- `from_openapi(document) -> dict`: candidates drawn from an OpenAPI 3 or Swagger 2 document, JSON or YAML, never saved
  as such (`openapi`);
- `from_oto1(definition_oto1) -> (document | None, report)`: the takeover, once, of a definition of oto 1 (`oto1`);
- `standard_errors(label, auth_kind)`: the standard error table, written out in a definition (`errors`);
- `from_host_openapi(document, *, reserved) -> dict`: the host profile, the functions of a host's own API described in
  OpenAPI, strict, every problem named (`host`, docs/conception/profil-hote.md).

The engine of the lib (`oto.connectors.engine.call`) runs a valid definition as it is, `oauth2_user` aside; a host's
definition (`host_delegated`) runs in the host only.
"""

from __future__ import annotations

from .errors import standard_errors
from .host import from_host_openapi
from .openapi import OpenAPIRefused, from_openapi, read_url
from .oto1 import from_oto1
from .problems import CODES, Problem
from .profile import PREFIX, validate

__all__ = [
    "CODES",
    "PREFIX",
    "OpenAPIRefused",
    "Problem",
    "from_host_openapi",
    "from_openapi",
    "from_oto1",
    "read_url",
    "standard_errors",
    "validate",
]
