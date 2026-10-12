"""Modjo workspace: the CRM objects Modjo mirrors (accounts, contacts, deals),
tags, topics, users, teams and CRM filling templates — all read-only.
Contract details: `../client.py`."""
from __future__ import annotations

import re
from typing import Any, Optional

DEAL_STATUSES = ("Open", "Closed won", "Closed lost", "Closed", "Deleted")
TEMPLATE_STATUSES = ("pending", "published")

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class WorkspaceMixin:
    """Mirrored CRM objects, workspace directory, CRM filling templates."""

    @staticmethod
    def _uuid(name: str, value: Any) -> str:
        if not isinstance(value, str) or not _UUID.match(value):
            raise ValueError(f"`{name}` must be a UUID; got {value!r}.")
        return value

    # --- CRM objects ----------------------------------------------------------

    def list_accounts(self, *, name: Optional[str] = None,
                      page: Optional[int] = None, size: Optional[int] = None) -> Any:
        """Accounts mirrored from the connected CRM."""
        return self._request("GET", "/accounts",
                             params={"name": name, **self._page(page, size)})

    def get_account(self, account_id: int) -> Any:
        return self._request("GET", f"/accounts/{self._positive_int('account_id', account_id)}")

    def list_contacts(self, *, name: Optional[str] = None,
                      page: Optional[int] = None, size: Optional[int] = None) -> Any:
        """Contacts (external people) mirrored from the connected CRM."""
        return self._request("GET", "/contacts",
                             params={"name": name, **self._page(page, size)})

    def get_contact(self, contact_id: int) -> Any:
        return self._request("GET", f"/contacts/{self._positive_int('contact_id', contact_id)}")

    def list_deals(self, *, name: Optional[str] = None,
                   account_id: Optional[int] = None, status: Optional[str] = None,
                   page: Optional[int] = None, size: Optional[int] = None) -> Any:
        """Deals mirrored from the connected CRM."""
        if account_id is not None:
            self._positive_int("account_id", account_id)
        self._choice("status", status, DEAL_STATUSES)
        return self._request("GET", "/deals", params={
            "name": name, "account_id": account_id, "status": status,
            **self._page(page, size)})

    def get_deal_summary(self, deal_id: int) -> Any:
        """AI summary of a deal across its calls (404 when there is none)."""
        return self._request("GET", f"/deals/{self._positive_int('deal_id', deal_id)}/summary")

    # --- directory ------------------------------------------------------------

    def list_tags(self, *, page: Optional[int] = None, size: Optional[int] = None) -> Any:
        return self._request("GET", "/tags", params=self._page(page, size))

    def list_topics(self, *, page: Optional[int] = None, size: Optional[int] = None) -> Any:
        return self._request("GET", "/topics", params=self._page(page, size))

    def list_users(self, *, email: Optional[str] = None,
                   page: Optional[int] = None, size: Optional[int] = None) -> Any:
        """Workspace members; `email` finds one (exact match)."""
        return self._request("GET", "/users",
                             params={"email": email, **self._page(page, size)})

    def get_user(self, user_id: int) -> Any:
        return self._request("GET", f"/users/{self._positive_int('user_id', user_id)}")

    def list_teams(self, *, name: Optional[str] = None,
                   page: Optional[int] = None, size: Optional[int] = None) -> Any:
        return self._request("GET", "/teams",
                             params={"name": name, **self._page(page, size)})

    def get_team(self, team_id: int) -> Any:
        return self._request("GET", f"/teams/{self._positive_int('team_id', team_id)}")

    def list_team_members(self, team_id: int, *, page: Optional[int] = None,
                          size: Optional[int] = None) -> Any:
        return self._request("GET", f"/teams/{self._positive_int('team_id', team_id)}/members",
                             params=self._page(page, size))

    # --- CRM filling templates ------------------------------------------------

    def list_crm_filling_templates(self, *, status: Optional[str] = None,
                                   page: Optional[int] = None,
                                   size: Optional[int] = None) -> Any:
        self._choice("status", status, TEMPLATE_STATUSES)
        return self._request("GET", "/crm-filling-templates",
                             params={"status": status, **self._page(page, size)})

    def get_crm_filling_template(self, template_uuid: str) -> Any:
        return self._request(
            "GET", f"/crm-filling-templates/{self._uuid('template_uuid', template_uuid)}")

    def list_crm_filling_template_fields(self, template_uuid: str, *,
                                         page: Optional[int] = None,
                                         size: Optional[int] = None) -> Any:
        """The CRM fields a template fills, with their prompt."""
        return self._request(
            "GET", f"/crm-filling-templates/{self._uuid('template_uuid', template_uuid)}/fields",
            params=self._page(page, size))
