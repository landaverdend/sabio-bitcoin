"""Repo-backed endpoints -- file tree, file content, blame, commits/branches/
authors all live under this one router, since they all resolve a repo_name
to a GitHub slug the same way and hit the GitHub API the same way.

No local clone anywhere: everything goes through GitHub's REST API (via
PyGithub, reusing agents/repos/github_tools.py's client/REPOS) except blame
and cheap total-commit-counts, which have no REST equivalent -- those use
GitHub's GraphQL API directly (PyGithub is REST-only, so this is a raw HTTP
client, not a new SDK dependency).
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime

from fastapi import APIRouter, HTTPException
from github import GithubException

from agents.repos.github_tools import REPOS, _get_client, _resolve_repo

router = APIRouter(prefix="/repo", tags=["repo"])

FILE_SIZE_CAP = 2_000_000  # generous for any real source file; guards
# against something pathological rather than a limit anyone should ever hit.
BINARY_SNIFF_BYTES = 8000
COMMITS_PAGE_SIZE = 30  # matches GitHub's own commit-history page size

_GRAPHQL_URL = "https://api.github.com/graphql"


def _graphql(query: str, variables: dict) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN required for this endpoint")
    req = urllib.request.Request(
        _GRAPHQL_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=exc.read().decode()) from exc
    if payload.get("errors"):
        raise HTTPException(status_code=404, detail=payload["errors"][0]["message"])
    return payload["data"]


def _slug(repo_name: str) -> tuple[str, str]:
    slug = REPOS.get(repo_name)
    if not slug:
        raise HTTPException(status_code=404, detail=f"no repo configured: {repo_name}")
    owner, name = slug.split("/", 1)
    return owner, name


def _resolve_ref(repo, ref: str) -> str:
    """"HEAD" (this project's old local-clone convention for "whatever's
    checked out") maps to the repo's actual default branch -- GitHub's API
    has no concept of a bare "HEAD" the way local git does."""
    return repo.default_branch if ref == "HEAD" else ref


@router.get("/tree")
def get_tree(repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Flat file/directory listing for a repo at a given ref (branch, tag, or
    commit sha), via the Git Trees API in recursive mode."""
    repo = _resolve_repo(repo_name)
    resolved_ref = _resolve_ref(repo, ref)
    try:
        tree = repo.get_git_tree(resolved_ref, recursive=True)
    except GithubException as exc:
        raise HTTPException(status_code=404, detail=f"ref not found: {ref}") from exc

    entries = [{"path": el.path, "type": el.type} for el in tree.tree]
    return {"repo": repo_name, "ref": ref, "entries": entries}


@router.get("/file")
def get_file(path: str, repo_name: str = "core", ref: str = "HEAD") -> dict:
    """File content at a given ref, via the Contents API. Binary files return
    content=None rather than mangled bytes. Files over ~1MB aren't readable
    this way -- GitHub's Contents API doesn't serve them."""
    repo = _resolve_repo(repo_name)
    resolved_ref = _resolve_ref(repo, ref)
    try:
        content_file = repo.get_contents(path, ref=resolved_ref)
    except GithubException as exc:
        raise HTTPException(status_code=404, detail=f"file not found: {path}@{ref}") from exc

    if isinstance(content_file, list):
        raise HTTPException(status_code=400, detail=f"not a file: {path}")

    raw = content_file.decoded_content
    if b"\x00" in raw[:BINARY_SNIFF_BYTES]:
        return {"repo": repo_name, "ref": ref, "path": path, "content": None, "binary": True}

    content = raw[:FILE_SIZE_CAP].decode("utf-8", errors="replace")
    return {"repo": repo_name, "ref": ref, "path": path, "content": content, "binary": False}


_BLAME_QUERY = """
query($owner: String!, $name: String!, $expression: String!, $path: String!) {
  repository(owner: $owner, name: $name) {
    object(expression: $expression) {
      ... on Commit {
        blame(path: $path) {
          ranges {
            startingLine
            endingLine
            commit {
              oid
              message
              committedDate
              author { name }
            }
          }
        }
      }
    }
  }
}
"""


@router.get("/blame")
def get_blame(path: str, repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Per-line blame (commit, author, date, commit summary) for a file at a
    given ref. No REST endpoint for this exists -- GitHub only exposes blame
    via GraphQL, so this bypasses PyGithub (REST-only) with a direct query."""
    owner, name = _slug(repo_name)
    data = _graphql(_BLAME_QUERY, {"owner": owner, "name": name, "expression": ref, "path": path})
    obj = (data.get("repository") or {}).get("object")
    if obj is None or "blame" not in obj:
        raise HTTPException(status_code=404, detail=f"file not found: {path}@{ref}")

    lines = []
    for rng in obj["blame"]["ranges"]:
        commit = rng["commit"]
        summary = (commit["message"] or "").splitlines()[0] if commit["message"] else ""
        for line_no in range(rng["startingLine"], rng["endingLine"] + 1):
            lines.append({
                "line": line_no,
                "sha": commit["oid"][:12],
                "author": (commit["author"] or {}).get("name", ""),
                "date": commit["committedDate"],
                "summary": summary,
            })
    return {"repo": repo_name, "ref": ref, "path": path, "lines": lines}


_SUMMARY_QUERY = """
query($owner: String!, $name: String!, $expression: String!) {
  repository(owner: $owner, name: $name) {
    object(expression: $expression) {
      ... on Commit {
        oid
        message
        committedDate
        author { name }
        history { totalCount }
      }
    }
  }
}
"""


@router.get("/summary")
def get_summary(repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Branch name, latest commit, and total commit count -- for a GitHub-style
    header bar above the file tree/viewer. Uses GraphQL: REST has no cheap way
    to get a total commit count without paginating through every commit."""
    repo = _resolve_repo(repo_name)
    resolved_ref = _resolve_ref(repo, ref)
    owner, name = _slug(repo_name)
    data = _graphql(_SUMMARY_QUERY, {"owner": owner, "name": name, "expression": resolved_ref})
    obj = (data.get("repository") or {}).get("object")
    if obj is None:
        raise HTTPException(status_code=404, detail=f"ref not found: {ref}")

    return {
        "repo": repo_name,
        "ref": ref,
        "branch": resolved_ref,
        "commit_count": obj["history"]["totalCount"],
        "latest_commit": {
            "sha": obj["oid"],
            "short_sha": obj["oid"][:7],
            "author": (obj["author"] or {}).get("name", ""),
            "date": obj["committedDate"],
            "message": (obj["message"] or "").strip(),
        },
    }


_BRANCHES_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name }
    refs(refPrefix: "refs/heads/", first: 100) {
      nodes {
        name
        target {
          ... on Commit { oid committedDate }
        }
      }
    }
  }
}
"""


@router.get("/branches")
def get_branches(repo_name: str = "core") -> dict:
    """All branches, most recently updated first -- backs the branch-switcher
    dropdown. Capped at 100 branches (GraphQL page size) -- generous for any
    real repo's active branch count."""
    owner, name = _slug(repo_name)
    data = _graphql(_BRANCHES_QUERY, {"owner": owner, "name": name})
    repo_data = data["repository"]
    default_name = (repo_data.get("defaultBranchRef") or {}).get("name")

    branches = []
    for node in repo_data["refs"]["nodes"]:
        target = node.get("target") or {}
        sha = target.get("oid", "")
        branches.append({
            "name": node["name"],
            "ref": node["name"],
            "sha": sha,
            "short_sha": sha[:7],
            "date": target.get("committedDate"),
            "is_default": node["name"] == default_name,
        })
    branches.sort(key=lambda b: b["date"] or "", reverse=True)
    return {"repo": repo_name, "branches": branches}


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_COUNT_QUERY = """
query($owner: String!, $name: String!, $expression: String!, $since: GitTimestamp, $until: GitTimestamp) {
  repository(owner: $owner, name: $name) {
    object(expression: $expression) {
      ... on Commit { history(since: $since, until: $until) { totalCount } }
    }
  }
}
"""


