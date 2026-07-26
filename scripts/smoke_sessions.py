"""Exercise Nostr auth and persistent chat sessions through the frontend origin.

Run this while the backend (port 8010) and Vite dev server (port 5173) are
running:

    python scripts/smoke_sessions.py

The script generates a disposable Nostr key in memory, creates one session,
verifies that it can be listed and reloaded, and removes it before exiting.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any
from uuid import uuid4

import requests
from pynostr.event import Event
from pynostr.key import PrivateKey


def _json(response: requests.Response) -> Any:
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type, (
        f"{response.request.method} {response.url} returned {content_type!r}, "
        "not JSON"
    )
    response.raise_for_status()
    return response.json()


def _signed_auth_event(private_key: PrivateKey, nonce: str) -> dict[str, Any]:
    event = Event(
        content="",
        created_at=int(time.time()),
        kind=22242,
        tags=[["challenge", nonce]],
    )
    event.sign(private_key.hex())
    return event.to_dict()


def run(
    base_url: str,
    expect_source: bool = False,
    expect_communication_source: bool = False,
) -> None:
    http = requests.Session()
    private_key = PrivateKey()
    pubkey = private_key.public_key.hex()
    session_id = str(uuid4())
    created = False

    print(f"Using disposable Nostr identity {pubkey[:8]}…{pubkey[-8:]}")
    try:
        challenge = _json(
            http.post(f"{base_url}/auth/challenge", timeout=10)
        )["nonce"]
        verified = _json(
            http.post(
                f"{base_url}/auth/verify",
                json={"event": _signed_auth_event(private_key, challenge)},
                timeout=10,
            )
        )
        assert verified["pubkey"] == pubkey
        assert _json(http.get(f"{base_url}/auth/me", timeout=10))["pubkey"] == pubkey
        print("✓ Nostr challenge login")

        if expect_source:
            message = (
                "In Bitcoin Core, read src/consensus/consensus.h lines 1-37 and briefly "
                "explain the exact code that defines MAX_BLOCK_WEIGHT."
            )
        elif expect_communication_source:
            message = (
                "What was Satoshi Nakamoto's take on libertarianism? Ground every "
                "claim in full archived messages and retrieve each message you cite."
            )
        else:
            message = "Reply exactly: Sabio session smoke test passed."
        response = http.post(
            f"{base_url}/chat/stream",
            json={"session_id": session_id, "message": message, "context": []},
            headers={"accept": "text/event-stream"},
            stream=True,
            timeout=(10, 180),
        )
        response.raise_for_status()
        created = True

        stream_events: list[dict[str, Any]] = []
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith("data: "):
                stream_events.append(json.loads(line.removeprefix("data: ")))

        errors = [event["message"] for event in stream_events if event["type"] == "error"]
        assert not errors, f"chat stream failed: {errors}"
        assert stream_events and stream_events[-1]["type"] == "done"
        assert any(event["type"] == "text" for event in stream_events)
        print("✓ Chat streamed through the Vite proxy")
        if expect_source:
            sources = [event for event in stream_events if event["type"] == "source"]
            assert sources, "the code explanation did not emit a source reference"
            assert all(
                source["github_url"].startswith("https://github.com/")
                and source["start_line"] <= source["end_line"]
                for source in sources
            ), f"invalid source metadata: {sources!r}"
            print("✓ Live response includes exact-line GitHub source references")
        if expect_communication_source:
            communication_sources = [
                event
                for event in stream_events
                if event["type"] == "communication_source"
            ]
            assert communication_sources, (
                "the communication answer did not emit an archived-message source"
            )
            assert all(
                source["source_url"].startswith(("http://", "https://"))
                and source["message_id"].isdigit()
                and source["excerpt"]
                for source in communication_sources
            ), f"invalid communication source metadata: {communication_sources!r}"
            print("✓ Live response includes original communication sources")

            detail = _json(
                http.get(
                    f"{base_url}/comms/messages/{communication_sources[0]['message_id']}",
                    timeout=20,
                )
            )
            assert detail["body"]
            assert detail["url"] == communication_sources[0]["source_url"]
            print("✓ Complete archived message loads through the side-panel API")

        sessions = _json(http.get(f"{base_url}/chat/sessions", timeout=20))
        summary = next(item for item in sessions if item["session_id"] == session_id)
        assert summary["title"] == message[:80]
        print("✓ Session appears in the signed-in session list")

        history = _json(
            http.get(f"{base_url}/chat/sessions/{session_id}", timeout=20)
        )
        assert history["session_id"] == session_id
        user_messages = [
            event
            for event in history["events"]
            if event["type"] == "user_message"
        ]
        assert any(
            event["type"] == "user_message" and event["message"] == message
            for event in history["events"]
        ), (
            f"stored user messages did not match: {user_messages!r}; "
            "all events: "
            f"{[(event.get('type'), event.get('author'), event.get('text')) for event in history['events']]!r}"
        )
        assert any(event["type"] == "text" for event in history["events"])
        if expect_source:
            assert any(event["type"] == "source" for event in history["events"])
            print("✓ Source references survive history reload")
        if expect_communication_source:
            assert any(
                event["type"] == "communication_source"
                for event in history["events"]
            )
            print("✓ Communication sources survive history reload")
        print("✓ Stored history reloads")

        _json(http.delete(f"{base_url}/chat/sessions/{session_id}", timeout=20))
        created = False
        sessions = _json(http.get(f"{base_url}/chat/sessions", timeout=20))
        assert all(item["session_id"] != session_id for item in sessions)
        print("✓ Session deletes cleanly")
    finally:
        if created:
            try:
                http.delete(f"{base_url}/chat/sessions/{session_id}", timeout=20)
            except requests.RequestException:
                pass
        try:
            http.post(f"{base_url}/auth/logout", timeout=10)
        except requests.RequestException:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://localhost:5173",
        help="Frontend origin whose API proxy should be tested",
    )
    parser.add_argument(
        "--expect-source",
        action="store_true",
        help="Ask a real code question and require exact-line source events",
    )
    parser.add_argument(
        "--expect-communication-source",
        action="store_true",
        help="Ask a real archive question and require original-message sources",
    )
    args = parser.parse_args()
    if args.expect_source and args.expect_communication_source:
        parser.error("choose only one source smoke-test mode")
    run(
        args.base_url.rstrip("/"),
        expect_source=args.expect_source,
        expect_communication_source=args.expect_communication_source,
    )
