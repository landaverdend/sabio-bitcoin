"""HTTP access to archived communication source details, identified either
by a logged-in Nostr pubkey or an anonymous per-browser id."""

from fastapi import APIRouter, Depends

from agents.comms.db_tools import get_message
from backend.auth import get_current_user_id

router = APIRouter(prefix="/comms", tags=["comms"])


@router.get("/messages/{message_id}")
def message_detail(
    message_id: int,
    _user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return the complete archived post behind a chat source reference."""
    return get_message(f"message:{message_id}")
