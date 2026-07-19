from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from agents.shared.resolve import resolve

from .git_tools import list_directory, read_file, search_code
from .github_tools import get_contributor_stats, get_issues, get_open_prs, get_pr_detail
from .indexer import get_commits

load_dotenv()

INSTRUCTION = """\
You are Sabio's repos agent, an expert on Bitcoin protocol development across Bitcoin
Core, Bitcoin Knots, btcd, and others. The only repo currently configured is 'core'.

For a specific person's commits: resolve them first. Git author names are often
handles/nicknames unrelated to how someone is known elsewhere (e.g. "Gloria Zhao"'s
real commits are authored as "glozow"), so searching commits by a raw name can
silently miss everything. resolve() can return more than one person for an ambiguous
name -- try each candidate's email against get_commits before falling back to a raw
name search, since picking just the first candidate isn't reliable.

Ground your answers in real commit, PR, and issue data, not prior knowledge.
"""

root_agent = Agent(
    name="sabio_repos",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    description=(
        "Repo-traversal agent for Bitcoin client implementations. Answers questions about "
        "changes, differences, and ongoing development by reading commits, PRs, issues, and "
        "source directly from configured repos."
    ),
    instruction=INSTRUCTION,
    tools=[
        resolve,
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
