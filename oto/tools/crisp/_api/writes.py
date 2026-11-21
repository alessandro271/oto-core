"""The writes of `CrispClient`: an internal note, a conversation's state, contact details
and segments, a contact's profile, custom data and segments, and a text message sent to a
conversation's contact. Nothing deletes.

A mixin composed into `CrispClient`, which provides the transport (`_send`).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .checks import choice, segment, text

CONVERSATION_STATES = ("pending", "unresolved", "resolved")
MAX_SEGMENTS, MAX_SEGMENT_LENGTH = 100, 100


def _required_text(value: Any, name: str) -> str:
    given = text(value, name)
    if given is None:
        raise ValueError(f"`{name}` is required.")
    return given


def _given(**fields: Any) -> Dict[str, Any]:
    """The fields given, checked as non-empty texts; an absent one is not sent."""
    return {k: text(v, k) for k, v in fields.items() if v is not None}


def _segments(value: Any) -> list:
    if not isinstance(value, list):
        raise ValueError(f"`segments` must be a list of texts; got {value!r}.")
    if len(value) > MAX_SEGMENTS:
        raise ValueError(f"`segments`: at most {MAX_SEGMENTS}; got {len(value)}.")
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > MAX_SEGMENT_LENGTH:
            raise ValueError(f"`segments`: each one is a non-empty text of at most "
                             f"{MAX_SEGMENT_LENGTH} characters; got {item!r}.")
    if len(set(value)) != len(value):
        raise ValueError(f"`segments` holds the same segment twice: {value!r}.")
    return list(value)


def _custom_data(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"`data` must be a non-empty object; got {value!r}.")
    for key, item in value.items():
        if not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"`data`: the value of {key!r} must be a text, a number or a "
                             f"boolean; got {item!r}.")
    return dict(value)


class WritesMixin:

    def _message(self, session_id: str, kind: str, content: str) -> Any:
        return self._send("POST", f"/conversation/{segment(session_id, 'session_id')}/message", {
            "type": kind, "from": "operator", "origin": "chat",
            "content": _required_text(content, "content")})

    # --- writing: conversations ---------------------------------------------

    def add_conversation_note(self, session_id: str, content: str) -> Any:
        """POST /conversation/{session_id}/message — an internal note (type `note`):
        the team sees it, the contact does not."""
        return self._message(session_id, "note", content)

    def change_conversation_state(self, session_id: str, state: str) -> Any:
        """PATCH /conversation/{session_id}/state — pending, unresolved or resolved."""
        if state is None:
            raise ValueError("`state` is required: " + ", ".join(CONVERSATION_STATES) + ".")
        return self._send("PATCH", f"/conversation/{segment(session_id, 'session_id')}/state",
                          {"state": choice(state, "state", CONVERSATION_STATES)})

    def update_conversation_meta(self, session_id: str, *, nickname: Optional[str] = None,
                                 email: Optional[str] = None, phone: Optional[str] = None,
                                 address: Optional[str] = None) -> Any:
        """PATCH /conversation/{session_id}/meta — the contact details the
        conversation carries; only the fields given are sent."""
        body = _given(nickname=nickname, email=email, phone=phone, address=address)
        if not body:
            raise ValueError("Give at least one of `nickname`, `email`, `phone`, `address`.")
        return self._send("PATCH", f"/conversation/{segment(session_id, 'session_id')}/meta", body)

    def set_conversation_segments(self, session_id: str, segments: list) -> Any:
        """PATCH /conversation/{session_id}/meta — the WHOLE list of segments."""
        return self._send("PATCH", f"/conversation/{segment(session_id, 'session_id')}/meta",
                          {"segments": _segments(segments)})

    def send_message(self, session_id: str, content: str) -> Any:
        """POST /conversation/{session_id}/message — a text (type `text`) that
        REACHES the contact; never retried."""
        return self._message(session_id, "text", content)

    # --- writing: contacts ---------------------------------------------------

    def update_person(self, people_id: str, *, email: Optional[str] = None,
                      nickname: Optional[str] = None, phone: Optional[str] = None,
                      address: Optional[str] = None) -> Any:
        """PATCH /people/profile/{people_id} — email, and `person` {nickname, phone,
        address}; only the fields given are sent, Crisp keeps the others."""
        body: Dict[str, Any] = _given(email=email)
        person = _given(nickname=nickname, phone=phone, address=address)
        if person:
            body["person"] = person
        if not body:
            raise ValueError("Give at least one of `email`, `nickname`, `phone`, `address`.")
        return self._send("PATCH", f"/people/profile/{segment(people_id, 'people_id')}", body)

    def update_person_data(self, people_id: str, data: Dict[str, Any]) -> Any:
        """PATCH /people/data/{people_id} — custom data, merged with the keys already set."""
        return self._send("PATCH", f"/people/data/{segment(people_id, 'people_id')}",
                          {"data": _custom_data(data)})

    def set_person_segments(self, people_id: str, segments: list) -> Any:
        """PATCH /people/profile/{people_id} — the WHOLE list of segments."""
        return self._send("PATCH", f"/people/profile/{segment(people_id, 'people_id')}",
                          {"segments": _segments(segments)})
