"""Persistent, Nostr-scoped ADK chat sessions and their SSE API.

ADK owns the physical session/event tables, but this application owns their
lifecycle: db/migrations/0009_adk_sessions.sql records the pinned ADK 1.13
schema so it is visible to migrations, backups, and operators instead of
being an import-time side effect nobody knows about.
"""

import asyncio
import base64
import binascii
import json
import os
from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, DatabaseSessionService
from google.genai import types
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError

from agents.root.agent import root_agent
from backend.auth import get_current_pubkey

router = APIRouter(prefix="/chat", tags=["chat"])

_APP_NAME = "sabio"
_MAX_SESSIONS_PER_PUBKEY = 20  # oldest (by last_update_time) evicted past this
_TITLE_CHARS = 80
_CONTEXT_ITEM_CHARS = 8000
_DISPLAY_MESSAGE_STATE_KEY = "_sabio_display_message"
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_IMAGES = 4
_MAX_ATTACHMENTS = 8

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

# A browser disconnect should cancel a StreamingResponse, but relying on that
# transport detail alone is brittle (proxies may buffer, and an agent may be
# awaiting an LLM call when the socket closes). Each submitted turn therefore
# gets an explicit stop signal addressed by its run id.
_active_runs: dict[tuple[str, str, str], asyncio.Event] = {}


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
    for stop_event in _active_runs.values():
        stop_event.set()
    _active_runs.clear()
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


def _decode_image_data(data_url: str, mime_type: str) -> bytes:
    prefix = f"data:{mime_type};base64,"
    if not data_url.startswith(prefix):
        raise ValueError("image data URL does not match its MIME type")
    try:
        raw = base64.b64decode(data_url[len(prefix):], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image data is not valid base64") from exc
    if not raw:
        raise ValueError("image cannot be empty")
    if len(raw) > _MAX_IMAGE_BYTES:
        raise ValueError("image is larger than 5 MB")

    signatures = {
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
    }
    if not signatures.get(mime_type, False):
        raise ValueError("image bytes do not match the declared MIME type")
    return raw


class ImageAttachment(BaseModel):
    kind: Literal["image"]
    name: str = Field(min_length=1, max_length=255)
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
    size: int = Field(gt=0, le=_MAX_IMAGE_BYTES)
    data_url: str = Field(max_length=7_100_000)

    @model_validator(mode="after")
    def validate_image(self):
        raw = _decode_image_data(self.data_url, self.mime_type)
        if len(raw) != self.size:
            raise ValueError("image size does not match its data")
        return self


class RepositoryAttachment(BaseModel):
    kind: Literal["repository"]
    repo_id: Literal["core", "knots", "bips", "secp256k1"]
    label: str = Field(min_length=1, max_length=120)


class PersonAttachment(BaseModel):
    kind: Literal["person"]
    person_id: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=200)
    github_username: str | None = Field(default=None, max_length=100)
    bitcointalk_username: str | None = Field(default=None, max_length=100)


ChatAttachment = Annotated[
    ImageAttachment | RepositoryAttachment | PersonAttachment,
    Field(discriminator="kind"),
]


class ChatRequest(BaseModel):
    session_id: UUID
    run_id: UUID = Field(default_factory=uuid4)
    message: str = Field(min_length=1, max_length=16_000)
    context: list[ContextItem] = Field(default_factory=list, max_length=8)
    attachments: list[ChatAttachment] = Field(
        default_factory=list,
        max_length=_MAX_ATTACHMENTS,
    )

    @model_validator(mode="after")
    def validate_attachment_counts(self):
        image_count = sum(
            isinstance(attachment, ImageAttachment)
            for attachment in self.attachments
        )
        if image_count > _MAX_IMAGES:
            raise ValueError(f"at most {_MAX_IMAGES} images can be attached")
        return self


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=_TITLE_CHARS)


class StopChatRequest(BaseModel):
    session_id: UUID
    run_id: UUID


