"""DataForSEO client — SEO data: keywords, domains, backlinks (dataforseo.com).

REST API v3, HTTP Basic auth (API login + API password from the DataForSEO
dashboard — not the account's sign-in password). Pay-as-you-go: every call
draws on a prepaid USD balance.

Only the synchronous **live** endpoints are wrapped: one POST, one answer. The
queued `task_post`/`task_get` flavour is cheaper per item but needs polling,
which a per-call client cannot carry.

**Request shape.** Every POST endpoint takes an ARRAY of task objects; this
client always sends exactly one task and returns that task's envelope.

**Errors live in the body, not the HTTP status.** DataForSEO answers HTTP 200
with a five-digit `status_code` at two levels — the request and each task
(`20000` = OK). A non-20000 at either level raises `UpstreamHTTPError`, with
the HTTP-like status derived from the five-digit code (`40100` → 401,
`40200`/`40210` → 402, `40400` → 404, `40202`/`429xx` → 429, `5xxxx` → 502,
any other `4xxxx` → 400) and the original code kept in the body.

**Cost.** Each task carries `cost` (USD actually charged). `_live` returns the
task as is, so `task["cost"]` is the billed amount of the call.

Requires: requests
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from ..common.credentials import require
from ..common import UpstreamHTTPError, raise_for_upstream
from ..http.client import refuse_redirect
from ._api import BacklinksMixin, DomainsMixin, KeywordsMixin

_HTTP_TIMEOUT = (10, 90)  # (connect, read) — Labs/backlinks live calls can take ~30 s
_OK = 20000


def _http_status(code: Any) -> int:
    """Five-digit DataForSEO status → the HTTP status it means."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return 502
    if 40100 <= c < 40200:
        return 401
    if 40200 <= c < 40300 and c != 40202:
        return 402
    if c == 40202 or 42900 <= c < 43000:
        return 429
    if 40400 <= c < 40500:
        return 404
    if 40000 <= c < 50000:
        return 400
    return 502


def _check(status_code: Any, status_message: Any) -> None:
    if status_code != _OK:
        raise UpstreamHTTPError(
            _http_status(status_code),
            {"status_code": status_code, "status_message": status_message},
            service="dataforseo")


class DataForSeoClient(KeywordsMixin, DomainsMixin, BacklinksMixin):
    """Client DataForSEO (https://api.dataforseo.com/v3), HTTP Basic auth."""

    BASE_URL = "https://api.dataforseo.com/v3"

    def __init__(self, login: str = None, password: str = None):
        """
        Args:
            login: API login (the account's email).
            password: API password (dashboard → API Access), not the sign-in password.
        """
        self.login = require(login, "DATAFORSEO_LOGIN")
        self.password = require(password, "DATAFORSEO_PASSWORD")
        self.session = requests.Session()
        self.session.auth = (self.login, self.password)

    # --- transport ----------------------------------------------------------

    def _request(self, method: str, path: str, *, json: Any = None) -> Dict[str, Any]:
        resp = self.session.request(method, f"{self.BASE_URL}{path}", json=json,
                                    timeout=_HTTP_TIMEOUT, allow_redirects=False)
        refuse_redirect(resp)
        raise_for_upstream(resp, service="dataforseo")
        body = resp.json() if resp.content else {}
        _check(body.get("status_code"), body.get("status_message"))
        return body

    @staticmethod
    def _compact(body: Dict[str, Any]) -> Dict[str, Any]:
        """Drops keys set to None — the API then applies ITS defaults."""
        return {k: v for k, v in body.items() if v is not None}

    def _task(self, method: str, path: str, task: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = self._request(method, path,
                             json=[self._compact(task)] if task is not None else None)
        tasks = body.get("tasks") or []
        if not tasks:
            raise UpstreamHTTPError(502, {"status_message": "no task in the response"},
                                    service="dataforseo")
        t = tasks[0]
        _check(t.get("status_code"), t.get("status_message"))
        return t

    def _live(self, path: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """POST one task to a live endpoint. Returns the task envelope:
        `{id, status_code, status_message, time, cost, result_count, path, data,
        result: [...]}` — `cost` in USD, `result` as documented per endpoint."""
        return self._task("POST", path, task)

    @staticmethod
    def _location(task: Dict[str, Any], location_code, location_name,
                  language_code, language_name) -> Dict[str, Any]:
        task.update({"location_code": location_code, "location_name": location_name,
                     "language_code": language_code, "language_name": language_name})
        return task

    # --- account ------------------------------------------------------------

    def user_data(self) -> Dict[str, Any]:
        """GET /appendix/user_data — login, balance (`money.balance`, USD), rate
        limits and spend statistics. Free."""
        return self._task("GET", "/appendix/user_data")

    def labs_locations_and_languages(self) -> Dict[str, Any]:
        """GET /dataforseo_labs/locations_and_languages — the locations (with
        `location_code`) and languages the Labs endpoints accept. Free."""
        return self._task("GET", "/dataforseo_labs/locations_and_languages")


__all__ = ["DataForSeoClient"]
