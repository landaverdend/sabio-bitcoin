"""Repo/git-backed endpoints -- file tree, file content, and (later) commits/
branches all live under this one router, since they all resolve a repo_name
to a path the same way and read git's object database the same way.

Reads always go through git's object database (git ls-tree / show), never
the working directory -- this is safe to call concurrently regardless of
what's checked out on disk, and scoped by ref rather than "whatever HEAD
happens to be right now."
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from git import Repo

from agents.repos.indexer import REPOS

router = APIRouter(prefix="/repo", tags=["repo"])

# Matches git's own binary-detection heuristic (same one `git diff`/`git grep`
# use): a NUL byte anywhere in the first chunk means treat the blob as binary
# rather than trying to decode it as text. Verified against a real binary
# (doc/bitcoin_logo_doxygen.png) and a real text file (src/validation.cpp) in
# this repo -- GitPython's `git show` silently mangles binary content into
# garbage text instead of raising, so this has to be checked explicitly.
BINARY_SNIFF_BYTES = 8000
FILE_SIZE_CAP = 2_000_000  # generous for any real source file here; guards
# against something pathological rather than a limit anyone should ever hit.


def _get_repo(repo_name: str) -> Repo:
    path = REPOS.get(repo_name)
    if not path:
        raise HTTPException(status_code=404, detail=f"no repo configured: {repo_name}")
    return Repo(path)


@router.get("/tree")
def get_tree(repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Flat file/directory listing for a repo at a given ref. Uses git's fast
    plumbing path (ls-tree shelling out to real git) rather than GitPython's
    object-walking API, which matters at this repo's size (~3k files)."""
    repo = _get_repo(repo_name)
    try:
        raw = repo.git.ls_tree("-r", "-t", ref)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"ref not found: {ref}") from exc

    entries = []
    for line in raw.splitlines():
        meta, path = line.split("\t", 1)
        _mode, obj_type, _sha = meta.split(" ")
        entries.append({"path": path, "type": obj_type})

    return {"repo": repo_name, "ref": ref, "entries": entries}


@router.get("/file")
def get_file(path: str, repo_name: str = "core", ref: str = "HEAD") -> dict:
    """File content at a given ref, read via git's object database (never the
    working directory) -- same rationale as /tree. Binary files return
    content=None rather than mangled bytes."""
    repo = _get_repo(repo_name)
    try:
        blob = repo.commit(ref).tree / path
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"file not found: {path}@{ref}") from exc

    raw = blob.data_stream.read()
    if b"\x00" in raw[:BINARY_SNIFF_BYTES]:
        return {"repo": repo_name, "ref": ref, "path": path, "content": None, "binary": True}

    content = raw[:FILE_SIZE_CAP].decode("utf-8", errors="replace")
    return {"repo": repo_name, "ref": ref, "path": path, "content": content, "binary": False}


# Header line of a `git blame --line-porcelain` entry: <40-hex-char sha> <orig-line> <final-line> [<group-size>]
_BLAME_HEADER_RE = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)")


def _parse_blame(raw: str) -> list[dict]:
    """Parse `git blame --line-porcelain` output. line-porcelain (vs. plain
    porcelain) repeats full commit info for every line rather than only the
    first time a commit appears, so each line's entry is self-contained --
    no need to track a commit cache across the output."""
    entries = []
    current: dict = {}
    for line in raw.split("\n"):
        header = _BLAME_HEADER_RE.match(line)
        if header:
            current = {"sha": header.group(1), "final_line": int(header.group(2))}
        elif line.startswith("author "):
            current["author"] = line[len("author "):]
        elif line.startswith("author-time "):
            current["author_time"] = int(line[len("author-time "):])
        elif line.startswith("summary "):
            current["summary"] = line[len("summary "):]
        elif line.startswith("\t"):
            author_time = current.get("author_time")
            entries.append({
                "line": current["final_line"],
                "sha": current["sha"][:12],
                "author": current.get("author", ""),
                "date": (
                    datetime.fromtimestamp(author_time, tz=timezone.utc).isoformat()
                    if author_time else None
                ),
                "summary": current.get("summary", ""),
            })
    return entries


