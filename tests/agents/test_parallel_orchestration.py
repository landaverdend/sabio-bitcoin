import asyncio

from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from pydantic import PrivateAttr

from agents.shared.research_tool import ParallelResearchTool
from backend.chat.events import event_payloads

EXACT_BIP_119_PROMPT = (
    "Cuál es el estado real de implementación de BIP-119 "
    "(OP_CHECKTEMPLATEVERIFY) en Bitcoin Core y Bitcoin Knots, y qué está "
    "diciendo realmente la comunidad al respecto en la lista de correo o "
    "en BitcoinTalk?"
)


class ParallelSpecialistLlm(BaseLlm):
    _call_count: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream=False):
        if self._call_count == 0:
            self._call_count += 1
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=name,
                                args={"request": EXACT_BIP_119_PROMPT},
                            )
                        )
                        for name in ("sabio_repos", "sabio_comms", "sabio_irc")
                    ],
                )
            )
            return

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Synthesis complete.")],
            )
        )


class EvidenceSpecialistLlm(BaseLlm):
    specialist_name: str
    evidence_tool_name: str
    evidence_tool_args: dict
    _call_count: int = PrivateAttr(default=0)
    _started: set[str] = PrivateAttr()
    _all_started: asyncio.Event = PrivateAttr()

    def set_barrier(self, started: set[str], all_started: asyncio.Event):
        self._started = started
        self._all_started = all_started

    async def generate_content_async(self, llm_request, stream=False):
        if self._call_count == 0:
            self._call_count += 1
            self._started.add(self.specialist_name)
            if len(self._started) == 3:
                self._all_started.set()
            await asyncio.wait_for(self._all_started.wait(), timeout=0.5)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=self.evidence_tool_name,
                                args=self.evidence_tool_args,
                            )
                        )
                    ],
                )
            )
            return

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=f"{self.specialist_name} primary evidence complete."
                    )
                ],
            )
        )


class RepeatingRootLlm(BaseLlm):
    _call_count: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream=False):
        self._call_count += 1
        if self._call_count <= 2:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="sabio_repos",
                                args={
                                    "request": (
                                        "Initial research."
                                        if self._call_count == 1
                                        else "Unnecessary second pass."
                                    )
                                },
                            )
                        )
                    ],
                )
            )
            return

        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Final synthesis.")],
            )
        )


class CountingSpecialistLlm(BaseLlm):
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Primary evidence.")],
            )
        )


def test_exact_multi_source_prompt_starts_specialists_concurrently():
    started: set[str] = set()
    all_started = asyncio.Event()

    async def mark_started(name: str) -> dict:
        started.add(name)
        if len(started) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=0.5)
        return {"answer": f"{name} evidence", "sources": []}

    async def sabio_repos(request: str) -> dict:
        return await mark_started("repos")

    async def sabio_comms(request: str) -> dict:
        return await mark_started("comms")

    async def sabio_irc(request: str) -> dict:
        return await mark_started("irc")

    async def run():
        service = InMemorySessionService()
        agent = Agent(
            name="parallel_test_root",
            model=ParallelSpecialistLlm(model="parallel-test"),
            instruction="Call the required research tools in parallel.",
            tools=[sabio_repos, sabio_comms, sabio_irc],
        )
        runner = Runner(
            app_name="parallel-test",
            agent=agent,
            session_service=service,
        )
        session = await service.create_session(
            app_name="parallel-test",
            user_id="test-user",
        )
        return [
            event
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=EXACT_BIP_119_PROMPT)],
                ),
            )
        ]

    events = asyncio.run(run())

    assert started == {"repos", "comms", "irc"}
    function_response_event = next(
        event
        for event in events
        if event.content
        and sum(bool(part.function_response) for part in event.content.parts or []) == 3
    )
    assert {
        part.function_response.name
        for part in function_response_event.content.parts
        if part.function_response
    } == {"sabio_repos", "sabio_comms", "sabio_irc"}


