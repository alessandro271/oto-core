"""Crisp — customer messaging: reads the workspace, inboxes, conversations and their
messages, contacts and the knowledge base; writes notes, states, contact details,
segments and custom data, and sends a text message to a conversation's contact."""

from .client import CrispClient

__all__ = ["CrispClient"]
