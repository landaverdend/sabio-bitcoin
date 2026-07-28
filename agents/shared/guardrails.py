
import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

_AGENT_NAME_PATTERN = re.compile(r"\bsabio_(?:repos|comms|irc)\b")


def serialize_agent_transfers(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> None:
    """Keep at most one transfer call in a model response.

    ADK executes function calls in one response concurrently and merges their
    ``EventActions``. Multiple ``transfer_to_agent`` calls therefore overwrite
    the same destination field; only the final transfer runs while every call
    still receives a misleading ``result: null`` response. Preserve the first
    requested destination and let the coordinator make any later handoffs in
    subsequent model turns.

    This mutates the response in place and deliberately returns ``None`` so
    later after-model callbacks, such as text redaction, still run.
    """
    if not llm_response.content or not llm_response.content.parts:
        return None

    transfer_seen = False
    retained_parts = []
    for part in llm_response.content.parts:
        is_transfer = (
            part.function_call is not None
            and part.function_call.name == "transfer_to_agent"
        )
        if not is_transfer:
            retained_parts.append(part)
            continue
        if transfer_seen:
            continue
        transfer_seen = True
        retained_parts.append(part)

    llm_response.content.parts = retained_parts
    return None


def redact_agent_names(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse | None:
    """after_model_callback: replace any literal internal agent name in a
    text response before it's ever yielded to the caller. Returning None
    (ADK's "unchanged" signal) when nothing matched avoids touching function
    calls or already-clean text."""
    if not llm_response.content or not llm_response.content.parts:
        return None

    changed = False
    for part in llm_response.content.parts:
        if part.text and _AGENT_NAME_PATTERN.search(part.text):
            part.text = _AGENT_NAME_PATTERN.sub("the relevant research tools", part.text)
            changed = True

    return llm_response if changed else None
