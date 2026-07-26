from typing import Optional

from github import GithubException

from .github_tools import REPOS, _get_client, _resolve_repo  # noqa: F401 (REPOS re-exported for callers)

_MAX_LIST_ENTRIES = 200
_MAX_READ_LINES = 300

# GitHub's Contents API refuses files over this via the same call that lists
# directories -- large files need the raw blob API instead, not worth the
# extra code path for source browsing.
_BINARY_SNIFF_BYTES = 8000


def list_directory(repo_name: str, path: str = ".", ref: Optional[str] = None) -> list[dict]:
    """List files and subdirectories at a path within a configured repo, as
    of a given ref (branch, tag, or commit sha -- defaults to the repo's
    default branch)."""
    repo = _resolve_repo(repo_name)
    path = "" if path in (".", "/") else path.strip("/")
    kwargs = {"ref": ref} if ref else {}
    try:
        contents = repo.get_contents(path, **kwargs)
    except GithubException as exc:
        raise ValueError(f"path not found: {path or '.'}@{ref or 'default'}") from exc

    if not isinstance(contents, list):
        raise ValueError(f"not a directory: {path}")

    entries = [
        {"name": c.name, "type": "dir" if c.type == "dir" else "file", "size": c.size}
        for c in contents[:_MAX_LIST_ENTRIES]
    ]
    return entries


def read_file(
    repo_name: str, path: str, start_line: int = 1, max_lines: int = _MAX_READ_LINES, ref: Optional[str] = None,
) -> dict:
    """Read a slice of a text file within a configured repo at a given ref
    (branch, tag, or commit sha -- defaults to the default branch), starting
    at start_line. Files over 1MB aren't readable this way -- GitHub's
    Contents API doesn't serve them, vanishingly rare for source files."""
    repo = _resolve_repo(repo_name)
    resolved_ref = ref or repo.default_branch
    if start_line < 1:
        return {
            "error": "start_line must be at least 1; retry with start_line=1",
            "repo": repo_name,
            "path": path,
            "ref": resolved_ref,
        }
    if max_lines < 1:
        return {
            "error": "max_lines must be at least 1; retry with a positive max_lines",
            "repo": repo_name,
            "path": path,
            "ref": resolved_ref,
        }
    max_lines = min(max_lines, _MAX_READ_LINES)
    kwargs = {"ref": ref} if ref else {}

    try:
        content_file = repo.get_contents(path.strip("/"), **kwargs)
    except GithubException as exc:
        raise ValueError(f"file not found: {path}@{ref or 'default'}") from exc

    if isinstance(content_file, list):
        raise ValueError(f"not a file: {path}")

    raw = content_file.decoded_content
    if b"\x00" in raw[:_BINARY_SNIFF_BYTES]:
        raise ValueError(f"{path} is a binary file -- cannot read as text")

    lines = raw.decode("utf-8", errors="replace").splitlines(keepends=True)
    if start_line > len(lines):
        # Tool-input mistakes are feedback for the model, not application
        # failures. Returning a normal result lets the agent retry with the
        # reported bound instead of aborting the entire SSE chat stream.
        return {
            "error": (
                f"start_line {start_line} is past the end of {path}; "
                f"the file has {len(lines)} lines. Retry with start_line at most {len(lines)}."
            ),
            "repo": repo_name,
            "path": path,
            "ref": resolved_ref,
            "total_lines": len(lines),
        }
    start_idx = start_line - 1
    selected = lines[start_idx:start_idx + max_lines]
    return {
        "repo": repo_name,
        "path": path,
        "ref": resolved_ref,
        "start_line": start_idx + 1,
        "end_line": start_idx + len(selected),
        "total_lines": len(lines),
        "content": "".join(selected),
        "github_url": (
            f"{content_file.html_url}#L{start_idx + 1}"
            + (f"-L{start_idx + len(selected)}" if len(selected) > 1 else "")
        ),
    }


def search_code(repo_name: str, query: str, max_results: int = 30) -> list[dict]:
    """Search source code in a configured repo using GitHub's code search --
    keyword/phrase based (quote exact phrases with ""), not a regex engine,
    and only searches the repo's default branch (GitHub's search index
    doesn't cover arbitrary refs)."""
    repo = _resolve_repo(repo_name)
    max_results = min(max_results, 30)
    results = []
    # fork:true -- GitHub's code search silently excludes forked repos from
    # results by default (e.g. bitcoinknots/bitcoin, a real GitHub fork of
    # bitcoin/bitcoin per repo.fork). Without this, search_code returns []
    # for every query against a forked repo_name regardless of content.
    # Conditional on repo.fork rather than always-on: empirically fork:true
    # doesn't just "stop excluding forks" (as GitHub's docs for repository
    # search read) -- for code search it restricts results to repos that
    # ARE forks, so adding it unconditionally breaks every non-fork repo
    # (bitcoin/bitcoin, fork:true -> 0 results, confirmed live).
    qualifiers = f"repo:{repo.full_name}" + (" fork:true" if repo.fork else "")
    for hit in _get_client().search_code(f"{query} {qualifiers}"):
        results.append({"path": hit.path, "url": hit.html_url})
        if len(results) >= max_results:
            break
    return results
