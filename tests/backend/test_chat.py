import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from backend import chat


def test_chat_request_requires_bounded_uuid_session():
    with pytest.raises(ValidationError):
        chat.ChatRequest(session_id="not-a-uuid", message="hello")

    with pytest.raises(ValidationError):
        chat.ChatRequest(
            session_id=uuid4(),
            message="hello",
            context=[
                {"path": f"file-{index}", "content": ""}
                for index in range(9)
            ],
        )


def test_history_uses_display_message_instead_of_generated_prompt():
    event = Event(
        id="event-1",
        invocation_id="invocation-1",
        author="user",
        content=types.Content(
            role="user",
            parts=[types.Part(text="Attached context:\n\nsecret source\n\n---\n\nExplain this")],
        ),
        actions=EventActions(
            state_delta={
                chat._DISPLAY_MESSAGE_STATE_KEY: {
                    "message": "Explain this",
                    "context": [
                        {
                            "path": "src/example.py",
                            "start_line": 10,
                            "end_line": 20,
                        }
                    ],
                }
            }
        ),
    )

    assert chat._event_payloads(event) == [
        {
            "type": "user_message",
            "message": "Explain this",
            "context": [
                {
                    "id": "event-1:0",
                    "path": "src/example.py",
                    "startLine": 10,
                    "endLine": 20,
                    "content": "",
                }
            ],
        }
    ]


def test_legacy_history_hides_attached_prompt_envelope():
    event = Event(
        author="user",
        content=types.Content(
            role="user",
            parts=[types.Part(text="Attached context:\n\nsource\n\n---\n\nWhat changed?")],
        ),
    )

    assert chat._event_payloads(event)[0]["message"] == "What changed?"


class _FakeSessionService:
    def __init__(self):
        self.sessions = [
            SimpleNamespace(id=f"old-{index}", last_update_time=float(index), state={})
            for index in range(chat._MAX_SESSIONS_PER_PUBKEY)
        ]
        self.deleted = []

    async def get_session(self, **_):
        return None

    async def create_session(self, *, session_id, state, **_):
        created = SimpleNamespace(id=session_id, last_update_time=100.0, state=state)
        self.sessions.append(created)
        return created

    async def list_sessions(self, **_):
        return SimpleNamespace(sessions=self.sessions)

    async def delete_session(self, *, session_id, **_):
        self.deleted.append(session_id)
        self.sessions = [session for session in self.sessions if session.id != session_id]


def test_ensure_session_creates_then_prunes_oldest():
    service = _FakeSessionService()
    asyncio.run(chat._ensure_session(service, "pubkey", str(uuid4()), "  First question  "))

    assert service.deleted == ["old-0"]
    assert len(service.sessions) == chat._MAX_SESSIONS_PER_PUBKEY
    assert service.sessions[-1].state["title"] == "First question"


def test_ensure_session_treats_concurrent_duplicate_create_as_success():
    intended_session = str(uuid4())

    class RaceService(_FakeSessionService):
        def __init__(self):
            super().__init__()
            self.sessions = []
            self.get_calls = 0

        async def get_session(self, **_):
            self.get_calls += 1
            return None if self.get_calls == 1 else SimpleNamespace(id=intended_session)

        async def create_session(self, **_):
            raise IntegrityError("duplicate", {}, RuntimeError("unique violation"))

    service = RaceService()
    asyncio.run(chat._ensure_session(service, "pubkey", intended_session, "hello"))

    assert service.get_calls == 2
    assert service.deleted == []


def test_stream_reports_setup_errors_as_sse_and_always_finishes():
    async def collect():
        with (
            patch.object(chat, "_get_session_runtime", return_value=(object(), object())),
            patch.object(chat, "_ensure_session", new=AsyncMock(side_effect=RuntimeError("db down"))),
        ):
            return [
                frame
                async for frame in chat._stream("pubkey", str(uuid4()), "hello", [])
            ]

    frames = asyncio.run(collect())
    payloads = [json.loads(frame.removeprefix("data: ").strip()) for frame in frames]
    assert payloads == [
        {"type": "error", "message": "db down"},
        {"type": "done"},
    ]
