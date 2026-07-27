import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from agents.shared import tools


def test_now_returns_current_utc_time():
    before = datetime.now().timestamp()
    result = tools.now("UTC")
    after = datetime.now().timestamp()

    assert result["timezone"] == "UTC"
    assert result["date"] == result["iso"][:10]
    assert int(before) <= result["unix_timestamp"] <= int(after)


def test_now_accepts_an_iana_timezone_and_rejects_unknown_ones():
    result = tools.now("America/Argentina/Buenos_Aires")

    assert result["timezone"] == "America/Argentina/Buenos_Aires"
    assert result["iso"].endswith("-03:00")
    assert "error" in tools.now("not/a-timezone")


def test_search_web_returns_only_unique_cited_http_sources():
    response = SimpleNamespace(
        output_text="A sourced answer. https://bitcoinops.org/example?utm_source=openai",
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        type="output_text",
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                title="Bitcoin Optech",
                                url="https://bitcoinops.org/example?utm_source=openai",
                            ),
                            SimpleNamespace(
                                type="url_citation",
                                title="Duplicate",
                                url="https://bitcoinops.org/example?utm_source=openai",
                            ),
                            SimpleNamespace(
                                type="url_citation",
                                title="Unsafe",
                                url="javascript:alert(1)",
                            ),
                        ],
                    )
                ],
            )
        ],
    )

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        async def create(self, **kwargs):
            self.kwargs = kwargs
            return response

    fake_responses = FakeResponses()

    class FakeClient:
        def __init__(self, **_):
            self.responses = fake_responses

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    with patch.object(tools, "AsyncOpenAI", FakeClient):
        result = asyncio.run(tools.search_web(" latest Bitcoin Core release "))

    assert result == {
        "answer": "A sourced answer. https://bitcoinops.org/example",
        "sources": [
            {
                "title": "Bitcoin Optech",
                "url": "https://bitcoinops.org/example",
            }
        ],
        "source_count": 1,
    }
    assert fake_responses.kwargs["store"] is False
    assert fake_responses.kwargs["tools"] == [
        {"type": "web_search", "search_context_size": "low"}
    ]
    assert fake_responses.kwargs["input"][1]["content"] == "latest Bitcoin Core release"


def test_search_web_rejects_unbounded_queries_without_an_api_call():
    result = asyncio.run(tools.search_web("x" * 1_001))

    assert "error" in result
    assert result["sources"] == []
