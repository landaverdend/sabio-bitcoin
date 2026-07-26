"""Persistent, Nostr-scoped ADK chat sessions and their SSE API.

ADK owns the physical session/event tables, but this application owns their
lifecycle: db/migrations/0009_adk_sessions.sql records the pinned ADK 1.13
schema so it is visible to migrations, backups, and operators instead of
being an import-time side effect nobody knows about.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, DatabaseSessionService
from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from agents.root.agent import root_agent
from backend.auth import get_current_pubkey

router = APIRouter(prefix="/chat", tags=["chat"])

_APP_NAME = "sabio"
_MAX_SESSIONS_PER_PUBKEY = 20  # oldest (by last_update_time) evicted past this
_TITLE_CHARS = 80
_CONTEXT_ITEM_CHARS = 8000
_DISPLAY_MESSAGE_STATE_KEY = "_sabio_display_message"

# Constructing DatabaseSessionService in pinned ADK 1.13 calls create_all().
# Keep that out of module import so test collection, CLI introspection, and
# unrelated API routes do not require a live database. The first chat request
# initializes one process-wide service/runner pair and reuses its pool.
_session_service: DatabaseSessionService | None = None
_runner: Runner | None = None

# ADK 1.13 has stale-session protection but no same-session in-process lock.
# Serializing complete runs prevents two requests in this worker from
# interleaving events. Database uniqueness remains the cross-worker backstop.
_session_locks: dict[tuple[str, str], asyncio.Lock] = {}
_session_locks_guard = asyncio.Lock()


def _get_session_runtime() -> tuple[DatabaseSessionService, Runner]:
    global _runner, _session_service
    if _session_service is None:
        _session_service = DatabaseSessionService(
            db_url=os.environ["DATABASE_URL"],
            # Neon may retire pooled connections while they are idle.
            pool_pre_ping=True,
        )
    if _runner is None:
        _runner = Runner(app_name=_APP_NAME, agent=root_agent, session_service=_session_service)
    return _session_service, _runner


def close_session_storage() -> None:
    """Dispose pooled DB connections during app shutdown."""
    global _runner, _session_service
    if _session_service is not None:
        _session_service.db_engine.dispose()
    _session_service = None
    _runner = None
    _session_locks.clear()


async def _get_session_lock(pubkey: str, session_id: str) -> asyncio.Lock:
    key = (pubkey, session_id)
    async with _session_locks_guard:
        lock = _session_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[key] = lock
        return lock


class ContextItem(BaseModel):
    """A file or a highlighted excerpt, explicitly attached by the user from
    the code panel -- content is inlined directly into the model's prompt
    rather than left for the repos agent to fetch itself via read_file, so
    the model is guaranteed to see exactly what was attached rather than
    possibly re-fetching the wrong slice (or the whole file, missing why a
    specific range was highlighted)."""

    path: str = Field(min_length=1, max_length=1024)
    start_line: int | None = None
    end_line: int | None = None
    content: str = Field(max_length=250_000)


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(min_length=1, max_length=16_000)
    context: list[ContextItem] = Field(default_factory=list, max_length=8)


def _build_prompt(message: str, context: list[ContextItem]) -> str:
    if not context:
        return message

    blocks = []
    for item in context:
        where = f"{item.path} (lines {item.start_line}-{item.end_line})" if item.start_line else item.path
        blocks.append(f"### {where}\n```\n{item.content[:_CONTEXT_ITEM_CHARS]}\n```")

    return "Attached context:\n\n" + "\n\n".join(blocks) + "\n\n---\n\n" + message


def _sse(payload: dict) -> str:
    # default=str: function-call args occasionally carry non-JSON-primitive
    # values (e.g. from Google AI's schema handling) -- str() is a safe
    # fallback rather than letting json.dumps raise mid-stream.
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _ensure_session(
    service: BaseSessionService,
    pubkey: str,
    session_id: str,
    message: str,
) -> None:
    existing = await service.get_session(
        app_name=_APP_NAME, user_id=pubkey, session_id=session_id,
    )
    if existing is not None:
        return

    title = message.strip()[:_TITLE_CHARS] or "New conversation"
    try:
        await service.create_session(
            app_name=_APP_NAME,
            user_id=pubkey,
            session_id=session_id,
            state={"title": title},
        )
    except IntegrityError:
        # Another worker may have won the get-then-create race. Only suppress
        # the constraint error when the intended session now really exists;
        # unrelated database integrity failures must remain visible.
        existing = await service.get_session(
            app_name=_APP_NAME, user_id=pubkey, session_id=session_id,
        )
        if existing is None:
            raise

    # Prune after creation. That makes the newly requested session usable
    # even when two workers create different sessions at the same time; the
    # cap is eventually restored instead of rejecting either request.
    existing_sessions = await service.list_sessions(app_name=_APP_NAME, user_id=pubkey)
    excess = len(existing_sessions.sessions) - _MAX_SESSIONS_PER_PUBKEY
    if excess > 0:
        oldest_first = sorted(
            (session for session in existing_sessions.sessions if session.id != session_id),
            key=lambda session: session.last_update_time,
        )
        for stale in oldest_first[:excess]:
            await service.delete_session(
                app_name=_APP_NAME, user_id=pubkey, session_id=stale.id,
            )


def _display_message(message: str, context: list[ContextItem]) -> dict:
    """Small user-facing copy attached to the persisted ADK user event.

    The actual event content is the model prompt, which includes full source
    excerpts. This metadata lets history reconstruct the original bubble and
    context chips without showing that generated prompt envelope.
    """
    return {
        "message": message,
        "context": [
            {
                "path": item.path,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in context
        ],
    }


def _legacy_display_text(text: str) -> str:
    """Recover the visible message from sessions created before metadata."""
    separator = "\n\n---\n\n"
    return text.rsplit(separator, 1)[-1] if separator in text else text


def _source_reference(response: dict) -> dict | None:
    """Build the frontend's source-reference event from read_file's result.

    Keeping this derived from the actual tool response, rather than parsing
    paths or line numbers out of model-written Markdown, guarantees that
    every rendered citation points to code the agent really inspected.
    """
    required = ("repo", "path", "ref", "start_line", "end_line", "github_url")
    if not all(key in response for key in required):
        return None
    if not (
        isinstance(response["repo"], str)
        and isinstance(response["path"], str)
        and isinstance(response["ref"], str)
        and isinstance(response["start_line"], int)
        and isinstance(response["end_line"], int)
        and isinstance(response["github_url"], str)
    ):
        return None
    if response["start_line"] < 1 or response["end_line"] < response["start_line"]:
        return None
    return {
        "type": "source",
        "repo": response["repo"],
        "path": response["path"],
        "ref": response["ref"],
        "start_line": response["start_line"],
        "end_line": response["end_line"],
        "github_url": response["github_url"],
    }


def _communication_reference(response: dict) -> dict | None:
    """Build a citable archive reference from get_message's full result."""
    message_id = response.get("id")
    channel = response.get("channel")
    body = response.get("body")
    url = response.get("url")
    if (
        not isinstance(message_id, (int, str))
        or isinstance(message_id, bool)
        or not isinstance(channel, str)
        or not isinstance(body, str)
        or not isinstance(url, str)
        or not url.startswith(("http://", "https://"))
    ):
        return None

    compact_body = " ".join(body.split())
    excerpt = compact_body[:360]
    if len(compact_body) > len(excerpt):
        excerpt += "…"

    return {
        "type": "communication_source",
        "message_id": str(message_id),
        "channel": channel,
        "author": response.get("author") if isinstance(response.get("author"), str) else None,
        "title": response.get("title") if isinstance(response.get("title"), str) else None,
        "posted_at": (
            response.get("posted_at")
            if isinstance(response.get("posted_at"), str)
            else None
        ),
        "excerpt": excerpt,
        "source_url": url,
    }


