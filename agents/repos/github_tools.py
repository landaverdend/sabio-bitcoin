import itertools
import os
import re
from datetime import date
from typing import Literal, Optional

from dotenv import load_dotenv
from github import Auth, Github

load_dotenv()

REPOS = {
    "core": "bitcoin/bitcoin",
    "knots": "bitcoinknots/bitcoin",
    "bips": "bitcoin/bips",
    "secp256k1": "bitcoin-core/secp256k1",
}

# repo_name -> repo_name it forked from. Knots rebases onto each Core release
# rather than tracking master, so nearly all of its history is Core's history
# re-authored under a different ref -- anything walking full commit history
# (e.g. scripts/link_github_contributors.py) should scope Knots to commits
# since its current divergence point, not redo Core's entire walk.
FORK_OF = {"knots": "core"}

_BODY_PREVIEW_CHARS = 500
_DISCUSSION_KINDS = (
    "pull_request",
    "conversation_comment",
    "review",
    "review_comment",
)
DiscussionKind = Literal[
    "pull_request",
    "conversation_comment",
    "review",
    "review_comment",
]


def _get_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return Github(auth=Auth.Token(token))
    return Github()


def _resolve_repo(repo_name: str):
    """Resolves a configured alias (REPOS) or, failing that, a raw "owner/repo"
    slug passed through as-is -- lets tools follow a PR onto its actual head
    repo (get_pr_detail returns head_repo/head_ref for exactly this), which is
    routinely a contributor's personal fork rather than a branch of the base
    repo: work that hasn't merged customarily lives there, not here."""
    slug = REPOS.get(repo_name) or (repo_name if "/" in repo_name else None)
    if not slug:
        raise ValueError(f"No GitHub repo configured for: {repo_name}")
    return _get_client().get_repo(slug)


def get_commits(
    repo_name: str = "core", author: Optional[str] = None, max_count: int = 100,
    oldest_first: bool = False,
) -> list[dict]:
    """List commits. author is a GitHub login or the email a commit was
    authored with (e.g. from resolve()) -- GitHub's API matches on those, not
    an arbitrary name/pattern the way local `git log --author` would.

    GitHub's API itself only ever returns commits newest-first, so this
    defaults to that; taking the last entry off a newest-first, max_count-
    limited page is NOT that author's first commit, just the oldest one
    within whatever page happened to be fetched -- for an active,
    long-tenured contributor that's still a recent commit, arbitrarily far
    from when they actually started. Pass oldest_first=True for "when did X
    start" / "first commit" questions instead: this walks from the true end
    of that author's history (via GitHub's own last-page link, not a forward
    walk through everything in between) so the oldest max_count commits
    returned are genuinely their earliest, not an artifact of pagination."""
    repo = _resolve_repo(repo_name)
    kwargs = {"author": author} if author else {}
    result = repo.get_commits(**kwargs)
    # PyGithub's PaginatedList.__getitem__ raises IndexError on a slice when
    # the result is empty (e.g. an author with zero matching commits), so
    # result[:max_count] isn't safe here -- islice has no such edge case.
    page = (
        list(reversed(result))[:max_count]
        if oldest_first
        else list(itertools.islice(result, max_count))
    )

    commits = []
    for commit in page:
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


