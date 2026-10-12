"""Modjo calls: list and detail, what Modjo drew from a call, its tags, the
import of a call, call reviews. Contract details: `../client.py`."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

CALL_EXPANDS = ("contacts", "deal", "account", "users", "libraries", "transcript",
                "tags", "topics", "summaries", "notes", "next-steps",
                "crm-filling-answers", "ai-scoring")
RETENTION_STATUSES = ("available", "deleted")
DIRECTIONS = ("inbound", "outbound")
PARTICIPANT_TYPES = ("user", "contact")
REVIEW_ORDERS = ("asc", "desc")

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_CALL_ID = re.compile(rf"^([0-9]+|{_UUID})$")


class CallsMixin:
    """Calls, their sub-resources and reviews."""

    # --- checks ---------------------------------------------------------------

    @staticmethod
    def _call_segment(call_id: Any) -> str:
        """A call id placed in the path: digits or a UUID, nothing else — never
        a way to reach another endpoint."""
        value = str(call_id) if isinstance(call_id, int) and not isinstance(call_id, bool) else call_id
        if not isinstance(value, str) or not _CALL_ID.match(value):
            raise ValueError(f"`call_id` must be a numeric call id or a call UUID; got {call_id!r}.")
        return value

    @classmethod
    def _expand(cls, expand: Optional[Sequence[str]]) -> Optional[str]:
        if expand is None:
            return None
        if isinstance(expand, str) or not expand:
            raise ValueError("`expand` must be a non-empty list.")
        for value in expand:
            cls._choice("expand", value, CALL_EXPANDS)
        return ",".join(dict.fromkeys(expand))

    # --- calls ----------------------------------------------------------------

    def list_calls(self, *, ids: Optional[Sequence[int]] = None,
                   title: Optional[str] = None,
                   min_duration: Optional[float] = None,
                   date_from: Optional[str] = None, date_to: Optional[str] = None,
                   created_from: Optional[str] = None,
                   created_to: Optional[str] = None,
                   user_id: Optional[int] = None, deal_id: Optional[int] = None,
                   account_id: Optional[int] = None,
                   recording_retention_status: Optional[str] = None,
                   expand: Optional[Sequence[str]] = None,
                   page: Optional[int] = None, size: Optional[int] = None) -> Any:
        """Calls of the workspace, one page. `date_from`/`date_to` bound the
        call date (`from`/`to` upstream), `created_*` the creation date."""
        if ids is not None:
            if isinstance(ids, (str, bytes)) or not ids or len(ids) > 100:
                raise ValueError("`ids` must be a list of 1 to 100 call ids.")
            ids = ",".join(str(self._positive_int("ids", i)) for i in ids)
        if min_duration is not None and (isinstance(min_duration, bool)
                                         or not isinstance(min_duration, (int, float))
                                         or min_duration < 0):
            raise ValueError("`min_duration` must be a number of seconds, 0 or more.")
        for name, value in (("user_id", user_id), ("deal_id", deal_id),
                            ("account_id", account_id)):
            if value is not None:
                self._positive_int(name, value)
        self._choice("recording_retention_status", recording_retention_status,
                     RETENTION_STATUSES)
        return self._request("GET", "/calls", params={
            "ids": ids, "title": title, "min_duration": min_duration,
            "from": date_from, "to": date_to, "created_from": created_from,
            "created_to": created_to, "user_id": user_id, "deal_id": deal_id,
            "account_id": account_id,
            "recording_retention_status": recording_retention_status,
            "expand": self._expand(expand), **self._page(page, size)})

    def get_call(self, call_id: Any, *, expand: Optional[Sequence[str]] = None) -> Any:
        """One call, by numeric id or UUID."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}",
                             params={"expand": self._expand(expand)})

    def get_call_transcript(self, call_id: Any) -> Any:
        """Timed transcript blocks with their speaker; empty while processing."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}/transcript")

    def list_call_summaries(self, call_id: Any) -> Any:
        """AI summaries, one per summary template; the text is `answer`."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}/summaries")

    def list_call_notes(self, call_id: Any) -> Any:
        """Published notes (user or AI); drafts are not returned."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}/notes")

    def list_call_next_steps(self, call_id: Any) -> Any:
        """Next steps drawn by the AI; empty while processing."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}/next-steps")

    def get_call_recording(self, call_id: Any) -> Any:
        """Signed download URL of the recording, valid one hour (`expiresAt`).
        410 when the retention policy deleted it."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}/recording")

    def list_call_crm_filling_answers(self, call_id: Any, *,
                                      page: Optional[int] = None,
                                      size: Optional[int] = None) -> Any:
        """CRM field values filled by the AI and pushed to the CRM."""
        return self._request(
            "GET", f"/calls/{self._call_segment(call_id)}/crm-filling-answers",
            params=self._page(page, size))

    def list_call_tags(self, call_id: Any) -> Any:
        """Tags set on the call."""
        return self._request("GET", f"/calls/{self._call_segment(call_id)}/tags")

    def add_call_tag(self, call_id: Any, tag_id: int) -> Any:
        """Set an existing tag on the call. Idempotent, hence retried."""
        return self._request("POST", f"/calls/{self._call_segment(call_id)}/tags",
                             json={"tagId": self._positive_int("tag_id", tag_id)},
                             retry=True)

    def remove_call_tag(self, call_id: Any, tag_id: int) -> Any:
        """Remove a tag from the call (the tag itself is kept)."""
        tag = self._positive_int("tag_id", tag_id)
        return self._request("DELETE", f"/calls/{self._call_segment(call_id)}/tags/{tag}",
                             retry=True)

    def upload_call(self, media_url: str, date: str,
                    participants: List[Dict[str, Any]], *,
                    name: Optional[str] = None, direction: Optional[str] = None,
                    duration: Optional[float] = None,
                    tags: Optional[List[str]] = None,
                    account: Optional[Dict[str, str]] = None,
                    deal: Optional[Dict[str, str]] = None,
                    crm_activity_id: Optional[str] = None) -> Any:
        """Import a call Modjo downloads from `media_url` (public https).

        Answers `{callId, status: "processing"}`. Never retried, and the API
        cannot delete a call: Modjo also logs it in the connected CRM.
        """
        if not isinstance(media_url, str) or not media_url.startswith("https://"):
            raise ValueError("`media_url` must be a public https URL.")
        if not isinstance(participants, list) or not participants:
            raise ValueError("`participants` must list at least one participant.")
        for participant in participants:
            if not isinstance(participant, dict) or not participant.get("email"):
                raise ValueError("each participant needs an `email` and a `type`.")
            self._choice("participants[].type", participant.get("type"), PARTICIPANT_TYPES)
            if participant.get("type") is None:
                raise ValueError("each participant needs a `type`: 'user' or 'contact'.")
        if not any(p.get("type") == "user" for p in participants):
            raise ValueError("at least one participant must be of type 'user', a licensed Modjo user.")
        self._choice("direction", direction, DIRECTIONS)
        for label, link in (("account", account), ("deal", deal)):
            if link is not None and not (isinstance(link, dict)
                                         and link.get("crm") and link.get("crmId")):
                raise ValueError(f"`{label}` must be {{'crm': ..., 'crmId': ...}}.")
        return self._request("POST", "/calls", json={
            "downloadMediaUrl": media_url, "date": date, "participants": participants,
            "name": name, "direction": direction, "duration": duration, "tags": tags,
            "account": account, "deal": deal, "crmActivityId": crm_activity_id,
        }, retry=False)

    # --- reviews --------------------------------------------------------------

    def list_call_reviews(self, *, start_date_time: Optional[str] = None,
                          end_date_time: Optional[str] = None,
                          order: Optional[str] = None,
                          page: Optional[int] = None,
                          size: Optional[int] = None) -> Any:
        """Call reviews with their answers; newest first unless `order="asc"`."""
        self._choice("order", order, REVIEW_ORDERS)
        return self._request("GET", "/call-reviews", params={
            "startDateTime": start_date_time, "endDateTime": end_date_time,
            "order": order, **self._page(page, size)})
