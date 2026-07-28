"""Persistent, Nostr-scoped chat API.

The package keeps the public application surface intentionally small:
``backend.main`` only needs the router and the storage shutdown hook. Request
models, prompt construction, event translation, and runtime state live in
their own modules so changes in one concern do not grow the route module.
"""

from backend.chat.routes import router
from backend.chat.runtime import close_session_storage

__all__ = ["close_session_storage", "router"]