def _build_prompt(
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment] | None = None,
) -> str:
    attachments = attachments or []
    reference_blocks = []
    for attachment in attachments:
        if isinstance(attachment, RepositoryAttachment):
            reference_blocks.append(
                f"- Repository: {attachment.label} (`repo_name={attachment.repo_id}`)"
            )
        elif isinstance(attachment, PersonAttachment):
            identities = []
            if attachment.github_username:
                identities.append(f"GitHub @{attachment.github_username}")
            if attachment.bitcointalk_username:
                identities.append(f"BitcoinTalk {attachment.bitcointalk_username}")
            identity_text = f"; known as {', '.join(identities)}" if identities else ""
            reference_blocks.append(
                f"- Person: {attachment.label} (`person_id={attachment.person_id}`{identity_text})"
            )

    image_count = sum(isinstance(attachment, ImageAttachment) for attachment in attachments)
    if not context and not reference_blocks and image_count == 0:
        return message

    blocks = []
    for item in context:
        where = (
            f"{item.path} (lines {item.start_line}-{item.end_line})"
            if item.start_line
            else item.path
        )
        blocks.append(f"### {where}\n```\n{item.content[:_CONTEXT_ITEM_CHARS]}\n```")

    prompt_parts = []
    if blocks:
        prompt_parts.append("Attached code context:\n\n" + "\n\n".join(blocks))
    if reference_blocks:
        prompt_parts.append(
            "Selected Sabio context (use these exact repository/person identifiers when "
            "calling tools):\n" + "\n".join(reference_blocks)
        )
    if image_count:
        prompt_parts.append(
            f"The user attached {image_count} image{'s' if image_count != 1 else ''}. "
            "Inspect the image content directly when answering."
        )

    return "\n\n".join(prompt_parts) + "\n\n---\n\n" + message


def _build_content(
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment],
) -> types.Content:
    parts = [types.Part(text=_build_prompt(message, context, attachments))]
    for attachment in attachments:
        if isinstance(attachment, ImageAttachment):
            parts.append(
                types.Part.from_bytes(
                    data=_decode_image_data(attachment.data_url, attachment.mime_type),
                    mime_type=attachment.mime_type,
                )
            )
    return types.Content(role="user", parts=parts)


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


def _display_message(
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment] | None = None,
) -> dict:
    """Small user-facing copy attached to the persisted ADK user event.

    The actual event content is the model prompt, which includes full source
    excerpts. This metadata lets history reconstruct the original bubble and
    context chips without showing that generated prompt envelope.
    """
    attachment_metadata = []
    for attachment in attachments or []:
        if isinstance(attachment, ImageAttachment):
            attachment_metadata.append({
                "kind": "image",
                "name": attachment.name,
                "mime_type": attachment.mime_type,
                "size": attachment.size,
            })
        elif isinstance(attachment, RepositoryAttachment):
            attachment_metadata.append({
                "kind": "repository",
                "repo_id": attachment.repo_id,
                "label": attachment.label,
            })
        elif isinstance(attachment, PersonAttachment):
            attachment_metadata.append({
                "kind": "person",
                "person_id": attachment.person_id,
                "label": attachment.label,
                "github_username": attachment.github_username,
                "bitcointalk_username": attachment.bitcointalk_username,
            })

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
        # Image bytes already live in the persisted ADK content parts. Keep
        # only small display metadata here so session state does not duplicate
        # several megabytes of base64 for every image.
        "attachments": attachment_metadata,
    }


def _legacy_display_text(text: str) -> str:
    """Recover the visible message from sessions created before metadata."""
    separator = "\n\n---\n\n"
    return text.rsplit(separator, 1)[-1] if separator in text else text


def _history_attachments(event: Event, display: dict) -> list[dict]:
    image_parts = [
        part.inline_data
        for part in (event.content.parts if event.content else [])
        if part.inline_data and part.inline_data.data and part.inline_data.mime_type
    ]
    image_index = 0
    attachments = []

    for index, item in enumerate(display.get("attachments", [])):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        attachment_id = f"{event.id}:attachment:{index}"
        if kind == "image":
            if image_index >= len(image_parts):
                continue
            image = image_parts[image_index]
            image_index += 1
            attachments.append({
                "id": attachment_id,
                "kind": "image",
                "name": item.get("name") or "Attached image",
                "mimeType": image.mime_type,
                "size": len(image.data),
                "dataUrl": (
                    f"data:{image.mime_type};base64,"
                    f"{base64.b64encode(image.data).decode('ascii')}"
                ),
            })
        elif kind == "repository" and item.get("repo_id") and item.get("label"):
            attachments.append({
                "id": attachment_id,
                "kind": "repository",
                "repoId": item["repo_id"],
                "label": item["label"],
            })
        elif kind == "person" and item.get("person_id") and item.get("label"):
            attachments.append({
                "id": attachment_id,
                "kind": "person",
                "personId": item["person_id"],
                "label": item["label"],
                "githubUsername": item.get("github_username"),
                "bitcointalkUsername": item.get("bitcointalk_username"),
            })

    return attachments


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


