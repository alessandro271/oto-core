"""Modjo call families, composed into `ModjoClient`.

One module per API domain. Contract details: `../client.py`.
"""

from .calls import CallsMixin
from .workspace import WorkspaceMixin

__all__ = ["CallsMixin", "WorkspaceMixin"]
