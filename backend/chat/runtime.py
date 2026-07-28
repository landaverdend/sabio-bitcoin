"""ADK session lifecycle, per-session concurrency, and stream cancellation."""

import asyncio
import json
import os
from collections.abc import AsyncIterator

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, DatabaseSessionService
from sqlalchemy.exc import IntegrityError

from agents.root.agent import root_agent
from backend.chat.constants import (
    APP_NAME,
    DISPLAY_MESSAGE_STATE_KEY,
    TITLE_CHARS,
)
from backend.chat.content import build_content, display_message
from backend.chat.events import event_payloads
from backend.chat.models import ChatAttachment, ChatLocale, ContextItem

# Constructing DatabaseSessionService in pinned ADK 1.13 calls create_all().
# Keep that out of import time so unrelated commands do not need a live DB.
_session_service: DatabaseSessionService | None = None
_runner: Runner | None = None

# ADK has stale-session protection but no same-session in-process lock.
_session_locks: dict[tuple[str, str], asyncio.Lock] = {}
_session_locks_guard = asyncio.Lock()

# Explicit run signals supplement transport-level disconnect cancellation.
_active_runs: dict[tuple[str, str, str], asyncio.Event] = {}


def get_session_runtime() -> tuple[DatabaseSessionService, Runner]:
    global _runner, _session_service
    if _session_service is None:
        _session_service = DatabaseSessionService(
            db_url=os.environ["DATABASE_URL"],
            pool_pre_ping=True,
        )
    if _runner is None:
        _runner = Runner(
            app_name=APP_NAME,
            agent=root_agent,
            session_service=_session_service,
        )
    return _session_service, _runner


def close_session_storage() -> None:
    """Stop active runs and dispose pooled DB connections at shutdown."""
    global _runner, _session_service
    for stop_event in _active_runs.values():
        stop_event.set()
    _active_runs.clear()
    if _session_service is not None:
        _session_service.db_engine.dispose()
    _session_service = None
    _runner = None
    _session_locks.clear()


async def get_session_lock(pubkey: str, session_id: str) -> asyncio.Lock:
    key = (pubkey, session_id)
    async with _session_locks_guard:
        lock = _session_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[key] = lock
        return lock


async def remove_session_lock(pubkey: str, session_id: str) -> None:
    async with _session_locks_guard:
        _session_locks.pop((pubkey, session_id), None)


def register_active_run(
    pubkey: str,
    session_id: str,
    run_id: str,
) -> tuple[tuple[str, str, str], asyncio.Event]:
    key = (pubkey, session_id, run_id)
    previous = _active_runs.get(key)
    if previous is not None:
        previous.set()
    stop_event = asyncio.Event()
    _active_runs[key] = stop_event
    return key, stop_event


def stop_active_run(pubkey: str, session_id: str, run_id: str) -> bool:
    stop_event = _active_runs.get((pubkey, session_id, run_id))
    if stop_event is None:
        return False
    stop_event.set()
    return True


async def ensure_session(
    service: BaseSessionService,
    pubkey: str,
    session_id: str,
    message: str,
    locale: ChatLocale = "en",
) -> None:
    existing = await service.get_session(
        app_name=APP_NAME,
        user_id=pubkey,
        session_id=session_id,
    )
    if existing is not None:
        return

    title = message.strip()[:TITLE_CHARS] or (
        "Nueva conversación" if locale == "es" else "New conversation"
    )
    try:
        await service.create_session(
            app_name=APP_NAME,
            user_id=pubkey,
            session_id=session_id,
            state={"title": title},
        )
    except IntegrityError:
        existing = await service.get_session(
            app_name=APP_NAME,
            user_id=pubkey,
            session_id=session_id,
        )
        if existing is None:
            raise


def encode_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def stream(
    pubkey: str,
    session_id: str,
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment] | None = None,
    stop_event: asyncio.Event | None = None,
    active_run_key: tuple[str, str, str] | None = None,
    locale: ChatLocale = "en",
) -> AsyncIterator[str]:
    attachments = attachments or []
    stop_event = stop_event or asyncio.Event()
    service, runner = get_session_runtime()
    lock = await get_session_lock(pubkey, session_id)
    events = None
    next_event_task = None
    stop_task = None

    try:
        async with lock:
            if stop_event.is_set():
                return
            await ensure_session(service, pubkey, session_id, message, locale)
            if stop_event.is_set():
                return

            events = runner.run_async(
                user_id=pubkey,
                session_id=session_id,
                new_message=build_content(
                    message,
                    context,
                    attachments,
                    locale,
                ),
                state_delta={
                    DISPLAY_MESSAGE_STATE_KEY: display_message(
                        message,
                        context,
                        attachments,
                    )
                },
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
                    await asyncio.gather(
                        next_event_task,
                        return_exceptions=True,
                    )
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

                for payload in event_payloads(event):
                    if stop_event.is_set():
                        break
                    yield encode_sse(payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if not stop_event.is_set():
            yield encode_sse({"type": "error", "message": str(exc)})
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
        yield encode_sse({"type": "done"})
