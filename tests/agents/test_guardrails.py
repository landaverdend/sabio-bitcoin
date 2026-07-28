from google.genai import types

from agents.shared.guardrails import redact_agent_names, serialize_agent_transfers


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


def test_keeps_only_first_transfer_call_in_one_model_response():
    from google.adk.models.llm_response import LlmResponse

    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="transfer_to_agent",
                        args={"agent_name": "sabio_repos"},
                    )
                ),
                types.Part(
                    function_call=types.FunctionCall(
                        name="transfer_to_agent",
                        args={"agent_name": "sabio_comms"},
                    )
                ),
                types.Part(
                    function_call=types.FunctionCall(
                        name="transfer_to_agent",
                        args={"agent_name": "sabio_irc"},
                    )
                ),
            ],
        )
    )

    assert serialize_agent_transfers(None, response) is None
    calls = [
        part.function_call
        for part in response.content.parts
        if part.function_call is not None
    ]
    assert len(calls) == 1
    assert calls[0].args["agent_name"] == "sabio_repos"


def test_transfer_guard_preserves_parallel_non_transfer_tools():
    from google.adk.models.llm_response import LlmResponse

    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="search_web",
                        args={"query": "current BIP-119 status"},
                    )
                ),
                types.Part(
                    function_call=types.FunctionCall(
                        name="transfer_to_agent",
                        args={"agent_name": "sabio_repos"},
                    )
                ),
            ],
        )
    )

    serialize_agent_transfers(None, response)

    assert [part.function_call.name for part in response.content.parts] == [
        "search_web",
        "transfer_to_agent",
    ]
