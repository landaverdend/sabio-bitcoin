import os

from dotenv import load_dotenv
from github import Auth, Github

load_dotenv()

REPOS = {
    "core": "bitcoin/bitcoin",
    "knots": "bitcoinknots/bitcoin",
    "bips": "bitcoin/bips",
    "secp256k1": "bitcoin-core/secp256k1",
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


def get_commits(repo_name: str = "core", author: str | None = None, max_count: int = 100) -> list[dict]:
    """List commits, newest first. author is a GitHub login or the email a
    commit was authored with (e.g. from resolve()) -- GitHub's API matches on
    those, not an arbitrary name/pattern the way local `git log --author`
    would."""
    repo = _resolve_repo(repo_name)
    kwargs = {"author": author} if author else {}
    commits = []
    for commit in repo.get_commits(**kwargs)[:max_count]:
        git_author = commit.commit.author
        commits.append({
            "repo": repo_name,
            "sha": commit.sha[:12],
            "author": git_author.name if git_author else None,
            "email": git_author.email if git_author else None,
            "date": git_author.date.isoformat() if git_author else None,
            "message": commit.commit.message.strip(),
            "url": commit.html_url,
        })
    return commits


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
    """Get full detail for a single pull request: diff stats, every review
    (with its actual comment text, not just approve/request-changes state),
    every top-level discussion comment (the "Conversation" tab), and every
    inline review comment (left on a specific diff line)."""
    repo = _resolve_repo(repo_name)
    pr = repo.get_pull(number)
    reviews = [
        {"author": r.user.login if r.user else None, "state": r.state, "body": _truncate(r.body)}
        for r in pr.get_reviews()
    ]
    comments = [
        {
            "author": c.user.login if c.user else None,
            "body": _truncate(c.body),
            "created_at": c.created_at.isoformat(),
            "url": c.html_url,
        }
        for c in pr.get_issue_comments()
    ]
    review_comments = [
        {
            "author": c.user.login if c.user else None,
            "body": _truncate(c.body),
            "path": c.path,
            # None for a comment whose diff context has since shifted --
            # GitHub then only exposes original_line, not line.
            "line": c.line or c.original_line,
            "created_at": c.created_at.isoformat(),
            "url": c.html_url,
        }
        for c in pr.get_review_comments()
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
        "comments": comments,
        "review_comments": review_comments,
        "url": pr.html_url,
    }


def search_prs(
    repo_name: str = "core",
    query: str = "",
    author: str | None = None,
    state: str | None = None,
    max_count: int = 20,
) -> list[dict]:
    """Search pull requests by title/body text, optionally scoped to an
    author (GitHub login -- e.g. from resolve()'s github_username) and/or
    state ("open"/"closed"). Unlike get_open_prs, this finds a PR regardless
    of age or whether it's still open -- a PR relevant to some topic could
    easily be old, merged, or closed by now, and get_open_prs would never
    surface it. Pass the resulting number to get_pr_detail for the full
    discussion."""
    repo = _resolve_repo(repo_name)
    query_parts = [f"repo:{repo.full_name}", "is:pr"]
    if query:
        query_parts.append(query)
    if author:
        query_parts.append(f"author:{author}")
    if state:
        query_parts.append(f"state:{state}")
    results = _get_client().search_issues(" ".join(query_parts))

    prs = []
    for issue in results[:max_count]:
        prs.append({
            "number": issue.number,
            "title": issue.title,
            "author": issue.user.login if issue.user else None,
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat(),
            "state": issue.state,
            "url": issue.html_url,
        })
    return prs


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
