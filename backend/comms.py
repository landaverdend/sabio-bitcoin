"""Authenticated HTTP access to archived communication source details."""

from fastapi import APIRouter, Depends

from agents.comms.db_tools import get_message
from backend.auth import get_current_pubkey

router = APIRouter(prefix="/comms", tags=["comms"])


@router.get("/messages/{message_id}")
def message_detail(
    message_id: int,
    _pubkey: str = Depends(get_current_pubkey),
) -> dict:
    """Return the complete archived post behind a chat source reference."""
    return get_message(f"message:{message_id}")
