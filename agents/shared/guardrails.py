
import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

_AGENT_NAME_PATTERN = re.compile(r"\bsabio_(?:repos|comms|irc)\b")
_SPECIALIST_TOOL_NAMES = {"sabio_repos", "sabio_comms", "sabio_irc"}
_ARCHIVE_SCOPE_TERMS = (
    "mailing list",
    "lista de correo",
    "bitcointalk",
    "forum",
    "foro",
)
_IRC_SCOPE_TERMS = (
    " irc",
    "irc ",
    "gnusha",
    "#bitcoin-core",
    "pr review club",
)
def _user_requested_archive_without_irc(
    callback_context: CallbackContext | None,
) -> bool:
    user_content = (
        callback_context.user_content if callback_context is not None else None
    )
    if not user_content or not user_content.parts:
        return False
    text = " ".join(part.text or "" for part in user_content.parts).lower()
    return (
        any(term in text for term in _ARCHIVE_SCOPE_TERMS)
        and not any(term in text for term in _IRC_SCOPE_TERMS)
    )


def coalesce_specialist_calls(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> None:
    """Keep one parallel tool call per specialist in a model response.

    A model may split one evidence domain into multiple calls (for example, one
    repository request for Core and another for Knots). The same specialist
    agent must not be run concurrently against itself. Merge those scopes into
    its first call while leaving different specialists and non-specialist tools
    untouched.
    """
    if not llm_response.content or not llm_response.content.parts:
        return None

    first_call_by_name = {}
    retained_parts = []
    exclude_unrequested_irc = _user_requested_archive_without_irc(
        callback_context
    )
    for part in llm_response.content.parts:
        function_call = part.function_call
        if not function_call or function_call.name not in _SPECIALIST_TOOL_NAMES:
            retained_parts.append(part)
            continue
        if function_call.name == "sabio_irc" and exclude_unrequested_irc:
            continue

        first_call = first_call_by_name.get(function_call.name)
        if first_call is None:
            first_call_by_name[function_call.name] = function_call
            retained_parts.append(part)
            continue

        first_args = dict(first_call.args or {})
        duplicate_args = dict(function_call.args or {})
        first_request = str(first_args.get("request", "")).strip()
        duplicate_request = str(duplicate_args.get("request", "")).strip()
        if duplicate_request and duplicate_request not in first_request:
            separator = "\n\nAdditional scope:\n" if first_request else ""
            first_args["request"] = (
                f"{first_request}{separator}{duplicate_request}"
            )
            first_call.args = first_args

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
