from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from .comms.agent import root_agent as comms_agent
from .repos.agent import root_agent as repos_agent

load_dotenv()

INSTRUCTION = """\
You are Sabio, the coordinator for a team of specialist agents covering Bitcoin protocol
development. Route each question to whichever specialist is best suited, and synthesize
their answers for the user.
"""

root_agent = Agent(
    name="sabio",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description="Sabio, a Bitcoin protocol intelligence assistant that coordinates specialist agents.",
    instruction=INSTRUCTION,
    sub_agents=[repos_agent, comms_agent],
)
