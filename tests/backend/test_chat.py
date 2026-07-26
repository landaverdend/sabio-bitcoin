import asyncio
import base64
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


def test_chat_request_validates_and_builds_multimodal_image_content():
    raw = b"\x89PNG\r\n\x1a\n" + b"image-bytes"
    data_url = f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"
    request = chat.ChatRequest(
        session_id=uuid4(),
        message="What is this?",
        attachments=[
            {
                "kind": "image",
                "name": "diagram.png",
                "mime_type": "image/png",
                "size": len(raw),
                "data_url": data_url,
            }
        ],
    )

    content = chat._build_content(request.message, request.context, request.attachments)

    assert len(content.parts) == 2
    assert "attached 1 image" in content.parts[0].text
    assert content.parts[1].inline_data.mime_type == "image/png"
    assert content.parts[1].inline_data.data == raw

    with pytest.raises(ValidationError):
        chat.ChatRequest(
            session_id=uuid4(),
            message="bad image",
            attachments=[
                {
                    "kind": "image",
                    "name": "fake.png",
                    "mime_type": "image/png",
                    "size": 4,
                    "data_url": "data:image/png;base64,ZmFrZQ==",
                }
            ],
        )


def test_repository_and_person_attachments_ground_the_prompt():
    request = chat.ChatRequest(
        session_id=uuid4(),
        message="Compare their recent work",
        attachments=[
            {"kind": "repository", "repo_id": "core", "label": "Bitcoin Core"},
            {
                "kind": "person",
                "person_id": 42,
                "label": "Ada",
                "github_username": "ada",
            },
        ],
    )

    prompt = chat._build_prompt(request.message, [], request.attachments)

    assert "repo_name=core" in prompt
    assert "person_id=42" in prompt
    assert "GitHub @ada" in prompt
    assert prompt.endswith("Compare their recent work")


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
            "attachments": [],
        }
    ]


def test_history_reconstructs_image_and_entity_attachments():
    raw = b"\x89PNG\r\n\x1a\n" + b"stored-image"
    event = Event(
        id="event-image",
        invocation_id="invocation-image",
        author="user",
        content=types.Content(
            role="user",
            parts=[
                types.Part(text="Inspect this"),
                types.Part.from_bytes(data=raw, mime_type="image/png"),
            ],
        ),
        actions=EventActions(
            state_delta={
                chat._DISPLAY_MESSAGE_STATE_KEY: {
                    "message": "Inspect this",
                    "context": [],
                    "attachments": [
                        {
                            "kind": "image",
                            "name": "chart.png",
                            "mime_type": "image/png",
                            "size": len(raw),
                        },
                        {
                            "kind": "repository",
                            "repo_id": "core",
                            "label": "Bitcoin Core",
                        },
                    ],
                }
            }
        ),
    )

    payload = chat._event_payloads(event)[0]

    assert payload["attachments"][0] == {
        "id": "event-image:attachment:0",
        "kind": "image",
        "name": "chart.png",
        "mimeType": "image/png",
        "size": len(raw),
        "dataUrl": f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}",
    }
    assert payload["attachments"][1] == {
        "id": "event-image:attachment:1",
        "kind": "repository",
        "repoId": "core",
        "label": "Bitcoin Core",
    }


def test_legacy_history_hides_attached_prompt_envelope():
    event = Event(
        author="user",
        content=types.Content(
            role="user",
            parts=[types.Part(text="Attached context:\n\nsource\n\n---\n\nWhat changed?")],
        ),
    )

    assert chat._event_payloads(event)[0]["message"] == "What changed?"


def test_read_file_result_becomes_interactive_source_reference():
    response = {
        "repo": "core",
        "path": "src/validation.cpp",
        "ref": "master",
        "start_line": 100,
        "end_line": 118,
        "total_lines": 6200,
        "content": "source",
        "github_url": "https://github.com/bitcoin/bitcoin/blob/master/src/validation.cpp#L100-L118",
    }
    event = Event(
        author="sabio_repos",
        content=types.Content(
            role="user",
            parts=[types.Part.from_function_response(name="read_file", response=response)],
        ),
    )

    assert chat._event_payloads(event) == [
        {
            "type": "tool_result",
            "author": "sabio_repos",
            "tool": "read_file",
        },
        {
            "type": "source",
            "repo": "core",
            "path": "src/validation.cpp",
            "ref": "master",
            "start_line": 100,
            "end_line": 118,
            "github_url": response["github_url"],
        },
    ]


def test_incomplete_read_file_result_does_not_render_broken_reference():
    event = Event(
        author="sabio_repos",
        content=types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(
                    name="read_file",
                    response={"error": "file not found"},
                )
            ],
        ),
    )

    assert chat._event_payloads(event) == [
        {
            "type": "tool_result",
            "author": "sabio_repos",
            "tool": "read_file",
        }
    ]

    assert chat._source_reference({
        "repo": "core",
        "path": "short.cpp",
        "ref": "master",
        "start_line": 50,
        "end_line": 49,
        "github_url": "https://github.com/example",
    }) is None


