from agents.root.agent import INSTRUCTION

NORMALIZED_INSTRUCTION = " ".join(INSTRUCTION.split())


def test_external_project_research_uses_web_and_archives_in_the_same_turn():
    assert "Use search_web as a complementary research tool" in NORMALIZED_INSTRUCTION
    assert "use the web early when necessary" in NORMALIZED_INSTRUCTION
    assert "Use useful discovered names and terms" in NORMALIZED_INSTRUCTION
    assert "Neither evidence path replaces the other" in NORMALIZED_INSTRUCTION
    assert "Do not call it mechanically" in NORMALIZED_INSTRUCTION


def test_research_does_not_stall_for_user_supplied_disambiguators():
    assert "Do not ask the user for a URL" in NORMALIZED_INSTRUCTION
    assert "before trying the available tools" in NORMALIZED_INSTRUCTION
    assert "Research requests authorize research now" in NORMALIZED_INSTRUCTION
    assert "Do not respond with a plan" in NORMALIZED_INSTRUCTION


def test_user_claims_are_verified_as_leads():
    assert (
        "A factual assertion from the user is a lead to verify"
        in NORMALIZED_INSTRUCTION
    )
    assert "current affiliation claim in the question" in NORMALIZED_INSTRUCTION


def test_multi_source_research_serializes_agent_transfers_and_retries():
    assert "Agent transfers are strictly sequential" in NORMALIZED_INSTRUCTION
    assert (
        "Never emit more than one transfer_to_agent call"
        in NORMALIZED_INSTRUCTION
    )
    assert "A null transfer response is control-flow bookkeeping" in NORMALIZED_INSTRUCTION
    assert "never tell the user to rerun the query" in NORMALIZED_INSTRUCTION
