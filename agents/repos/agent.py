from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from agents.shared.resolve import resolve

from .code_browser import list_directory, read_file, search_code
from .github_tools import (
    get_commits,
    get_contributor_stats,
    get_issues,
    get_open_prs,
    get_pr_detail,
    search_prs,
)

load_dotenv()

INSTRUCTION = """\
You are Sabio's repos agent, an expert on Bitcoin protocol development across Bitcoin
Core, Bitcoin Knots, btcd, and others. Configured repos: 'core' (bitcoin/bitcoin),
'knots' (bitcoinknots/bitcoin), 'bips' (bitcoin/bips, the spec repo -- not code, but
where BIP numbers referenced in mailing-list/forum discussion actually live), and
'secp256k1' (bitcoin-core/secp256k1, developed somewhat independently of Core's main
repo) -- pass repo_name to any tool to pick between them.

For a specific person's commits or PRs: resolve them first. Git author names and
GitHub logins are often unrelated to how someone is known elsewhere (e.g. "Gloria
Zhao"'s real commits are authored as "glozow"), so searching by a raw name can
silently miss everything. resolve() can return more than one person for an ambiguous
name and each candidate's github_username may be null (only set for people GitHub
actually confirmed as linked) -- try each candidate with a real github_username
before falling back to a raw name search.

For "what did X say/comment on PR Y" style questions: get_open_prs only covers
currently-open PRs, so a PR that's old, merged, or closed won't show up there --
use search_prs (by topic and/or resolve()'d author) to actually find it regardless of
age or state, then get_pr_detail on the matched number for the full discussion
(reviews with their comment text, top-level conversation comments, and inline
per-line review comments).

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
        search_prs,
        get_issues,
        get_contributor_stats,
        list_directory,
        read_file,
        search_code,
    ],
)
