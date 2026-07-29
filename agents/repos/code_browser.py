import threading
import time
from math import ceil
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Optional

from github import GithubException

from .github_tools import (  # noqa: F401 (REPOS re-exported for callers)
    REPOS,
    _get_search_client,
    _resolve_repo,
)

_MAX_LIST_ENTRIES = 200
_MAX_READ_LINES = 300
_CODE_SEARCH_LIMIT = 8
_CODE_SEARCH_WINDOW_SECONDS = 60.0
_CODE_SEARCH_MIN_INTERVAL_SECONDS = 1.0
_CODE_SEARCH_CACHE_TTL_SECONDS = 300.0
_CODE_SEARCH_CACHE_ENTRIES = 256

# GitHub's Contents API refuses files over this via the same call that lists
# directories -- large files need the raw blob API instead, not worth the
# extra code path for source browsing.
_BINARY_SNIFF_BYTES = 8000


class _CodeSearchThrottle:
    """Process-wide rolling-window gate for GitHub's small code-search quota."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._limit = limit
        self._window_seconds = window_seconds
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._requests: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> float | None:
        """Reserve one request or return seconds until budget is available."""
        with self._lock:
            now = self._clock()
            self._discard_expired(now)
            if len(self._requests) >= self._limit:
                return max(
                    0.0,
                    self._window_seconds - (now - self._requests[0]),
                )

            if self._requests:
                delay = self._min_interval_seconds - (now - self._requests[-1])
                if delay > 0:
                    self._sleep(delay)
                    now = self._clock()
                    self._discard_expired(now)

            if len(self._requests) >= self._limit:
                return max(
                    0.0,
                    self._window_seconds - (now - self._requests[0]),
                )
            self._requests.append(now)
            return None

    def _discard_expired(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._requests and self._requests[0] <= cutoff:
            self._requests.popleft()


_CODE_SEARCH_THROTTLE = _CodeSearchThrottle(
    limit=_CODE_SEARCH_LIMIT,
    window_seconds=_CODE_SEARCH_WINDOW_SECONDS,
    min_interval_seconds=_CODE_SEARCH_MIN_INTERVAL_SECONDS,
)
_CODE_SEARCH_CACHE: OrderedDict[
    tuple[str, str], tuple[float, list[dict]]
] = OrderedDict()
_CODE_SEARCH_CACHE_LOCK = threading.Lock()


def _code_search_cache_get(key: tuple[str, str]) -> list[dict] | None:
    now = time.monotonic()
    with _CODE_SEARCH_CACHE_LOCK:
        cached = _CODE_SEARCH_CACHE.get(key)
        if cached is None:
            return None
        created_at, results = cached
        if now - created_at >= _CODE_SEARCH_CACHE_TTL_SECONDS:
            del _CODE_SEARCH_CACHE[key]
            return None
        _CODE_SEARCH_CACHE.move_to_end(key)
        return [dict(result) for result in results]


def _code_search_cache_put(key: tuple[str, str], results: list[dict]) -> None:
    with _CODE_SEARCH_CACHE_LOCK:
        _CODE_SEARCH_CACHE[key] = (
            time.monotonic(),
            [dict(result) for result in results],
        )
        _CODE_SEARCH_CACHE.move_to_end(key)
        while len(_CODE_SEARCH_CACHE) > _CODE_SEARCH_CACHE_ENTRIES:
            _CODE_SEARCH_CACHE.popitem(last=False)


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


def search_code(
    repo_name: str,
    query: str,
    max_results: int = 30,
) -> list[dict] | dict:
    """Search source code in a configured repo using GitHub's code search --
    keyword/phrase based (quote exact phrases with ""), not a regex engine,
    and only searches the repo's default branch (GitHub's search index
    doesn't cover arbitrary refs).

    Identical searches are cached briefly. When this Sabio process has used
    its safe share of GitHub's code-search quota, returns an error with
    retry_after_seconds instead of blocking the whole research turn.
    """
    query = query.strip()
    max_results = max(0, min(max_results, 30))
    if not query:
        return {
            "error": "query cannot be blank",
            "retry_after_seconds": 0,
        }
    if max_results == 0:
        return []

    cache_key = (repo_name.casefold(), query.casefold())
    cached = _code_search_cache_get(cache_key)
    if cached is not None:
        return cached[:max_results]

    retry_after = _CODE_SEARCH_THROTTLE.acquire()
    if retry_after is not None:
        return {
            "error": (
                "GitHub code-search budget is busy. Reuse existing results, "
                "inspect a known file or PR, or retry after the reported delay."
            ),
            "retry_after_seconds": max(1, ceil(retry_after)),
        }

    # A matching request may have filled the cache while this call waited for
    # the shared gate. Recheck before spending a real GitHub request.
    cached = _code_search_cache_get(cache_key)
    if cached is not None:
        return cached[:max_results]

    repo = _resolve_repo(repo_name)
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
    try:
        for hit in _get_search_client().search_code(f"{query} {qualifiers}"):
            results.append({"path": hit.path, "url": hit.html_url})
            if len(results) >= 30:
                break
    except GithubException as exc:
        if exc.status not in (403, 429):
            raise
        headers = exc.headers or {}
        retry_after_header = headers.get("retry-after")
        reset_header = headers.get("x-ratelimit-reset")
        retry_seconds = 60
        if retry_after_header and str(retry_after_header).isdigit():
            retry_seconds = max(1, int(retry_after_header))
        elif reset_header and str(reset_header).isdigit():
            retry_seconds = max(1, int(reset_header) - int(time.time()))
        return {
            "error": "GitHub code search is temporarily rate-limited.",
            "retry_after_seconds": retry_seconds,
        }

    _code_search_cache_put(cache_key, results)
    return results[:max_results]
