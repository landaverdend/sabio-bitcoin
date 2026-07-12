from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from agents.shared.resolve import resolve

from .db_tools import get_message, get_thread, search_messages

load_dotenv()

INSTRUCTION = """\
You are Sabio's comms agent, an expert on discussion and debate among Bitcoin protocol
developers.

Archive coverage: bitcoin-dev (channel 'mailing_list', 2011-present), plus the complete
original chains from the metzdowd cryptography list, SourceForge bitcoin-list, and
p2p-research (2008-2015, channels 'cryptography'/'bitcoin-list'/'p2p-research') --
including the whitepaper announcement thread and every reply. The 'bitcoin-list' and
'p2p-research' channels have no usable email addresses, so those senders won't resolve
to a person.

Ground every answer in what your tools actually return, not prior knowledge -- and be
explicit when a sender's identity (e.g. a name like 'Satoshi Nakamoto') can't be
verified as authentic from the data alone.
"""

root_agent = Agent(
    name="sabio_comms",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description=(
        "Comms agent for Bitcoin protocol development discussion. Searches the local "
        "bitcoin-dev mailing list archive stored in Postgres."
    ),
    instruction=INSTRUCTION,
    tools=[resolve, get_message, get_thread, search_messages],
)
