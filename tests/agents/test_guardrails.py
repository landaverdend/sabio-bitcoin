from google.genai import types

from agents.shared.guardrails import coalesce_specialist_calls, redact_agent_names


def _response(*texts: str):
    from google.adk.models.llm_response import LlmResponse

    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=text) for text in texts],
        )
    )


def test_redacts_internal_agent_names_from_text():
    response = _response("I'll hand this off to sabio_repos to check.")

    altered = redact_agent_names(None, response)

    assert altered is not None
    assert "sabio_repos" not in altered.content.parts[0].text
    assert "the relevant research tools" in altered.content.parts[0].text


def test_redacts_every_known_agent_name():
    response = _response("Ask sabio_comms or sabio_irc for that.")

    altered = redact_agent_names(None, response)

    assert altered is not None
    text = altered.content.parts[0].text
    assert "sabio_comms" not in text
    assert "sabio_irc" not in text


def test_leaves_clean_text_unchanged():
    response = _response("Bitcoin Core merged this in PR #12345.")

    assert redact_agent_names(None, response) is None


def test_does_not_false_positive_on_a_longer_word():
    response = _response("The sabio_repository setting is unrelated.")

    assert redact_agent_names(None, response) is None


def test_leaves_function_call_parts_untouched():
    from google.adk.models.llm_response import LlmResponse

    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="resolve", args={}))],
        )
    )

    assert redact_agent_names(None, response) is None


def test_handles_response_with_no_content():
    from google.adk.models.llm_response import LlmResponse

    assert redact_agent_names(None, LlmResponse()) is None


def test_coalesces_duplicate_calls_to_one_specialist():
    from google.adk.models.llm_response import LlmResponse

    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="sabio_repos",
                        args={"request": "Check Bitcoin Core."},
                    )
                ),
                types.Part(
                    function_call=types.FunctionCall(
                        name="sabio_repos",
                        args={"request": "Check Bitcoin Knots."},
                    )
                ),
            ],
        )
    )

    assert coalesce_specialist_calls(None, response) is None
    assert len(response.content.parts) == 1
    request = response.content.parts[0].function_call.args["request"]
    assert "Check Bitcoin Core." in request
    assert "Check Bitcoin Knots." in request
    assert "Additional scope:" in request


def test_coalescer_preserves_parallel_specialists_and_other_tools():
    from google.adk.models.llm_response import LlmResponse

    names = ["now", "sabio_repos", "sabio_comms", "sabio_irc", "search_web"]
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name=name,
                        args={"request": name},
                    )
                )
                for name in names
            ],
        )
    )

    assert coalesce_specialist_calls(None, response) is None
    assert [
        part.function_call.name for part in response.content.parts
    ] == names


def test_coalescer_drops_unrequested_irc_for_explicit_archive_scope():
    from types import SimpleNamespace

    from google.adk.models.llm_response import LlmResponse

    callback_context = SimpleNamespace(
        user_content=types.Content(
            role="user",
            parts=[
                types.Part(
                    text="¿Qué dice la lista de correo o BitcoinTalk sobre BIP-119?"
                )
            ],
        )
    )
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(name=name, args={})
                )
                for name in ("sabio_repos", "sabio_comms", "sabio_irc")
            ],
        )
    )

    assert coalesce_specialist_calls(callback_context, response) is None
    assert [
        part.function_call.name for part in response.content.parts
    ] == ["sabio_repos", "sabio_comms"]


def test_coalescer_keeps_irc_when_user_explicitly_requests_it():
    from types import SimpleNamespace

    from google.adk.models.llm_response import LlmResponse

    callback_context = SimpleNamespace(
        user_content=types.Content(
            role="user",
            parts=[
                types.Part(
                    text="Busca la lista de correo y los logs IRC de Gnusha."
                )
            ],
        )
    )
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="sabio_irc", args={"request": "Search IRC."}
                    )
                )
            ],
        )
    )

    assert coalesce_specialist_calls(callback_context, response) is None
    assert response.content.parts[0].function_call.name == "sabio_irc"
