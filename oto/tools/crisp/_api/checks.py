"""Argument checks shared by the reads (`client.py`) and the writes (`writes.py`)."""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote


def segment(value: Any, name: str) -> str:
    """One path segment: a non-empty string, never `.` or `..`, percent-encoded
    (`@` kept, so that an email stays readable)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` must be a non-empty string; got {value!r}.")
    if value in (".", ".."):
        raise ValueError(f"`{name}` cannot be {value!r}.")
    return quote(value, safe="@")


def choice(value: Optional[str], name: str, allowed: tuple) -> Optional[str]:
    if value is None:
        return None
    if value not in allowed:
        raise ValueError(f"`{name}` invalid: {value!r}. Accepted values: "
                         + ", ".join(repr(a) for a in allowed))
    return value


def text(value: Any, name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` must be a non-empty string; got {value!r}.")
    return value
