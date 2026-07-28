"""FastAPI routes for chat streaming and persisted conversations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from backend.auth import get_current_pubkey
from backend.chat.constants import APP_NAME
from backend.chat.events import event_payloads
from backend.chat.models import (
    ChatRequest,
    RenameSessionRequest,
    StopChatRequest,
)
from backend.chat.runtime import (
    get_session_lock,
    get_session_runtime,
    register_active_run,
    remove_session_lock,
    stop_active_run,
    stream,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def stream_chat(
    req: ChatRequest,
    pubkey: str = Depends(get_current_pubkey),
) -> StreamingResponse:
    session_id = str(req.session_id)
    active_run_key, stop_event = register_active_run(
        pubkey,
        session_id,
        str(req.run_id),
    )
    return StreamingResponse(
        stream(
            pubkey,
            session_id,
            req.message,
            req.context,
            attachments=req.attachments,
            stop_event=stop_event,
            active_run_key=active_run_key,
            locale=req.locale,
        ),
        media_type="text/event-stream",
    )


@router.post("/stop")
async def stop_chat(
    req: StopChatRequest,
    pubkey: str = Depends(get_current_pubkey),
) -> dict:
    stopped = stop_active_run(
        pubkey,
        str(req.session_id),
        str(req.run_id),
    )
    return {"stopped": stopped}


@router.get("/sessions")
async def list_chat_sessions(
    pubkey: str = Depends(get_current_pubkey),
) -> list[dict]:
    service, _ = get_session_runtime()
    result = await service.list_sessions(app_name=APP_NAME, user_id=pubkey)
    sessions = [
        {
            "session_id": session.id,
            "title": (session.state or {}).get("title", "New conversation"),
            "last_update_time": session.last_update_time,
        }
        for session in result.sessions
    ]
    sessions.sort(key=lambda session: session["last_update_time"], reverse=True)
    return sessions


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: UUID,
    pubkey: str = Depends(get_current_pubkey),
) -> dict:
    service, _ = get_session_runtime()
    normalized_id = str(session_id)
    session = await service.get_session(
        app_name=APP_NAME,
        user_id=pubkey,
        session_id=normalized_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    events = [payload for event in session.events for payload in event_payloads(event)]
    return {"session_id": normalized_id, "events": events}


@router.patch("/sessions/{session_id}")
async def rename_chat_session(
    session_id: UUID,
    req: RenameSessionRequest,
    pubkey: str = Depends(get_current_pubkey),
) -> dict:
    service, _ = get_session_runtime()
    normalized_id = str(session_id)
    lock = await get_session_lock(pubkey, normalized_id)
    async with lock:
        session = await service.get_session(
            app_name=APP_NAME,
            user_id=pubkey,
            session_id=normalized_id,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title cannot be blank")
        await service.append_event(
            session,
            Event(
                author="system",
                actions=EventActions(state_delta={"title": title}),
            ),
        )
    return {"session_id": normalized_id, "title": title}


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: UUID,
    pubkey: str = Depends(get_current_pubkey),
) -> dict:
    service, _ = get_session_runtime()
    normalized_id = str(session_id)
    lock = await get_session_lock(pubkey, normalized_id)
    async with lock:
        await service.delete_session(
            app_name=APP_NAME,
            user_id=pubkey,
            session_id=normalized_id,
        )
    await remove_session_lock(pubkey, normalized_id)
    return {"ok": True}
