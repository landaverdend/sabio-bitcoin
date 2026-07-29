from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import patch

from agents.repos import code_browser


def _repo_with_file(content: str):
    content_file = SimpleNamespace(
        decoded_content=content.encode(),
        html_url="https://github.com/bitcoin/bitcoin/blob/master/example.cpp",
    )
    return SimpleNamespace(
        default_branch="master",
        get_contents=lambda *_args, **_kwargs: content_file,
    )


def test_read_file_one_line_past_eof_is_recoverable():
    repo = _repo_with_file("line one\nline two\n")

    with patch.object(code_browser, "_resolve_repo", return_value=repo):
        result = code_browser.read_file(
            "core",
            "example.cpp",
            start_line=3,
            max_lines=10,
        )

    assert result == {
        "error": (
            "start_line 3 is past the end of example.cpp; "
            "the file has 2 lines. Retry with start_line at most 2."
        ),
        "repo": "core",
        "path": "example.cpp",
        "ref": "master",
        "total_lines": 2,
    }


def test_read_file_valid_slice_has_exact_source_metadata():
    repo = _repo_with_file("line one\nline two\nline three\n")

    with patch.object(code_browser, "_resolve_repo", return_value=repo):
        result = code_browser.read_file(
            "core",
            "example.cpp",
            start_line=2,
            max_lines=2,
        )

    assert result["content"] == "line two\nline three\n"
    assert result["start_line"] == 2
    assert result["end_line"] == 3
    assert result["github_url"].endswith("#L2-L3")


def test_code_search_throttle_spaces_requests_and_caps_the_window():
    now = 0.0

    def clock():
        return now

    def sleep(seconds):
        nonlocal now
        now += seconds

    throttle = code_browser._CodeSearchThrottle(
        limit=2,
        window_seconds=60,
        min_interval_seconds=1,
        clock=clock,
        sleep=sleep,
    )

    assert throttle.acquire() is None
    assert throttle.acquire() is None
    assert now == 1
    assert throttle.acquire() == 59


def test_search_code_caches_identical_queries():
    calls = []
    repo = SimpleNamespace(full_name="bitcoin/bitcoin", fork=False)
    hits = [
        SimpleNamespace(
            path="src/script/interpreter.cpp",
            html_url="https://github.com/bitcoin/bitcoin/blob/master/src/script/interpreter.cpp",
        )
    ]
    client = SimpleNamespace(
        search_code=lambda query: calls.append(query) or hits,
    )
    throttle = SimpleNamespace(acquire=lambda: None)

    with (
        patch.object(code_browser, "_resolve_repo", return_value=repo),
        patch.object(code_browser, "_get_search_client", return_value=client),
        patch.object(code_browser, "_CODE_SEARCH_THROTTLE", throttle),
        patch.object(code_browser, "_CODE_SEARCH_CACHE", OrderedDict()),
    ):
        first = code_browser.search_code("core", "CHECKTEMPLATEVERIFY")
        second = code_browser.search_code("core", "checktemplateverify")

    assert first == second
    assert len(calls) == 1
    assert calls[0] == "CHECKTEMPLATEVERIFY repo:bitcoin/bitcoin"


def test_search_code_returns_immediately_when_local_budget_is_full():
    throttle = SimpleNamespace(acquire=lambda: 42.4)

    with (
        patch.object(code_browser, "_CODE_SEARCH_THROTTLE", throttle),
        patch.object(code_browser, "_CODE_SEARCH_CACHE", OrderedDict()),
        patch.object(code_browser, "_resolve_repo") as resolve_repo,
    ):
        result = code_browser.search_code("core", "CHECKTEMPLATEVERIFY")

    assert result == {
        "error": (
            "GitHub code-search budget is busy. Reuse existing results, "
            "inspect a known file or PR, or retry after the reported delay."
        ),
        "retry_after_seconds": 43,
    }
    resolve_repo.assert_not_called()
