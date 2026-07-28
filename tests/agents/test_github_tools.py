from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agents.repos import github_tools


NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _user(login: str):
    return SimpleNamespace(login=login)


def _pr(*, body: str = "Pull request body"):
    conversation = [
        SimpleNamespace(
            id=101,
            user=_user("alice"),
            body="Initial discussion without the target.",
            created_at=NOW,
            updated_at=NOW,
            html_url="https://github.com/bitcoin/bitcoin/pull/42#issuecomment-101",
            issue_url="https://api.github.com/repos/bitcoin/bitcoin/issues/42",
        ),
        SimpleNamespace(
            id=102,
            user=_user("bob"),
            body=("context " * 100) + "package relay is the important match",
            created_at=NOW,
            updated_at=NOW,
            html_url="https://github.com/bitcoin/bitcoin/pull/42#issuecomment-102",
            issue_url="https://api.github.com/repos/bitcoin/bitcoin/issues/42",
        ),
    ]
    reviews = [
        SimpleNamespace(
            id=201,
            user=_user("carol"),
            body="ACK, package relay looks correct.",
            state="APPROVED",
            submitted_at=NOW,
            html_url="https://github.com/bitcoin/bitcoin/pull/42#pullrequestreview-201",
        )
    ]
    inline = [
        SimpleNamespace(
            id=301,
            user=_user("bob"),
            body="Could this package relay condition be simplified?",
            path="src/net_processing.cpp",
            line=None,
            original_line=700,
            created_at=NOW,
            updated_at=NOW,
            html_url="https://github.com/bitcoin/bitcoin/pull/42#discussion_r301",
            pull_request_url="https://api.github.com/repos/bitcoin/bitcoin/pulls/42",
        )
    ]
    pr = SimpleNamespace(
        number=42,
        title="Add package relay",
        body=body,
        user=_user("author"),
        created_at=NOW,
        updated_at=NOW,
        html_url="https://github.com/bitcoin/bitcoin/pull/42",
        base=SimpleNamespace(repo=SimpleNamespace(full_name="bitcoin/bitcoin")),
        get_issue_comments=lambda: conversation,
        get_reviews=lambda: reviews,
        get_review_comments=lambda: inline,
        get_issue_comment=lambda item_id: next(
            item for item in conversation if item.id == item_id
        ),
        get_review=lambda item_id: next(item for item in reviews if item.id == item_id),
        get_review_comment=lambda item_id: next(
            item for item in inline if item.id == item_id
        ),
    )
    return pr


def test_search_prs_builds_supported_github_qualifiers():
    captured = {}
    client = SimpleNamespace(
        search_issues=lambda query: captured.setdefault("query", query) and []
    )
    repo = SimpleNamespace(full_name="bitcoin/bitcoin")

    with (
        patch.object(github_tools, "_resolve_repo", return_value=repo),
        patch.object(github_tools, "_get_client", return_value=client),
    ):
        result = github_tools.search_prs(
            "core",
            "package relay",
            author="glozow",
            commenter="sipa",
            reviewed_by="achow101",
            state="closed",
            search_in="comments",
            merged=True,
            created_after="2024-01-02",
            updated_after="2025-03-04",
        )

    assert result == []
    assert captured["query"] == (
        "repo:bitcoin/bitcoin is:pr package relay in:comments author:glozow "
        "commenter:sipa reviewed-by:achow101 state:closed is:merged "
        "created:>=2024-01-02 updated:>=2025-03-04"
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"search_in": "files"}, "search_in must be one of"),
        ({"created_after": "last-week"}, "created_after must be an ISO date"),
        ({"updated_after": "2026-02-30"}, "updated_after must be an ISO date"),
    ],
)
def test_search_prs_rejects_invalid_structured_qualifiers(kwargs, message):
    with patch.object(
        github_tools,
        "_resolve_repo",
        return_value=SimpleNamespace(full_name="bitcoin/bitcoin"),
    ):
        with pytest.raises(ValueError, match=message):
            github_tools.search_prs(**kwargs)


def test_search_pr_discussion_returns_exact_ids_and_match_centered_excerpts():
    repo = SimpleNamespace(get_pull=lambda _number: _pr())

    with patch.object(github_tools, "_resolve_repo", return_value=repo):
        results = github_tools.search_pr_discussion(
            "core",
            42,
            query="package relay",
            commenter="bob",
        )

    assert [(item["kind"], item["id"]) for item in results] == [
        ("conversation_comment", 102),
        ("review_comment", 301),
    ]
    assert all("package relay" in item["excerpt"] for item in results)
    assert results[1]["path"] == "src/net_processing.cpp"
    assert results[1]["line"] == 700


def test_get_pr_discussion_item_returns_untruncated_citable_text():
    body = "x" * 700
    pr = _pr()
    pr.get_issue_comment(102).body = body
    repo = SimpleNamespace(get_pull=lambda _number: pr)

    with patch.object(github_tools, "_resolve_repo", return_value=repo):
        result = github_tools.get_pr_discussion_item(
            "core",
            42,
            "conversation_comment",
            102,
        )

    assert result["repo"] == "bitcoin/bitcoin"
    assert result["pr_number"] == 42
    assert result["kind"] == "conversation_comment"
    assert result["id"] == 102
    assert result["body"] == body
    assert result["url"].endswith("#issuecomment-102")


def test_get_pr_discussion_item_rejects_comment_from_another_pr():
    pr = _pr()
    comment = pr.get_issue_comment(102)
    comment.issue_url = "https://api.github.com/repos/bitcoin/bitcoin/issues/99"
    repo = SimpleNamespace(get_pull=lambda _number: pr)

    with patch.object(github_tools, "_resolve_repo", return_value=repo):
        with pytest.raises(ValueError, match="does not belong to PR #42"):
            github_tools.get_pr_discussion_item(
                "core",
                42,
                "conversation_comment",
                102,
            )
