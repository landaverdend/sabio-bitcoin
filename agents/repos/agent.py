from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from .fs_tools import list_directory, read_file, search_code
from .github_tools import get_contributor_stats, get_issues, get_open_prs, get_pr_detail
from .indexer import get_commits

load_dotenv()

root_agent = Agent(
    name="sabio_repos",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description="Repo-traversal agent for Bitcoin client implementations. Answers questions about changes, differences, and ongoing development by reading commits, PRs, issues, and source directly from configured repos.",
    instruction=(
        "You are Sabio's repos agent, an expert on Bitcoin protocol development. "
        "You help technical users understand what is happening across Bitcoin client implementations "
        "including Bitcoin Core, Bitcoin Knots, btcd, and others. "
        "You can explain commits, PRs, issues, and contributor history in plain English, "
        "and synthesize differences between implementations. "
        "The only repo currently configured is 'core' (Bitcoin Core). "
        "Use the available tools to ground your answers in real commit, PR, and issue data "
        "rather than relying on prior knowledge. "
        "You can also browse the actual source tree of a repo with list_directory, read_file, "
        "and search_code when a question needs the real implementation, not just metadata."
    ),
    tools=[
        get_commits,
        get_open_prs,
        get_pr_detail,
        get_issues,
        get_contributor_stats,
        list_directory,
        read_file,
        search_code,
    ],
)