def _format_commit(commit) -> dict:
    git_author = commit.commit.author
    return {
        "sha": commit.sha,
        "short_sha": commit.sha[:7],
        "author": git_author.name if git_author else "",
        "date": git_author.date.isoformat() if git_author else None,
        "message": commit.commit.message.strip(),
    }


@router.get("/commits")
def get_commits(
    repo_name: str = "core",
    ref: str = "HEAD",
    page: int = 1,
    author: str | None = None,
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
) -> dict:
    """Paginated commit history for a ref, newest first. author is a GitHub
    login or commit email (exact match -- a real behavior change from the
    old local-git version, which matched a raw name against git's --author
    regex). since/until are "YYYY-MM-DD" dates forming an inclusive range.
    q searches commit messages via GitHub's commit search (a separate,
    rate-limited index) rather than REST's commit listing, which has no
    message-search parameter at all -- when q is given, the other filters
    fold into that same search query instead of REST's since/until/author
    params."""
    repo = _resolve_repo(repo_name)
    resolved_ref = _resolve_ref(repo, ref)
    page = max(1, page)

    for label, value in (("since", since), ("until", until)):
        if value is not None and not _ISO_DATE_RE.match(value):
            raise HTTPException(status_code=400, detail=f"invalid {label} date: {value}")

    owner, name = _slug(repo_name)

    if q:
        query_parts = [q, f"repo:{owner}/{name}"]
        if author:
            query_parts.append(f"author:{author}")
        if since:
            query_parts.append(f"committer-date:>={since}")
        if until:
            query_parts.append(f"committer-date:<={until}")
        results = _get_client().search_commits(" ".join(query_parts))
        total = results.totalCount
        commits = [_format_commit(c) for c in results.get_page(page - 1)]
    else:
        kwargs = {"sha": resolved_ref}
        if author:
            kwargs["author"] = author
        if since:
            kwargs["since"] = datetime.fromisoformat(since)
        if until:
            kwargs["until"] = datetime.fromisoformat(until)
        try:
            paginated = repo.get_commits(**kwargs)
            commits = [_format_commit(c) for c in paginated.get_page(page - 1)]
        except GithubException as exc:
            raise HTTPException(status_code=404, detail=f"ref not found: {ref}") from exc

        # Cheap total count via GraphQL history() -- avoids paginating
        # through the whole history just to count it, which REST would need.
        # since/until must be passed here too, or this would count the
        # *unfiltered* history instead of matching what was actually paged.
        count_vars = {"owner": owner, "name": name, "expression": resolved_ref}
        if since:
            count_vars["since"] = f"{since}T00:00:00Z"
        if until:
            count_vars["until"] = f"{until}T23:59:59Z"
        data = _graphql(_COUNT_QUERY, count_vars)
        obj = (data.get("repository") or {}).get("object") or {}
        total = obj.get("history", {}).get("totalCount", len(commits))

    return {
        "repo": repo_name,
        "ref": ref,
        "page": page,
        "page_size": COMMITS_PAGE_SIZE,
        "total": total,
        "author": author,
        "since": since,
        "until": until,
        "q": q,
        "commits": commits,
    }