@router.get("/blame")
def get_blame(path: str, repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Per-line blame (commit, author, date, commit summary) for a file at a
    given ref. Shells out to real git (line-porcelain format) rather than
    GitPython's Blame API -- same fast-plumbing-path rationale as /tree, and
    matters more here: blame is real work for git to compute (~1.8s on this
    repo's most-edited file, src/validation.cpp at ~6.4k lines)."""
    repo = _get_repo(repo_name)
    try:
        raw = repo.git.blame("--line-porcelain", ref, "--", path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"file not found: {path}@{ref}") from exc

    return {"repo": repo_name, "ref": ref, "path": path, "lines": _parse_blame(raw)}


# %x00 (a literal NUL) as the field delimiter in `git log --format` rather
# than a printable character -- a commit message/author could in principle
# contain any printable delimiter, but never a NUL (git strips those).
_LOG_FORMAT = "%H%x00%an%x00%aI%x00%s"


def _parse_log_line(line: str) -> dict:
    sha, author, date, message = line.split("\x00")
    return {"sha": sha, "short_sha": sha[:7], "author": author, "date": date, "message": message.strip()}


@router.get("/summary")
def get_summary(repo_name: str = "core", ref: str = "HEAD") -> dict:
    """Branch name, latest commit, and total commit count -- for a GitHub-style
    header bar above the file tree/viewer."""
    repo = _get_repo(repo_name)
    try:
        branch = repo.git.rev_parse("--abbrev-ref", ref)
        commit_count = int(repo.git.rev_list("--count", ref))
        latest = _parse_log_line(repo.git.log("-1", f"--format={_LOG_FORMAT}", ref))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"ref not found: {ref}") from exc

    return {
        "repo": repo_name,
        "ref": ref,
        "branch": branch,
        "commit_count": commit_count,
        "latest_commit": latest,
    }


COMMITS_PAGE_SIZE = 30  # matches GitHub's own commit-history page size


@router.get("/commits")
def get_commits(repo_name: str = "core", ref: str = "HEAD", page: int = 1) -> dict:
    """Paginated commit history for a ref, newest first -- same order as
    GitHub's own commits view. page is 1-indexed, matching how it'll be used
    directly as a "page N of M" control."""
    repo = _get_repo(repo_name)
    page = max(1, page)
    skip = (page - 1) * COMMITS_PAGE_SIZE
    try:
        total = int(repo.git.rev_list("--count", ref))
        raw = repo.git.log(
            f"-{COMMITS_PAGE_SIZE}", f"--skip={skip}", f"--format={_LOG_FORMAT}", ref,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"ref not found: {ref}") from exc

    commits = [_parse_log_line(line) for line in raw.splitlines()]
    return {
        "repo": repo_name,
        "ref": ref,
        "page": page,
        "page_size": COMMITS_PAGE_SIZE,
        "total": total,
        "commits": commits,
    }


# %B (raw full message: subject + body) instead of %s -- the commit detail
# view shows the whole thing, GitHub-style, not just the subject line.
_COMMIT_DETAIL_FORMAT = "%H%x00%an%x00%aI%x00%P%x00%B"

_STATUS_NAMES = {"A": "added", "M": "modified", "D": "deleted"}  # R100 etc (renames) handled separately


@router.get("/commit")
def get_commit(sha: str, repo_name: str = "core") -> dict:
    """Full detail for a single commit -- message, parent(s), and per-file
    change stats -- for a GitHub-style commit detail page. Diff *content* for
    each file is fetched separately via /repo/file at this sha and its first
    parent, reusing that endpoint rather than duplicating file-content logic
    here."""
    repo = _get_repo(repo_name)
    try:
        raw = repo.git.show("-s", f"--format={_COMMIT_DETAIL_FORMAT}", sha)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"commit not found: {sha}") from exc

    full_sha, author, date, parents_raw, message = raw.split("\x00", 4)
    parents = parents_raw.split(" ") if parents_raw else []

    files: list[dict] = []
    if parents:
        # Diff against the first parent -- same convention git itself uses
        # for `<sha>^`, and what GitHub shows for merge commits (the changes
        # the merge introduced relative to mainline, not a 3-way combination
        # of both parents).
        numstat = repo.git.diff("--numstat", parents[0], full_sha)
        name_status = repo.git.diff("--name-status", "--find-renames", parents[0], full_sha)

        stats_by_path = {}
        for line in numstat.splitlines():
            added, deleted, path = line.split("\t")
            stats_by_path[path] = {
                "additions": 0 if added == "-" else int(added),  # "-" = binary file
                "deletions": 0 if deleted == "-" else int(deleted),
            }

        for line in name_status.splitlines():
            parts = line.split("\t")
            status_code, paths = parts[0], parts[1:]
            path = paths[-1]  # for renames, the new path
            status = "renamed" if status_code.startswith("R") else _STATUS_NAMES.get(status_code, "modified")
            files.append({
                "path": path,
                "old_path": paths[0] if status == "renamed" else None,
                "status": status,
                **stats_by_path.get(path, {"additions": 0, "deletions": 0}),
            })
    else:
        # Root commit (no parent) -- every file it introduced counts as added.
        for line in repo.git.show("--format=", "--name-status", full_sha).splitlines():
            _status, path = line.split("\t", 1)
            files.append({"path": path, "old_path": None, "status": "added", "additions": 0, "deletions": 0})

    return {
        "repo": repo_name,
        "sha": full_sha,
        "short_sha": full_sha[:7],
        "author": author,
        "date": date,
        "message": message.strip(),
        "parents": parents,
        "parent_short": parents[0][:7] if parents else None,
        "files": files,
    }
