from agents.comms.agent import INSTRUCTION as COMMS_INSTRUCTION
from agents.comms.agent import root_agent as comms_agent
from agents.irc.agent import INSTRUCTION as IRC_INSTRUCTION
from agents.irc.agent import root_agent as irc_agent
from agents.repos.agent import INSTRUCTION as REPOS_INSTRUCTION
from agents.repos.agent import root_agent as repos_agent
from agents.shared.instructions import COORDINATOR_RETURN_INSTRUCTION


def test_specialists_share_one_coordinator_return_contract():
    for instruction in (
        COMMS_INSTRUCTION,
        IRC_INSTRUCTION,
        REPOS_INSTRUCTION,
    ):
        assert instruction.endswith(COORDINATOR_RETURN_INSTRUCTION)
        assert instruction.count("Coordinator contract") == 1


def test_specialists_can_only_return_to_the_coordinator():
    for agent in (comms_agent, irc_agent, repos_agent):
        assert agent.disallow_transfer_to_peers is True
        assert agent.disallow_transfer_to_parent is False
