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