def _event_payloads(event: Event) -> list[dict]:
    """Turns one ADK event into this app's own {type, ...} shape -- shared by
    the live SSE loop below and by the session-history endpoint, so a past
    conversation replays through the exact same parsing a live one streams
    through, rather than a second hand-maintained copy that could drift."""
    if event.author == "user":
        display = (event.actions.state_delta or {}).get(_DISPLAY_MESSAGE_STATE_KEY)
        if isinstance(display, dict) and isinstance(display.get("message"), str):
            context = [
                {
                    "id": f"{event.id}:{index}",
                    "path": item.get("path", ""),
                    "startLine": item.get("start_line"),
                    "endLine": item.get("end_line"),
                    "content": "",
                }
                for index, item in enumerate(display.get("context", []))
                if isinstance(item, dict) and item.get("path")
            ]
            return [{
                "type": "user_message",
                "message": display["message"],
                "context": context,
            }]

        # Backward compatibility for already-persisted sessions.
        if event.content and event.content.parts:
            text = "".join(part.text or "" for part in event.content.parts)
            return [{"type": "user_message", "message": _legacy_display_text(text), "context": []}]
        return []

    if not event.content or not event.content.parts:
        return []
    payloads = []
    for part in event.content.parts:
        if part.function_call:
            # transfer_to_agent is ADK's own sub-agent routing mechanism
            # (root -> sabio_repos/sabio_comms) -- surfaced as a distinct
            # "handoff" event rather than a generic tool call, since it's
            # not one of this app's own tools.
            if part.function_call.name == "transfer_to_agent":
                payloads.append({"type": "handoff", "to": part.function_call.args.get("agent_name")})
            else:
                payloads.append({
                    "type": "tool_call",
                    "author": event.author,
                    "tool": part.function_call.name,
                    "args": part.function_call.args,
                })
        elif part.function_response:
            if part.function_response.name != "transfer_to_agent":
                payloads.append({
                    "type": "tool_result", "author": event.author, "tool": part.function_response.name,
                })
                if part.function_response.name == "read_file":
                    source = _source_reference(part.function_response.response or {})
                    if source is not None:
                        payloads.append(source)
                elif part.function_response.name == "get_message":
                    source = _communication_reference(part.function_response.response or {})
                    if source is not None:
                        payloads.append(source)
        elif part.text:
            payloads.append({"type": "text", "author": event.author, "text": part.text})
    return payloads