def test_get_message_result_becomes_communication_source():
    response = {
        "id": 42,
        "channel": "bitcointalk",
        "external_id": "12345",
        "author": "satoshi",
        "email": None,
        "title": "Re: Philosophy",
        "body": "  A source-backed statement.\n\nWith useful context.  ",
        "url": "https://bitcointalk.org/index.php?topic=1.msg42#msg42",
        "posted_at": "2010-01-01T00:00:00+00:00",
        "thread_id": "1",
        "person_id": 1,
    }
    event = Event(
        author="sabio_comms",
        content=types.Content(
            role="user",
            parts=[types.Part.from_function_response(name="get_message", response=response)],
        ),
    )

    assert chat._event_payloads(event) == [
        {
            "type": "tool_result",
            "author": "sabio_comms",
            "tool": "get_message",
        },
        {
            "type": "communication_source",
            "message_id": "42",
            "channel": "bitcointalk",
            "author": "satoshi",
            "title": "Re: Philosophy",
            "posted_at": "2010-01-01T00:00:00+00:00",
            "excerpt": "A source-backed statement. With useful context.",
            "source_url": response["url"],
        },
    ]


def test_search_result_does_not_become_final_communication_source():
    event = Event(
        author="sabio_comms",
        content=types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(
                    name="search_messages",
                    response={"result": [{"id": "message:42", "snippet": "not full evidence"}]},
                )
            ],
        ),
    )

    assert chat._event_payloads(event) == [
        {
            "type": "tool_result",
            "author": "sabio_comms",
            "tool": "search_messages",
        }
    ]


def test_search_web_result_becomes_clickable_web_sources():
    response = {
        "answer": "A sourced answer.",
        "sources": [
            {
                "title": "Bitcoin Optech",
                "url": "https://bitcoinops.org/en/newsletters/2026/01/01/",
            },
            {
                "title": "Duplicate",
                "url": "https://bitcoinops.org/en/newsletters/2026/01/01/",
            },
            {"title": "Unsafe", "url": "javascript:alert(1)"},
        ],
    }
    event = Event(
        author="sabio_repos",
        content=types.Content(
            role="user",
            parts=[types.Part.from_function_response(name="search_web", response=response)],
        ),
    )

    assert chat._event_payloads(event) == [
        {
            "type": "tool_result",
            "author": "sabio_repos",
            "tool": "search_web",
        },
        {
            "type": "web_source",
            "title": "Bitcoin Optech",
            "source_url": response["sources"][0]["url"],
        },
    ]


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


def test_stream_stop_cancels_the_pending_agent_event():
    async def exercise():
        started = asyncio.Event()
        closed = asyncio.Event()
        stop_event = asyncio.Event()
        active_run_key = ("pubkey", str(uuid4()), str(uuid4()))

        class WaitingRunner:
            async def run_async(self, **_):
                try:
                    started.set()
                    await asyncio.Event().wait()
                    yield Event(author="root")
                finally:
                    closed.set()

        chat._active_runs[active_run_key] = stop_event
        with (
            patch.object(chat, "_get_session_runtime", return_value=(object(), WaitingRunner())),
            patch.object(chat, "_ensure_session", new=AsyncMock()),
        ):
            stream = chat._stream(
                active_run_key[0],
                active_run_key[1],
                "hello",
                [],
                stop_event=stop_event,
                active_run_key=active_run_key,
            )
            next_frame = asyncio.create_task(anext(stream))
            await asyncio.wait_for(started.wait(), timeout=1)
            stop_event.set()
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(next_frame, timeout=1)

        assert closed.is_set()
        assert active_run_key not in chat._active_runs

    asyncio.run(exercise())


def test_stop_chat_signals_only_the_addressed_run():
    async def exercise():
        pubkey = "pubkey"
        session_id = uuid4()
        run_id = uuid4()
        active_key = (pubkey, str(session_id), str(run_id))
        other_key = (pubkey, str(session_id), str(uuid4()))
        active_stop = asyncio.Event()
        other_stop = asyncio.Event()
        chat._active_runs[active_key] = active_stop
        chat._active_runs[other_key] = other_stop
        try:
            result = await chat.stop_chat(
                chat.StopChatRequest(session_id=session_id, run_id=run_id),
                pubkey,
            )
            assert result == {"stopped": True}
            assert active_stop.is_set()
            assert not other_stop.is_set()
        finally:
            chat._active_runs.pop(active_key, None)
            chat._active_runs.pop(other_key, None)

    asyncio.run(exercise())
