from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from .mailing_list_tools import get_message, get_recent_messages, get_thread, search_mailing_list

load_dotenv()

root_agent = Agent(
    name="sabio_comms",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description="Comms agent for Bitcoin protocol development discussion. Answers questions using the bitcoin-dev mailing list.",
    instruction=(
        "You are Sabio's comms agent, an expert on discussion and debate among Bitcoin protocol "
        "developers. You have access to the bitcoin-dev mailing list archive (mirrored at "
        "gnusha.org/pi/bitcoindev). "
        "Use search_mailing_list to find messages related to a topic, get_recent_messages to see "
        "what's currently being discussed, get_message to read one message in full, and get_thread "
        "to read an entire discussion end to end. "
        "Ground your answers in the actual message content and cite who said what, rather than "
        "relying on prior knowledge of Bitcoin development history."
    ),
    tools=[search_mailing_list, get_recent_messages, get_message, get_thread],
)
