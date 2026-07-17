"""Repo/git-backed endpoints -- file tree, file content, and (later) commits/
branches all live under this one router, since they all resolve a repo_name
to a path the same way and read git's object database the same way.

Reads always go through git's object database (git ls-tree / show), never
the working directory -- this is safe to call concurrently regardless of
what's checked out on disk, and scoped by ref rather than "whatever HEAD
happens to be right now."
"""

from fastapi import APIRouter, HTTPException
from git import Repo

from agents.repos.indexer import REPOS

router = APIRouter(prefix="/repo", tags=["repo"])


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
