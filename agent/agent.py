from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from .github_tools import get_contributor_stats, get_issues, get_open_prs, get_pr_detail
from .indexer import get_commits

load_dotenv()

root_agent = Agent(
    name="sabio",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description="Bitcoin protocol intelligence agent. Answers questions about changes, differences, and ongoing development across Bitcoin client implementations.",
    instruction=(
        "You are Sabio, an expert on Bitcoin protocol development. "
        "You help technical users understand what is happening across Bitcoin client implementations "
        "including Bitcoin Core, Bitcoin Knots, btcd, and others. "
        "You can explain commits, PRs, issues, and contributor history in plain English, "
        "and synthesize differences between implementations. "
        "The only repo currently configured is 'core' (Bitcoin Core). "
        "Use the available tools to ground your answers in real commit, PR, and issue data "
        "rather than relying on prior knowledge."
    ),
    tools=[get_commits, get_open_prs, get_pr_detail, get_issues, get_contributor_stats],
)
