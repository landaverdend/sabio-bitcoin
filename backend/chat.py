"""Chat endpoint -- streams a root-agent turn (text plus tool-use/handoff
events) to the frontend over SSE.

Sessions are in-memory only (InMemorySessionService): lost on backend
restart, scoped to a single fixed user_id since there's no auth yet. Fine
for a local single-user tool right now -- swap in ADK's DatabaseSessionService
(pointed at the existing Postgres) if this ever needs to survive a restart.
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from agents.root.agent import root_agent

router = APIRouter(prefix="/chat", tags=["chat"])

_APP_NAME = "sabio"
_USER_ID = "local"  # single-user local tool, no auth yet

# Built once at import time and reused across requests -- InMemoryRunner owns
# an InMemorySessionService that keys sessions by (app_name, user_id,
# session_id), so a fresh Runner per request would silently drop history.
_runner = InMemoryRunner(agent=root_agent, app_name=_APP_NAME)


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _sse(payload: dict) -> str:
    # default=str: function-call args occasionally carry non-JSON-primitive
    # values (e.g. from Google AI's schema handling) -- str() is a safe
    # fallback rather than letting json.dumps raise mid-stream.
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _ensure_session(session_id: str) -> None:
    existing = await _runner.session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id,
    )
    if existing is None:
        await _runner.session_service.create_session(
            app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id,
        )


async def _stream(session_id: str, message: str) -> AsyncIterator[str]:
    await _ensure_session(session_id)
    content = types.Content(role="user", parts=[types.Part(text=message)])

    try:
        async for event in _runner.run_async(
            user_id=_USER_ID, session_id=session_id, new_message=content,
        ):
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.function_call:
                    # transfer_to_agent is ADK's own sub-agent routing
                    # mechanism (root -> sabio_repos/sabio_comms) -- surfaced
                    # as a distinct "handoff" event rather than a generic
                    # tool call, since it's not one of this app's own tools.
                    if part.function_call.name == "transfer_to_agent":
                        yield _sse({
                            "type": "handoff",
                            "to": part.function_call.args.get("agent_name"),
                        })
                    else:
                        yield _sse({
                            "type": "tool_call",
                            "author": event.author,
                            "tool": part.function_call.name,
                            "args": part.function_call.args,
                        })
                elif part.function_response:
                    if part.function_response.name != "transfer_to_agent":
                        yield _sse({
                            "type": "tool_result",
                            "author": event.author,
                            "tool": part.function_response.name,
                        })
                elif part.text:
                    yield _sse({"type": "text", "author": event.author, "text": part.text})
    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})
    finally:
        yield _sse({"type": "done"})


@router.post("/stream")
async def stream_chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_stream(req.session_id, req.message), media_type="text/event-stream")
