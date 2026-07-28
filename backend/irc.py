"""HTTP access to archived IRC event details."""

from fastapi import APIRouter, Depends

from agents.irc.db_tools import get_irc_event
from backend.auth import get_current_user_id

router = APIRouter(prefix="/irc", tags=["irc"])


@router.get("/events/{event_id}")
def event_detail(
    event_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return the complete Gnusha event behind a chat source reference."""
    return get_irc_event(event_id)