def _web_references(response: dict) -> list[dict]:
    """Build source-card events only from search_web's cited URLs."""
    raw_sources = response.get("sources")
    if not isinstance(raw_sources, list):
        return []

    references = []
    seen_urls: set[str] = set()
    for source in raw_sources[:8]:
        if not isinstance(source, dict):
            continue
        title = source.get("title")
        url = source.get("url")
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(url, str)
            or not url.startswith(("http://", "https://"))
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        references.append({
            "type": "web_source",
            "title": title.strip(),
            "source_url": url,
        })
    return references


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
                "attachments": _history_attachments(event, display),
            }]

        # Backward compatibility for already-persisted sessions.
        if event.content and event.content.parts:
            text = "".join(part.text or "" for part in event.content.parts)
            return [{
                "type": "user_message",
                "message": _legacy_display_text(text),
                "context": [],
                "attachments": [],
            }]
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
                elif part.function_response.name == "search_web":
                    payloads.extend(_web_references(part.function_response.response or {}))
        elif part.text:
            payloads.append({"type": "text", "author": event.author, "text": part.text})
    return payloads


async def _stream(
    pubkey: str,
    session_id: str,
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment] | None = None,
    stop_event: asyncio.Event | None = None,
    active_run_key: tuple[str, str, str] | None = None,
) -> AsyncIterator[str]:
    attachments = attachments or []
    stop_event = stop_event or asyncio.Event()
    service, runner = _get_session_runtime()
    lock = await _get_session_lock(pubkey, session_id)
    events = None
    next_event_task = None
    stop_task = None
    try:
        async with lock:
            if stop_event.is_set():
                return
            await _ensure_session(service, pubkey, session_id, message)
            if stop_event.is_set():
                return
            content = _build_content(message, context, attachments)
            state_delta = {
                _DISPLAY_MESSAGE_STATE_KEY: _display_message(
                    message,
                    context,
                    attachments,
                )
            }

            events = runner.run_async(
                user_id=pubkey,
                session_id=session_id,
                new_message=content,
                state_delta=state_delta,
            ).__aiter__()

            while not stop_event.is_set():
                next_event_task = asyncio.create_task(anext(events))
                stop_task = asyncio.create_task(stop_event.wait())
                completed, _ = await asyncio.wait(
                    {next_event_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if stop_task in completed:
                    next_event_task.cancel()
                    await asyncio.gather(next_event_task, return_exceptions=True)
                    next_event_task = None
                    stop_task = None
                    break

                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)
                stop_task = None
                try:
                    event = next_event_task.result()
                except StopAsyncIteration:
                    next_event_task = None
                    break
                next_event_task = None

                for payload in _event_payloads(event):
                    if stop_event.is_set():
                        break
                    yield _sse(payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if not stop_event.is_set():
            yield _sse({"type": "error", "message": str(exc)})
    finally:
        pending_tasks = [
            task
            for task in (next_event_task, stop_task)
            if task is not None and not task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        if events is not None:
            close_events = getattr(events, "aclose", None)
            if close_events is not None:
                await close_events()

        if (
            active_run_key is not None
            and _active_runs.get(active_run_key) is stop_event
        ):
            _active_runs.pop(active_run_key, None)

    if not stop_event.is_set():
        yield _sse({"type": "done"})


@router.post("/stream")
async def stream_chat(req: ChatRequest, pubkey: str = Depends(get_current_pubkey)) -> StreamingResponse:
    session_id = str(req.session_id)
    run_id = str(req.run_id)
    active_run_key = (pubkey, session_id, run_id)
    stop_event = asyncio.Event()
    previous = _active_runs.get(active_run_key)
    if previous is not None:
        previous.set()
    _active_runs[active_run_key] = stop_event
    return StreamingResponse(
        _stream(
            pubkey,
            session_id,
            req.message,
            req.context,
            req.attachments,
            stop_event,
            active_run_key,
        ),
        media_type="text/event-stream",
    )


@router.post("/stop")
async def stop_chat(
    req: StopChatRequest,
    pubkey: str = Depends(get_current_pubkey),
) -> dict:
    stop_event = _active_runs.get((pubkey, str(req.session_id), str(req.run_id)))
    if stop_event is None:
        return {"stopped": False}
    stop_event.set()
    return {"stopped": True}


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


@router.patch("/sessions/{session_id}")
async def rename_chat_session(
    session_id: UUID, req: RenameSessionRequest, pubkey: str = Depends(get_current_pubkey),
) -> dict:
    """Renaming isn't a normal ADK session field -- state is the only mutable
    per-session slot the schema gives us, and the title already lives there
    (see _ensure_session). Updating it means appending a real event whose
    only effect is the state delta: author='system' (never 'user') keeps
    _event_payloads' history replay from mistaking this for a chat turn, and
    no content means it already returns [] there without any special-casing."""
    service, _ = _get_session_runtime()
    normalized_id = str(session_id)
    lock = await _get_session_lock(pubkey, normalized_id)
    async with lock:
        session = await service.get_session(
            app_name=_APP_NAME, user_id=pubkey, session_id=normalized_id,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title cannot be blank")
        await service.append_event(
            session, Event(author="system", actions=EventActions(state_delta={"title": title})),
        )
    return {"session_id": normalized_id, "title": title}


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