async def _stream(pubkey: str, session_id: str, message: str, context: list[ContextItem]) -> AsyncIterator[str]:
    service, runner = _get_session_runtime()
    lock = await _get_session_lock(pubkey, session_id)
    try:
        async with lock:
            await _ensure_session(service, pubkey, session_id, message)
            prompt = _build_prompt(message, context)
            content = types.Content(role="user", parts=[types.Part(text=prompt)])
            state_delta = {_DISPLAY_MESSAGE_STATE_KEY: _display_message(message, context)}

            async for event in runner.run_async(
                user_id=pubkey,
                session_id=session_id,
                new_message=content,
                state_delta=state_delta,
            ):
                for payload in _event_payloads(event):
                    yield _sse(payload)
    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})
    finally:
        yield _sse({"type": "done"})


@router.post("/stream")
async def stream_chat(req: ChatRequest, pubkey: str = Depends(get_current_pubkey)) -> StreamingResponse:
    session_id = str(req.session_id)
    return StreamingResponse(
        _stream(pubkey, session_id, req.message, req.context),
        media_type="text/event-stream",
    )


@router.get("/sessions")
async def list_chat_sessions(pubkey: str = Depends(get_current_pubkey)) -> list[dict]:
    service, _ = _get_session_runtime()
    result = await service.list_sessions(app_name=_APP_NAME, user_id=pubkey)
    sessions = [
        {
            "session_id": s.id,
            "title": (s.state or {}).get("title", "New conversation"),
            "last_update_time": s.last_update_time,
        }
        for s in result.sessions
    ]
    sessions.sort(key=lambda s: s["last_update_time"], reverse=True)
    return sessions


@router.get("/sessions/{session_id}")
async def get_chat_session(session_id: UUID, pubkey: str = Depends(get_current_pubkey)) -> dict:
    service, _ = _get_session_runtime()
    normalized_id = str(session_id)
    session = await service.get_session(
        app_name=_APP_NAME, user_id=pubkey, session_id=normalized_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    events = [payload for event in session.events for payload in _event_payloads(event)]
    return {"session_id": normalized_id, "events": events}


@router.delete("/sessions/{session_id}")
async def delete_chat_session(session_id: UUID, pubkey: str = Depends(get_current_pubkey)) -> dict:
    service, _ = _get_session_runtime()
    normalized_id = str(session_id)
    lock = await _get_session_lock(pubkey, normalized_id)
    async with lock:
        await service.delete_session(
            app_name=_APP_NAME, user_id=pubkey, session_id=normalized_id,
        )
    async with _session_locks_guard:
        _session_locks.pop((pubkey, normalized_id), None)
    return {"ok": True}
