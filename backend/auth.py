"""Nostr login -- no passwords, no email, no server-side key custody.

Standard NIP-42-style challenge/response: the browser's Nostr extension
(NIP-07, i.e. window.nostr -- Alby, nos2x, etc.) signs a one-time server
issued nonce with the user's own key, proving ownership of that pubkey
without the key or any secret ever touching this server. On success the
pubkey is stored in a signed session cookie (Starlette's SessionMiddleware,
see backend/main.py) and becomes the ADK session user_id for everything
else (see backend/chat/) -- ADK already keys every session operation by
user_id, so a pubkey slots into that dimension with no schema of our own.

Login is optional, not required: get_current_user_id below falls back to
a per-browser anonymous id (a UUID the frontend generates and persists in
localStorage, sent as the X-Anon-Id header) so chat still gets a stable
user_id to scope sessions by without an account. Logging in just swaps
that id for a real pubkey going forward -- the two identities are never
merged.
"""

import secrets
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pynostr.event import Event

router = APIRouter(prefix="/auth", tags=["auth"])

_CHALLENGE_TTL_SECONDS = 300
_AUTH_EVENT_KIND = 22242  # NIP-42 "client authentication"
_ANON_ID_HEADER = "X-Anon-Id"

# In-memory, single-use, short-lived -- a nonce is worthless the moment it's
# consumed or expires, so there's no reason to persist these across a
# restart (unlike the login session itself, which the signed cookie alone
# already survives one).
_pending_challenges: dict[str, float] = {}


class VerifyRequest(BaseModel):
    event: dict


@router.post("/challenge")
def create_challenge() -> dict:
    nonce = secrets.token_hex(16)
    _pending_challenges[nonce] = time.time() + _CHALLENGE_TTL_SECONDS
    return {"nonce": nonce}


def _consume_challenge(nonce: str) -> None:
    expires_at = _pending_challenges.pop(nonce, None)
    if expires_at is None or expires_at < time.time():
        raise HTTPException(status_code=400, detail="challenge expired or unknown -- request a new one")


@router.post("/verify")
def verify(req: VerifyRequest, request: Request) -> dict:
    """Body is the raw signed Nostr event the client got back from
    window.nostr.signEvent() -- verify() below recomputes the event id from
    its actual fields (ignoring whatever id the client sent) and checks the
    BIP340 Schnorr signature against it, so both "is this really signed by
    this pubkey" and "does the signature cover what's claimed" are one call."""
    try:
        event = Event.from_dict(req.event)
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"malformed event: {exc}") from exc

    if event.kind != _AUTH_EVENT_KIND:
        raise HTTPException(status_code=400, detail=f"expected kind {_AUTH_EVENT_KIND}, got {event.kind}")

    challenge = next((t[1] for t in event.tags if len(t) > 1 and t[0] == "challenge"), None)
    if not challenge:
        raise HTTPException(status_code=400, detail="event missing a challenge tag")
    _consume_challenge(challenge)

    if not event.verify():
        raise HTTPException(status_code=401, detail="invalid signature")

    request.session["pubkey"] = event.pubkey
    return {"pubkey": event.pubkey}


@router.get("/me")
def me(request: Request) -> dict:
    pubkey = request.session.get("pubkey")
    if not pubkey:
        raise HTTPException(status_code=401, detail="not logged in")
    return {"pubkey": pubkey}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


def get_current_user_id(request: Request) -> str:
    """FastAPI dependency for chat/comms/irc routes -- resolves whichever
    identity the caller has: a logged-in Nostr pubkey if present, otherwise
    the anonymous per-browser id from the X-Anon-Id header. Either way the
    result becomes the ADK session user_id (see backend/chat/), so history
    stays scoped to whichever identity actually sent the request. Prefixed
    so an anonymous id can never collide with a real 64-hex pubkey."""
    pubkey = request.session.get("pubkey")
    if pubkey:
        return pubkey

    anon_id = request.headers.get(_ANON_ID_HEADER)
    if not anon_id:
        raise HTTPException(status_code=400, detail=f"missing {_ANON_ID_HEADER} header")
    try:
        UUID(anon_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{_ANON_ID_HEADER} must be a UUID") from None
    return f"anon:{anon_id}"