def _iso_date(value: str, field_name: str) -> str:
    """Validate a date before placing it in a GitHub search qualifier."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date (YYYY-MM-DD)") from exc


def _discussion_terms(query: str) -> list[str]:
    return re.findall(r"[\w+#.-]+", query.casefold())


def _discussion_excerpt(body: str | None, terms: list[str]) -> str:
    """Return a compact excerpt centered on the first matching search term."""
    text = " ".join((body or "").split())
    if len(text) <= _BODY_PREVIEW_CHARS:
        return text

    folded = text.casefold()
    positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
    match_at = min(positions) if positions else 0
    start = max(0, match_at - 140)
    end = min(len(text), start + _BODY_PREVIEW_CHARS)
    if end - start < _BODY_PREVIEW_CHARS:
        start = max(0, end - _BODY_PREVIEW_CHARS)
    return (
        ("..." if start else "")
        + text[start:end]
        + ("..." if end < len(text) else "")
    )


def _matches_discussion(
    body: str | None,
    terms: list[str],
    author: str | None,
    commenter: str | None,
) -> tuple[bool, int]:
    if commenter and (author or "").casefold() != commenter.casefold():
        return False, 0
    folded = (body or "").casefold()
    if terms and not all(term in folded for term in terms):
        return False, 0
    return True, sum(folded.count(term) for term in terms)


def _discussion_base(pr, kind: DiscussionKind, item_id: int, body: str | None) -> dict:
    return {
        "repo": pr.base.repo.full_name,
        "pr_number": pr.number,
        "pr_title": pr.title,
        "kind": kind,
        "id": item_id,
        "body": body or "",
    }


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
    """Get a compact overview of one pull request: diff stats and previews of
    its reviews, Conversation-tab comments, and inline review comments.
    Use search_pr_discussion plus get_pr_discussion_item when exact,
    untruncated discussion text is needed as evidence."""
    repo = _resolve_repo(repo_name)
    pr = repo.get_pull(number)
    reviews = [
        {
            "id": r.id,
            "author": r.user.login if r.user else None,
            "state": r.state,
            "body": _truncate(r.body),
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "url": getattr(r, "html_url", None) or pr.html_url,
        }
        for r in pr.get_reviews()
    ]
    comments = [
        {
            "id": c.id,
            "author": c.user.login if c.user else None,
            "body": _truncate(c.body),
            "created_at": c.created_at.isoformat(),
            "url": c.html_url,
        }
        for c in pr.get_issue_comments()
    ]
    review_comments = [
        {
            "id": c.id,
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
        # Where the proposed code actually lives -- often a contributor's own
        # fork, not a branch of repo_name itself (merged=False means none of
        # this exists on the default branch yet). Pass these straight through
        # as read_file/list_directory's repo_name/ref to read it directly:
        # _resolve_repo accepts a raw "owner/repo" slug, not just the four
        # configured aliases, for exactly this.
        "head_repo": pr.head.repo.full_name if pr.head.repo else None,
        "head_ref": pr.head.ref,
    }


def search_prs(
    repo_name: str = "core",
    query: str = "",
    author: Optional[str] = None,
    state: Optional[str] = None,
    search_in: Literal["all", "title", "body", "comments"] = "all",
    commenter: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    merged: Optional[bool] = None,
    created_after: Optional[str] = None,
    updated_after: Optional[str] = None,
    max_count: int = 20,
) -> list[dict]:
    """Search pull requests using GitHub's PR-level search index.

    search_in can restrict text matches to a PR's title, body, or comments.
    commenter finds PRs a GitHub user commented on; reviewed_by finds PRs
    they reviewed. Discovery results identify matching PRs but do not identify
    the exact matching comment. Follow with search_pr_discussion, then
    get_pr_discussion_item before quoting or making a claim about a comment.
    """
    repo = _resolve_repo(repo_name)
    query_parts = [f"repo:{repo.full_name}", "is:pr"]
    if query:
        query_parts.append(query)
    if search_in not in ("all", "title", "body", "comments"):
        raise ValueError("search_in must be one of: all, title, body, comments")
    if search_in != "all":
        query_parts.append(f"in:{search_in}")
    if author:
        query_parts.append(f"author:{author}")
    if commenter:
        query_parts.append(f"commenter:{commenter}")
    if reviewed_by:
        query_parts.append(f"reviewed-by:{reviewed_by}")
    if state in ("open", "closed"):
        query_parts.append(f"state:{state}")
    if merged is not None:
        query_parts.append("is:merged" if merged else "is:unmerged")
    if created_after:
        query_parts.append(f"created:>={_iso_date(created_after, 'created_after')}")
    if updated_after:
        query_parts.append(f"updated:>={_iso_date(updated_after, 'updated_after')}")
    results = _get_client().search_issues(" ".join(query_parts))

    prs = []
    for issue in results:
        if len(prs) >= max_count:
            break
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


def search_pr_discussion(
    repo_name: str = "core",
    number: int = 0,
    query: str = "",
    commenter: Optional[str] = None,
    include_conversation: bool = True,
    include_reviews: bool = True,
    include_inline: bool = True,
    max_count: int = 20,
) -> list[dict]:
    """Search the actual discussion attached to one pull request.

    Unlike search_prs, this returns the exact matching PR body, conversation
    comments, review summaries, and inline review comments. Results contain
    compact excerpts for discovery. Call get_pr_discussion_item with a
    result's kind and id to retrieve the full, citable text.
    """
    repo = _resolve_repo(repo_name)
    pr = repo.get_pull(number)
    terms = _discussion_terms(query)
    results: list[dict] = []

    def append_result(item: dict, author: str | None) -> None:
        matches, score = _matches_discussion(item["body"], terms, author, commenter)
        if not matches:
            return
        item["author"] = author
        item["excerpt"] = _discussion_excerpt(item.pop("body"), terms)
        item["score"] = score
        results.append(item)

    if include_conversation:
        body_item = _discussion_base(pr, "pull_request", pr.number, pr.body)
        body_item.update({
            "created_at": pr.created_at.isoformat(),
            "url": pr.html_url,
        })
        append_result(body_item, pr.user.login if pr.user else None)
        for comment in pr.get_issue_comments():
            item = _discussion_base(
                pr, "conversation_comment", comment.id, comment.body
            )
            item.update({
                "created_at": comment.created_at.isoformat(),
                "url": comment.html_url,
            })
            append_result(item, comment.user.login if comment.user else None)

    if include_reviews:
        for review in pr.get_reviews():
            item = _discussion_base(pr, "review", review.id, review.body)
            item.update({
                "state": review.state,
                "created_at": (
                    review.submitted_at.isoformat() if review.submitted_at else None
                ),
                "url": getattr(review, "html_url", None) or pr.html_url,
            })
            append_result(item, review.user.login if review.user else None)

    if include_inline:
        for comment in pr.get_review_comments():
            item = _discussion_base(
                pr, "review_comment", comment.id, comment.body
            )
            item.update({
                "path": comment.path,
                "line": comment.line or comment.original_line,
                "created_at": comment.created_at.isoformat(),
                "url": comment.html_url,
            })
            append_result(item, comment.user.login if comment.user else None)

    results.sort(
        key=lambda item: (item["score"], item.get("created_at") or ""),
        reverse=True,
    )
    return results[:max(0, max_count)]


def _ensure_discussion_item_belongs_to_pr(item, number: int, kind: DiscussionKind) -> None:
    if kind == "conversation_comment":
        parent_url = getattr(item, "issue_url", "")
        marker = f"/issues/{number}"
    else:
        parent_url = getattr(item, "pull_request_url", "")
        marker = f"/pulls/{number}"
    if parent_url and marker not in parent_url:
        raise ValueError(f"{kind} {item.id} does not belong to PR #{number}")


def get_pr_discussion_item(
    repo_name: str = "core",
    number: int = 0,
    kind: DiscussionKind = "conversation_comment",
    item_id: int = 0,
) -> dict:
    """Retrieve one exact, untruncated PR discussion item for evidence.

    Use the kind and id returned by search_pr_discussion. This is the
    authoritative read step for quoting a PR body, conversation comment,
    review summary, or inline review comment.
    """
    if kind not in _DISCUSSION_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(_DISCUSSION_KINDS)}")

    repo = _resolve_repo(repo_name)
    pr = repo.get_pull(number)
    if kind == "pull_request":
        if item_id not in (0, pr.number):
            raise ValueError(f"pull_request item_id must be {pr.number}")
        item = _discussion_base(pr, kind, pr.number, pr.body)
        item.update({
            "author": pr.user.login if pr.user else None,
            "created_at": pr.created_at.isoformat(),
            "updated_at": pr.updated_at.isoformat(),
            "url": pr.html_url,
        })
        return item

    if item_id <= 0:
        raise ValueError("item_id must be the positive id from search_pr_discussion")

    if kind == "conversation_comment":
        comment = pr.get_issue_comment(item_id)
        _ensure_discussion_item_belongs_to_pr(comment, number, kind)
        item = _discussion_base(pr, kind, comment.id, comment.body)
        item.update({
            "author": comment.user.login if comment.user else None,
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat(),
            "url": comment.html_url,
        })
        return item

    if kind == "review":
        review = pr.get_review(item_id)
        item = _discussion_base(pr, kind, review.id, review.body)
        item.update({
            "author": review.user.login if review.user else None,
            "state": review.state,
            "created_at": (
                review.submitted_at.isoformat() if review.submitted_at else None
            ),
            "url": getattr(review, "html_url", None) or pr.html_url,
        })
        return item

    comment = pr.get_review_comment(item_id)
    _ensure_discussion_item_belongs_to_pr(comment, number, kind)
    item = _discussion_base(pr, kind, comment.id, comment.body)
    item.update({
        "author": comment.user.login if comment.user else None,
        "path": comment.path,
        "line": comment.line or comment.original_line,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
        "url": comment.html_url,
    })
    return item


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
