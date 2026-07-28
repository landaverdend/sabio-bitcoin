"""Run a specialist agent as a normal ADK tool and preserve its citations."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any

from google.adk.agents.run_config import RunConfig
from google.adk.agents.llm_agent import LlmAgent
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools._forwarding_artifact_service import ForwardingArtifactService
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from typing_extensions import override

from google.adk.utils.context_utils import Aclosing

_SOURCE_PAYLOAD_TYPES = {
    "communication_source",
    "github_discussion_source",
    "source",
    "web_source",
}
_MAX_SOURCE_PAYLOADS = 20
_MAX_SPECIALIST_LLM_CALLS = 4
_SPECIALIST_TIMEOUT_SECONDS = 75
_MAX_TRACKED_INVOCATIONS = 512
_COMPLETED_SPECIALISTS: OrderedDict[str, set[str]] = OrderedDict()

logger = logging.getLogger("sabio.research")


def _completed_specialists(invocation_id: str) -> set[str]:
    completed = _COMPLETED_SPECIALISTS.setdefault(invocation_id, set())
    _COMPLETED_SPECIALISTS.move_to_end(invocation_id)
    while len(_COMPLETED_SPECIALISTS) > _MAX_TRACKED_INVOCATIONS:
        _COMPLETED_SPECIALISTS.popitem(last=False)
    return completed


def _source_payloads(event: Any) -> list[dict]:
    # Import lazily so the agent layer does not initialize backend chat state
    # merely by being imported by scripts or tests.
    from backend.chat.events import event_payloads

    return [
        payload
        for payload in event_payloads(event)
        if payload.get("type") in _SOURCE_PAYLOAD_TYPES
    ]


def _deduplicate_sources(sources: list[dict]) -> list[dict]:
    deduplicated = []
    seen: set[str] = set()
    for source in sources:
        key = json.dumps(source, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(source)
        if len(deduplicated) >= _MAX_SOURCE_PAYLOADS:
            break
    return deduplicated


class ParallelResearchTool(AgentTool):
    """AgentTool variant that returns compact nested source-card metadata.

    ADK executes ordinary function tools from one model response concurrently.
    Wrapping each specialist this way therefore permits parallel research,
    unlike ``transfer_to_agent``, whose destination is a single event field.
    """

    @override
    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict:
        invocation_id = tool_context.invocation_id
        completed = _completed_specialists(invocation_id)
        if self.agent.name in completed:
            return {
                "answer": (
                    "This specialist already completed its research for the "
                    "current user turn. Use the earlier result and synthesize "
                    "the final answer without calling it again."
                ),
                "sources": [],
            }

        if self.skip_summarization:
            tool_context.actions.skip_summarization = True

        if isinstance(self.agent, LlmAgent) and self.agent.input_schema:
            input_value = self.agent.input_schema.model_validate(args)
            content = types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=input_value.model_dump_json(exclude_none=True)
                    )
                ],
            )
        else:
            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=args["request"])],
            )

        runner = Runner(
            app_name=self.agent.name,
            agent=self.agent,
            artifact_service=ForwardingArtifactService(tool_context),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
            credential_service=tool_context._invocation_context.credential_service,
        )
        session = await runner.session_service.create_session(
            app_name=self.agent.name,
            user_id=tool_context._invocation_context.user_id,
            state=tool_context.state.to_dict(),
        )

        last_content = None
        sources: list[dict] = []
        event_count = 0
        tool_call_count = 0
        started_at = time.perf_counter()
        timed_out = False
        logger.info(
            "specialist=%s model=%s started",
            self.agent.name,
            getattr(self.agent.model, "model", type(self.agent.model).__name__),
        )
        try:
            async with asyncio.timeout(_SPECIALIST_TIMEOUT_SECONDS):
                async with Aclosing(
                    runner.run_async(
                        user_id=session.user_id,
                        session_id=session.id,
                        new_message=content,
                        run_config=RunConfig(
                            max_llm_calls=_MAX_SPECIALIST_LLM_CALLS
                        ),
                    )
                ) as events:
                    async for event in events:
                        event_count += 1
                        if event.actions.state_delta:
                            tool_context.state.update(event.actions.state_delta)
                        if event.content:
                            last_content = event.content
                            tool_call_count += sum(
                                bool(part.function_call)
                                for part in event.content.parts or []
                            )
                        sources.extend(_source_payloads(event))
        except TimeoutError:
            timed_out = True

        answer = ""
        if last_content:
            answer = "\n".join(
                part.text for part in last_content.parts or [] if part.text
            )
        deduplicated_sources = _deduplicate_sources(sources)
        if timed_out:
            timeout_note = (
                f"Research reached its {_SPECIALIST_TIMEOUT_SECONDS}-second "
                "limit. Synthesize only from the primary sources collected "
                "below and identify any remaining gap."
            )
            answer = f"{answer}\n\n{timeout_note}".strip()
        log_completion = logger.warning if timed_out else logger.info
        log_completion(
            "specialist=%s duration_ms=%d events=%d tool_calls=%d sources=%d timed_out=%s",
            self.agent.name,
            int((time.perf_counter() - started_at) * 1000),
            event_count,
            tool_call_count,
            len(deduplicated_sources),
            timed_out,
        )
        result = {
            "answer": answer,
            "sources": deduplicated_sources,
        }
        completed.add(self.agent.name)
        return result
