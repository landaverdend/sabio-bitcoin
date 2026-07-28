from agents.comms.agent import INSTRUCTION as COMMS_INSTRUCTION
from agents.comms.agent import root_agent as comms_agent
from agents.irc.agent import INSTRUCTION as IRC_INSTRUCTION
from agents.irc.agent import root_agent as irc_agent
from agents.repos.agent import INSTRUCTION as REPOS_INSTRUCTION
from agents.repos.agent import root_agent as repos_agent
from agents.root.agent import root_agent
from agents.shared.instructions import SPECIALIST_TOOL_INSTRUCTION
from agents.shared.research_tool import ParallelResearchTool


def test_specialists_share_one_coordinator_return_contract():
    for instruction in (
        COMMS_INSTRUCTION,
        IRC_INSTRUCTION,
        REPOS_INSTRUCTION,
    ):
        assert instruction.endswith(SPECIALIST_TOOL_INSTRUCTION)
        assert instruction.count("Coordinator contract") == 1


def test_specialists_run_as_standalone_tools_without_transfer_targets():
    for agent in (comms_agent, irc_agent, repos_agent):
        assert agent.parent_agent is None
        assert agent.sub_agents == []


def test_root_exposes_specialists_as_parallel_tools_not_transfer_targets():
    research_tools = [
        tool for tool in root_agent.tools if isinstance(tool, ParallelResearchTool)
    ]

    assert {tool.name for tool in research_tools} == {
        "sabio_comms",
        "sabio_irc",
        "sabio_repos",
    }
    assert root_agent.sub_agents == []


def test_comms_agent_requires_direct_message_evidence_without_thread_detour():
    tool_names = {
        getattr(tool, "name", getattr(tool, "__name__", ""))
        for tool in comms_agent.tools
    }
    assert "get_thread" not in tool_names
    assert {"search_messages", "get_message"} <= tool_names
