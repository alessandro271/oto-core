"""Modjo Public API client (v2, workspace API key).

The methods implement the functions described in
`connectors/modjo/connector.yaml`, under the same names and with the same
arguments: calls and what Modjo drew from them (transcript, AI summaries,
notes, next steps, recording, CRM filling answers, tags), call reviews, the
CRM objects Modjo mirrors (accounts, contacts, deals and a deal's summary),
the workspace (tags, topics, users, teams) and CRM filling templates; writes
on the tags of a call and the import of a call. Plus `ask_agent`, a question
to Modjo's AI about a call, a deal or an account, which stays out of the
description: it may run five minutes, and the description has one timeout
for every function. Users, teams and webhooks are read or left alone, never
administered.

Responses are returned as Modjo sends them, `{}` on a 204. A list answers
`{data, pagination: {page, size, total}}`: another page exists while
`page * size < total` — `has_next_page(response)` says it.

What the caller needs to know, and cannot guess:

- ⚠️ **The key belongs to the WORKSPACE** (created by an admin or a manager),
  not to a person: `list_calls` without `user_id` returns everyone's calls.
- **Rate: 100 requests per minute for the whole workspace**, all keys
  together, in a fixed window; failed requests count. A 429 is waited out
  (`X-RateLimit-Reset`, bounded) and retried, for reads and idempotent writes
  only.
- **A call is processed asynchronously** (5 to 30 minutes after an import):
  `status` goes `processing` → `completed` | `failed`; transcript, summaries
  and next steps stay empty until then.
- **`upload_call` is never retried and cannot be undone**: the API has no
  call deletion, and Modjo logs the call in the connected CRM.
- **Recording URLs are signed for one hour**: never store them.

Usage:
    client = ModjoClient(api_key="...")
    jane = client.list_users(email="jane@example.com")["data"][0]
    calls = client.list_calls(user_id=jane["id"], expand=["contacts", "deal"])

Requires: requests
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, Optional

import requests

from ..common import raise_for_upstream
from ..common.credentials import require
from ..http.client import refuse_redirect
from ._api import CallsMixin, WorkspaceMixin

# (connect, read) — never an unbounded wait.
HTTP_TIMEOUT = (10, 60)
#: `ask_agent` runs Modjo's AI synchronously: 30 s to 2 min, up to 5 min.
ASK_TIMEOUT = (10, 300)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
#: Longest wait honoured from `X-RateLimit-Reset` (the window is 60 s).
MAX_RESET_WAIT = 60.0


def has_next_page(response: Dict[str, Any]) -> bool:
    """Whether a Modjo list has a page after this one (`page * size < total`)."""
    pagination = response.get("pagination") or {}
    page, size, total = (pagination.get(k) for k in ("page", "size", "total"))
    if not all(isinstance(v, int) for v in (page, size, total)):
        return False
    return page * size < total


class ModjoClient(CallsMixin, WorkspaceMixin):
    """Client for the Modjo Public API v2 (`Authorization: Bearer <key>`).

    An upstream refusal raises `UpstreamHTTPError` (`service="modjo"`), its
    body Modjo's `{code, message}`; an invalid argument raises `ValueError`
    before any request.
    """

    BASE_URL = "https://api.modjo.ai/v2"

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Modjo Public API key, passed by the consumer. Created by
                an admin or a manager in Modjo → Settings → Integrations →
                Public API.
        """
        self.api_key = require(api_key, "MODJO_API_KEY")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    # --- transport ------------------------------------------------------------

    def _request(self, method: str, path: str, *,
                 params: Optional[Dict[str, Any]] = None,
                 json: Any = None, retry: Optional[bool] = None,
                 timeout=HTTP_TIMEOUT) -> Any:
        """One call. `retry` defaults to reads only: a replayed import would
        create a second call."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if json is not None:
            json = {k: v for k, v in json.items() if v is not None}
        retryable = method.upper() == "GET" if retry is None else retry
        last = None
        for attempt in range(MAX_ATTEMPTS):
            last = self.session.request(
                method, f"{self.BASE_URL}{path}", params=params or None,
                json=json, timeout=timeout, allow_redirects=False)
            refuse_redirect(last)
            if (last.status_code not in RETRY_STATUSES
                    or not retryable or attempt == MAX_ATTEMPTS - 1):
                break
            time.sleep(self._wait(last, attempt))
        raise_for_upstream(last, service="modjo")
        return last.json() if last.content else {}

    @staticmethod
    def _wait(response, attempt: int) -> float:
        """After a 429, the window's end (`X-RateLimit-Reset`, in seconds,
        bounded); otherwise an exponential backoff."""
        reset = (response.headers or {}).get("X-RateLimit-Reset")
        if response.status_code == 429 and reset is not None:
            try:
                return min(max(float(reset), 1.0), MAX_RESET_WAIT)
            except ValueError:
                pass
        return float(2 ** attempt)

    # --- argument checks -------------------------------------------------------

    @staticmethod
    def _positive_int(name: str, value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"`{name}` must be a positive integer; got {value!r}.")
        return value

    @staticmethod
    def _choice(name: str, value: Optional[str], allowed: Iterable[str]) -> None:
        allowed = tuple(allowed)
        if value is not None and value not in allowed:
            raise ValueError(f"invalid `{name}`: {value!r}. Accepted values: "
                             + ", ".join(repr(a) for a in allowed))

    @classmethod
    def _page(cls, page: Optional[int], size: Optional[int]) -> Dict[str, Any]:
        if page is not None:
            cls._positive_int("page", page)
        if size is not None:
            cls._positive_int("size", size)
            if size > 100:
                raise ValueError(f"`size` is at most 100 (Modjo cap); got {size}.")
        return {"page": page, "size": size}

    # --- probe ----------------------------------------------------------------

    def probe(self) -> Any:
        """Connection check: the workspace's tags, one item — no call data,
        and a clean 401 if the key is wrong."""
        return self.list_tags(size=1)

    # --- Modjo AI ---------------------------------------------------------------

    def ask_agent(self, scope_type: str, scope_id: Any, *,
                  instructions: Optional[str] = None,
                  schema: Dict[str, Any],
                  schema_name: str = "answer",
                  schema_description: Optional[str] = None,
                  strict: Optional[bool] = None) -> Any:
        """Ask Modjo's AI about one call, deal or account; the answer follows
        `schema` (`{id, scope, output}`, every field of `output` may be null).

        Synchronous, up to five minutes, never retried: each attempt runs the
        AI again. 403 when the feature is not enabled for the workspace, 409
        when the call is not processed yet.

        Args:
            scope_type: "call", "deal" or "account".
            scope_id: its id (a call also takes its UUID).
            instructions: the question, 1 to 4,000 characters.
            schema: JSON Schema of the answer — object, array, string, number,
                integer, boolean and scalar enums only.
            schema_name: name of the answer format.
            schema_description: what the answer is, 1,000 characters at most.
            strict: whether Modjo enforces the schema strictly.
        """
        self._choice("scope_type", scope_type, ("call", "deal", "account"))
        if scope_type == "call":
            scope_id = self._call_segment(scope_id)
            scope_id = int(scope_id) if scope_id.isdigit() else scope_id
        else:
            scope_id = self._positive_int("scope_id", scope_id)
        if instructions is not None and not 1 <= len(instructions) <= 4000:
            raise ValueError("`instructions` must be 1 to 4,000 characters.")
        if not isinstance(schema, dict) or not schema:
            raise ValueError("`schema` must be a non-empty JSON Schema object.")
        json_schema = {"name": schema_name, "schema": schema}
        if schema_description is not None:
            json_schema["description"] = schema_description
        if strict is not None:
            json_schema["strict"] = strict
        return self._request("POST", "/agents/ask", json={
            "scope": {"type": scope_type, "id": scope_id},
            "instructions": instructions,
            "responseFormat": {"type": "json_schema", "json_schema": json_schema},
        }, retry=False, timeout=ASK_TIMEOUT)
