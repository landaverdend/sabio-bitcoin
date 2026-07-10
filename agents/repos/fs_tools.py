import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPOS = {
    "core": os.getenv("REPO_BITCOIN_CORE"),
}

_MAX_LIST_ENTRIES = 200
_MAX_READ_LINES = 300
_MAX_SEARCH_RESULTS = 50
_SKIP_DIRS = {".git"}


def _resolve_repo_root(repo_name: str) -> Path:
    path = REPOS.get(repo_name)
    if not path:
        raise ValueError(f"No path configured for repo: {repo_name}")
    root = Path(path).resolve()
    if not root.is_dir():
        raise ValueError(f"Configured path for {repo_name} does not exist: {root}")
    return root


def _resolve_safe_path(repo_name: str, relative_path: str) -> Path:
    root = _resolve_repo_root(repo_name)
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path '{relative_path}' escapes the '{repo_name}' repo root")
    return candidate


def list_directory(repo_name: str, path: str = ".") -> list[dict]:
    """List files and subdirectories at a path within a configured repo."""
    target = _resolve_safe_path(repo_name, path)
    if not target.is_dir():
        raise ValueError(f"Not a directory: {path}")

    entries = []
    for entry in sorted(target.iterdir()):
        if entry.name in _SKIP_DIRS:
            continue
        entries.append({
            "name": entry.name,
            "type": "dir" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        })
        if len(entries) >= _MAX_LIST_ENTRIES:
            break
    return entries


def read_file(repo_name: str, path: str, start_line: int = 1, max_lines: int = _MAX_READ_LINES) -> dict:
    """Read a slice of a text file within a configured repo, starting at start_line."""
    target = _resolve_safe_path(repo_name, path)
    if not target.is_file():
        raise ValueError(f"Not a file: {path}")

    max_lines = min(max_lines, _MAX_READ_LINES)
    with target.open("r", errors="replace") as f:
        lines = f.readlines()

    start_idx = max(start_line - 1, 0)
    selected = lines[start_idx:start_idx + max_lines]
    return {
        "path": path,
        "start_line": start_idx + 1,
        "end_line": start_idx + len(selected),
        "total_lines": len(lines),
        "content": "".join(selected),
    }


def search_code(repo_name: str, pattern: str, path: str = ".", max_results: int = _MAX_SEARCH_RESULTS) -> list[dict]:
    """Search for a regex pattern in files under a path within a configured repo, grep-style."""
    root = _resolve_repo_root(repo_name)
    target = _resolve_safe_path(repo_name, path)
    max_results = min(max_results, _MAX_SEARCH_RESULTS)

    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"Invalid regex '{pattern}': {e}")

    results = []
    for file in target.rglob("*"):
        if _SKIP_DIRS & set(file.parts):
            continue
        if not file.is_file():
            continue
        try:
            with file.open("r", errors="replace") as f:
                for i, line in enumerate(f, start=1):
                    if regex.search(line):
                        results.append({
                            "path": str(file.relative_to(root)),
                            "line": i,
                            "text": line.strip()[:200],
                        })
                        if len(results) >= max_results:
                            return results
        except PermissionError:
            continue
    return results


if __name__ == "__main__":
    for entry in list_directory("core", "src")[:10]:
        print(entry)
