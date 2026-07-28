
import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

_AGENT_NAME_PATTERN = re.compile(r"\bsabio_(?:repos|comms|irc)\b")


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
