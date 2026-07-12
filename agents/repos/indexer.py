import os
from typing import Optional

from dotenv import load_dotenv
from git import Repo

load_dotenv()

REPOS = {
    "core": os.getenv("REPO_BITCOIN_CORE"),
}


def get_commits(repo_name: str, author: Optional[str] = None, max_count: int = 100) -> list[dict]:
    """List commits, newest first. author is an optional name/email substring
    (matches git's own --author=<pattern>) -- e.g. an email from resolve()."""
    path = REPOS.get(repo_name)
    if not path:
        raise ValueError(f"No path configured for repo: {repo_name}")

    repo = Repo(path)
    kwargs = {"max_count": max_count}
    if author:
        kwargs["author"] = author

    commits = []
    for commit in repo.iter_commits(**kwargs):
        commits.append({
            "repo": repo_name,
            "sha": commit.hexsha[:12],
            "author": commit.author.name,
            "email": commit.author.email,
            "date": commit.authored_datetime.isoformat(),
            "message": commit.message.strip(),
        })
    return commits


if __name__ == "__main__":
    commits = get_commits("core", max_count=10)
    for c in commits:
        print(f"[{c['date'][:10]}] {c['sha']} {c['author']}: {c['message'][:80]}")