def test_real_research_wrappers_run_concurrently_and_forward_sources():
    started: set[str] = set()
    all_started = asyncio.Event()

    async def read_file(path: str) -> dict:
        return {
            "repo": "bips",
            "path": path,
            "ref": "master",
            "start_line": 1,
            "end_line": 20,
            "content": "BIP 119",
            "github_url": (
                "https://github.com/bitcoin/bips/blob/master/"
                "bip-0119.mediawiki#L1-L20"
            ),
        }

    async def get_message(message_id: str) -> dict:
        return {
            "id": message_id,
            "channel": "mailing_list",
            "author": "Example Author",
            "title": "CTV discussion",
            "posted_at": "2025-06-12T02:06:52+00:00",
            "body": "Complete mailing-list evidence.",
            "url": "https://gnusha.org/pi/bitcoindev/example/",
        }

    async def get_irc_event(event_id: str) -> dict:
        return {
            "id": event_id,
            "channel": "bitcoin-core-dev",
            "author": "example",
            "title": "BIP 119",
            "posted_at": "2025-03-07T11:22:00+00:00",
            "body": "Complete IRC evidence.",
            "url": "https://gnusha.org/bitcoin-core-dev/2025-03-07.log",
        }

    def specialist(
        name: str,
        evidence_tool,
        evidence_tool_name: str,
        evidence_tool_args: dict,
    ) -> Agent:
        model = EvidenceSpecialistLlm(
            model=f"{name}-test",
            specialist_name=name,
            evidence_tool_name=evidence_tool_name,
            evidence_tool_args=evidence_tool_args,
        )
        model.set_barrier(started, all_started)
        return Agent(
            name=name,
            model=model,
            instruction="Retrieve evidence and return a concise report.",
            tools=[evidence_tool],
        )

    async def run():
        service = InMemorySessionService()
        root = Agent(
            name="parallel_wrapper_root",
            model=ParallelSpecialistLlm(model="parallel-wrapper-test"),
            instruction="Call the required specialist tools concurrently.",
            tools=[
                ParallelResearchTool(
                    specialist(
                        "sabio_repos",
                        read_file,
                        "read_file",
                        {"path": "bip-0119.mediawiki"},
                    )
                ),
                ParallelResearchTool(
                    specialist(
                        "sabio_comms",
                        get_message,
                        "get_message",
                        {"message_id": "message:39701"},
                    )
                ),
                ParallelResearchTool(
                    specialist(
                        "sabio_irc",
                        get_irc_event,
                        "get_irc_event",
                        {"event_id": "irc_event:391796"},
                    )
                ),
            ],
        )
        runner = Runner(
            app_name="parallel-wrapper-test",
            agent=root,
            session_service=service,
        )
        session = await service.create_session(
            app_name="parallel-wrapper-test",
            user_id="test-user",
        )
        return [
            event
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=EXACT_BIP_119_PROMPT)],
                ),
            )
        ]

    events = asyncio.run(run())

    assert started == {"sabio_repos", "sabio_comms", "sabio_irc"}
    outer_result = next(
        event
        for event in events
        if event.content
        and sum(bool(part.function_response) for part in event.content.parts or []) == 3
    )
    payloads = event_payloads(outer_result)
    assert [payload["type"] for payload in payloads].count("tool_result") == 3
    assert {payload["type"] for payload in payloads} >= {
        "communication_source",
        "source",
    }
    communication_ids = {
        payload["message_id"]
        for payload in payloads
        if payload["type"] == "communication_source"
    }
    assert communication_ids == {"message:39701", "irc_event:391796"}


def test_repeated_specialist_call_in_one_turn_does_not_rerun_research():
    specialist_model = CountingSpecialistLlm(model="counting-specialist")

    async def run():
        service = InMemorySessionService()
        root = Agent(
            name="repeat_cache_root",
            model=RepeatingRootLlm(model="repeating-root"),
            instruction="Call the tool, then try it again.",
            tools=[
                ParallelResearchTool(
                    Agent(
                        name="sabio_repos",
                        model=specialist_model,
                        instruction="Return the evidence.",
                    )
                )
            ],
        )
        runner = Runner(
            app_name="repeat-cache-test",
            agent=root,
            session_service=service,
        )
        session = await service.create_session(
            app_name="repeat-cache-test",
            user_id="test-user",
        )
        return [
            event
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text="Research once.")],
                ),
            )
        ]

    events = asyncio.run(run())

    assert specialist_model.calls == 1
    responses = [
        part.function_response.response
        for event in events
        if event.content
        for part in event.content.parts or []
        if part.function_response
        and part.function_response.name == "sabio_repos"
    ]
    assert len(responses) == 2
    assert "already completed" in responses[1]["answer"]