@router.get("/authors")
def get_authors(repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Top contributors by commit count -- backs the "filter by user" picker
    on the commits page. Repo-wide (all branches), by GitHub login -- unlike
    the old local-git version this isn't scoped to a specific ref, since
    there's no cheap REST/GraphQL equivalent of `git shortlog -sn <ref>`."""
    repo = _resolve_repo(repo_name)
    authors = [{"name": c.login, "commit_count": c.contributions} for c in repo.get_contributors()]
    return {"repo": repo_name, "ref": ref, "authors": authors}


@router.get("/commit")
def get_commit(sha: str, repo_name: str = "core") -> dict:
    """Full detail for a single commit -- message, parent(s), and per-file
    change stats -- for a GitHub-style commit detail page."""
    repo = _resolve_repo(repo_name)
    try:
        commit = repo.get_commit(sha)
    except GithubException as exc:
        raise HTTPException(status_code=404, detail=f"commit not found: {sha}") from exc

    git_author = commit.commit.author
    files = [
        {
            "path": f.filename,
            "old_path": f.previous_filename,
            "status": f.status,
            "additions": f.additions,
            "deletions": f.deletions,
        }
        for f in commit.files
    ]
    parents = [p.sha for p in commit.parents]

    return {
        "repo": repo_name,
        "sha": commit.sha,
        "short_sha": commit.sha[:7],
        "author": git_author.name if git_author else "",
        "date": git_author.date.isoformat() if git_author else None,
        "message": commit.commit.message.strip(),
        "parents": parents,
        "parent_short": parents[0][:7] if parents else None,
        "files": files,
    }
