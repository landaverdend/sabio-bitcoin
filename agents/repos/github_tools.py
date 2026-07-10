import os

from dotenv import load_dotenv
from github import Auth, Github

load_dotenv()

REPOS = {
    "core": os.getenv("GITHUB_REPO_CORE", "bitcoin/bitcoin"),
}

_BODY_PREVIEW_CHARS = 500


def _get_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return Github(auth=Auth.Token(token))
    return Github()


def _resolve_repo(repo_name: str):
    slug = REPOS.get(repo_name)
    if not slug:
        raise ValueError(f"No GitHub repo configured for: {repo_name}")
    return _get_client().get_repo(slug)


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) > _BODY_PREVIEW_CHARS:
        return text[:_BODY_PREVIEW_CHARS] + "..."
    return text


def get_open_prs(repo_name: str = "core", max_count: int = 20) -> list[dict]:
    """List currently open pull requests for a configured repo, newest first."""
    repo = _resolve_repo(repo_name)
    prs = []
    for pr in repo.get_pulls(state="open", sort="created", direction="desc")[:max_count]:
        prs.append({
            "number": pr.number,
            "title": pr.title,
            "author": pr.user.login if pr.user else None,
            "created_at": pr.created_at.isoformat(),
            "updated_at": pr.updated_at.isoformat(),
            "labels": [l.name for l in pr.labels],
            "draft": pr.draft,
            "url": pr.html_url,
        })
    return prs


def get_pr_detail(repo_name: str = "core", number: int = 0) -> dict:
    """Get full detail for a single pull request, including review state and diff stats."""
    repo = _resolve_repo(repo_name)
    pr = repo.get_pull(number)
    reviews = [
        {"author": r.user.login if r.user else None, "state": r.state}
        for r in pr.get_reviews()
    ]
    return {
        "number": pr.number,
        "title": pr.title,
        "author": pr.user.login if pr.user else None,
        "state": pr.state,
        "body": _truncate(pr.body),
        "created_at": pr.created_at.isoformat(),
        "updated_at": pr.updated_at.isoformat(),
        "merged": pr.merged,
        "commits": pr.commits,
        "changed_files": pr.changed_files,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "labels": [l.name for l in pr.labels],
        "reviews": reviews,
        "url": pr.html_url,
    }


def get_issues(repo_name: str = "core", state: str = "open", max_count: int = 20) -> list[dict]:
    """List issues (excluding pull requests) for a configured repo."""
    repo = _resolve_repo(repo_name)
    issues = []
    for issue in repo.get_issues(state=state, sort="created", direction="desc"):
        if issue.pull_request is not None:
            continue
        issues.append({
            "number": issue.number,
            "title": issue.title,
            "author": issue.user.login if issue.user else None,
            "created_at": issue.created_at.isoformat(),
            "comments": issue.comments,
            "labels": [l.name for l in issue.labels],
            "url": issue.html_url,
        })
        if len(issues) >= max_count:
            break
    return issues


def get_contributor_stats(repo_name: str = "core", max_count: int = 20) -> list[dict]:
    """List top contributors to a configured repo, ranked by total commit count."""
    repo = _resolve_repo(repo_name)
    stats = []
    for contributor in repo.get_contributors()[:max_count]:
        stats.append({
            "login": contributor.login,
            "contributions": contributor.contributions,
            "url": contributor.html_url,
        })
    return stats


if __name__ == "__main__":
    for pr in get_open_prs(max_count=5):
        print(f"#{pr['number']} {pr['title']} ({pr['author']})")
