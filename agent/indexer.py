import os
from git import Repo
from dotenv import load_dotenv

load_dotenv()

REPOS = {
    "core": os.getenv("REPO_BITCOIN_CORE"),
}


def get_commits(repo_name: str, max_count: int = 100) -> list[dict]:
    path = REPOS.get(repo_name)
    if not path:
        raise ValueError(f"No path configured for repo: {repo_name}")

    repo = Repo(path)
    commits = []
    for commit in repo.iter_commits(max_count=max_count):
        commits.append({
            "repo": repo_name,
            "sha": commit.hexsha[:12],
            "author": commit.author.name,
            "date": commit.authored_datetime.isoformat(),
            "message": commit.message.strip(),
        })
    return commits


if __name__ == "__main__":
    commits = get_commits("core", max_count=10)
    for c in commits:
        print(f"[{c['date'][:10]}] {c['sha']} {c['author']}: {c['message'][:80]}")
