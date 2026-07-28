from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from agents.irc import db_tools


def _run_query_returning(rows):
    return patch.object(db_tools, "run_query", return_value=rows)


class TestSearchIrc:
    def test_searches_only_gnusha_and_supports_pr_context(self):
        posted_at = datetime(2025, 4, 9, 17, 1, tzinfo=timezone.utc)
        rows = [
            (
                42,
                "bitcoin-core-pr-reviews",
                "theStack",
                7,
                posted_at,
                "message",
                "This changes the fee estimation behavior.",
                "github_pr",
                "bitcoin/bitcoin#31664",
                "#31664 Fee estimation",
                "https://github.com/bitcoin/bitcoin/pull/31664",
                "https://gnusha.org/bitcoin-core-pr-reviews/2025-04-09.log",
                0.25,
            )
        ]
        with _run_query_returning(rows) as run_query:
            results = db_tools.search_irc(
                query="fee estimation",
                channel="#bitcoin-core-pr-reviews",
                context_kind="github_pr",
                context_key="bitcoin/bitcoin#31664",
            )

        sql, params = run_query.call_args.args
        assert "e.source = 'gnusha'" in sql
        assert "e.search_vector @@" in sql
        assert "e.channel = %(channel)s" in sql
        assert "e.context_key = %(context_key)s" in sql
        assert params["channel"] == "bitcoin-core-pr-reviews"
        assert params["context_key"] == "bitcoin/bitcoin#31664"
        assert results == [
            {
                "id": "irc_event:42",
                "channel": "bitcoin-core-pr-reviews",
                "nick": "theStack",
                "person_id": 7,
                "posted_at": posted_at.isoformat(),
                "event_type": "message",
                "snippet": "This changes the fee estimation behavior.",
                "context_kind": "github_pr",
                "context_key": "bitcoin/bitcoin#31664",
                "context_title": "#31664 Fee estimation",
                "context_url": "https://github.com/bitcoin/bitcoin/pull/31664",
                "source_url": (
                    "https://gnusha.org/bitcoin-core-pr-reviews/"
                    "2025-04-09.log"
                ),
                "score": 0.25,
            }
        ]

    def test_person_filter_expands_to_canonical_group(self):
        with _run_query_returning([]) as run_query:
            db_tools.search_irc(person_id=539)

        sql, params = run_query.call_args.args
        assert "member_ids" in sql
        assert "e.person_id IN (SELECT id FROM member_ids)" in sql
        assert params["id"] == 539

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"channel": "random-channel"}, "unsupported IRC channel"),
            ({"context_kind": "random-kind"}, "unsupported IRC context kind"),
        ],
    )
    def test_rejects_unsupported_structured_filters(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            db_tools.search_irc(**kwargs)


def _irc_event_row(event_id=42, nick="fanquake", body="also included #25573"):
    return (
        event_id,
        "bitcoin-core-dev",
        date(2026, 7, 28),
        100,
        datetime(2026, 7, 28, 17, 30, tzinfo=timezone.utc),
        "message",
        nick,
        nick.lower(),
        body,
        7,
        "Michael Ford",
        "bitcoin/bitcoin#25573",
        None,
        "https://github.com/bitcoin/bitcoin/pull/25573",
        "github_pr",
        "https://gnusha.org/bitcoin-core-dev/2026-07-28.log",
        "abc123",
        f"10:30 < {nick}> {body}",
    )


def test_get_irc_event_returns_complete_citable_message():
    with _run_query_returning([_irc_event_row()]):
        event = db_tools.get_irc_event("irc_event:42")

    assert event["id"] == "irc_event:42"
    assert event["channel"] == "bitcoin-core-dev"
    assert event["author"] == "fanquake"
    assert event["person_display_name"] == "Michael Ford"
    assert event["context_kind"] == "github_pr"
    assert event["context_key"] == "bitcoin/bitcoin#25573"
    assert event["url"] == "https://gnusha.org/bitcoin-core-dev/2026-07-28.log"
    assert event["raw_line"] == "10:30 < fanquake> also included #25573"


def test_get_irc_context_returns_neighboring_human_events():
    log_date = date(2026, 7, 28)
    context_rows = [
        _irc_event_row(41, "darosior", "Did you run the others with prune too?"),
        _irc_event_row(42),
    ]
    with patch.object(
        db_tools,
        "run_query",
        side_effect=[
            [("gnusha", "bitcoin-core-dev", log_date)],
            context_rows,
        ],
    ) as run_query:
        result = db_tools.get_irc_context("irc_event:42", before=2, after=3)

    assert result["focus_id"] == "irc_event:42"
    assert [event["id"] for event in result["events"]] == [
        "irc_event:41",
        "irc_event:42",
    ]
    sql, params = run_query.call_args_list[1].args
    assert "row_number() OVER (ORDER BY e.line_number)" in sql
    assert "ranked.sequence BETWEEN focus.sequence" in sql
    assert params["before"] == 2
    assert params["after"] == 3


@pytest.mark.parametrize("event_id", ["nope", "irc_event:0", "irc_event:-1"])
def test_irc_event_ids_are_strict(event_id):
    with pytest.raises(ValueError, match="irc_event:123"):
        db_tools.get_irc_event(event_id)
