from collections import Counter
from datetime import date, timezone
from unittest.mock import MagicMock, patch

from scripts import ingest_gnusha_irc


def test_parse_log_filters_system_events_bots_and_meeting_controls():
    text = """--- Log opened Thu Jan 13 00:00:17 2022
08:58 -!- someone [~person@example.test] has joined #bitcoin-core-dev
08:59 < bitcoin-git> [bitcoin] pushed a commit
09:00 < achow101> hello before the meeting
09:01 < achow101> #startmeeting
09:02 < corebot> Useful commands: #topic #endmeeting
09:03 < achow101> #topic Package relay
09:04 < sipa> We should consider the orphan handling.
09:05 < achow101> #endmeeting
09:06  * sipa nods
09:07 -!- someone has quit [Quit: gone]
"""

    events, stats = ingest_gnusha_irc.parse_log(
        "bitcoin-core-dev",
        date(2022, 1, 13),
        text,
    )

    assert [event.body for event in events] == [
        "hello before the meeting",
        "#topic Package relay",
        "We should consider the orphan handling.",
        "nods",
    ]
    assert events[0].context is None
    assert events[1].context is not None
    assert events[1].context.kind == "weekly_meeting"
    assert events[2].normalized_nick == "sipa"
    assert events[3].event_type == "action"
    assert events[3].context is None

    assert stats["dropped_non_message"] == 3
    assert stats["dropped_bot"] == 2
    assert stats["dropped_meeting_control"] == 2
    assert stats["kept"] == 4
    assert stats["context_weekly_meeting"] == 2
    assert stats["context_none"] == 2


def test_parse_log_converts_gnusha_pst_to_utc():
    text = "09:00 < sipa> hello"

    events, _ = ingest_gnusha_irc.parse_log(
        "bitcoin-core-pr-reviews",
        date(2023, 2, 22),
        text,
    )

    assert events[0].posted_at.tzinfo == timezone.utc
    assert events[0].posted_at.isoformat() == "2023-02-22T17:00:00+00:00"


def test_review_club_context_is_primary_even_when_message_mentions_related_pr():
    meeting_context = ingest_gnusha_irc.Context(
        kind="github_pr",
        key="bitcoin/bitcoin#31664",
        title="#31664 Fee estimation",
        url="https://github.com/bitcoin/bitcoin/pull/31664",
    )
    text = """10:00 < abubakarsadiq> #startmeeting
10:01 < abubakarsadiq> Compare this with PR #12966
10:02 < theStack> Sounds good
10:03 < abubakarsadiq> #endmeeting
"""

    events, _ = ingest_gnusha_irc.parse_log(
        "bitcoin-core-pr-reviews",
        date(2025, 4, 9),
        text,
        review_contexts={date(2025, 4, 9): meeting_context},
    )

    assert len(events) == 2
    assert all(event.context == meeting_context for event in events)


def test_explicit_references_are_conservative_and_typed():
    pull = ingest_gnusha_irc.extract_explicit_context(
        "See https://github.com/bitcoin/bitcoin/pull/25038"
    )
    issue = ingest_gnusha_irc.extract_explicit_context(
        "See https://github.com/bitcoin/bitcoin/issues/31756"
    )
    shorthand = ingest_gnusha_irc.extract_explicit_context("PR #31741 should fix this")
    bare_number = ingest_gnusha_irc.extract_explicit_context("Maybe #31741 matters")

    assert pull is not None
    assert pull.kind == "github_pr"
    assert pull.key == "bitcoin/bitcoin#25038"
    assert issue is not None
    assert issue.kind == "github_issue"
    assert shorthand is not None
    assert shorthand.kind == "github_pr"
    assert bare_number is None


def test_parse_review_contexts_handles_pr_and_non_pr_meetings():
    html = """
    <table>
      <tr class="Home-posts-post">
        <td class="Home-posts-post-date">22 Feb 2023</td>
        <td><a class="Home-posts-post-title" href="/25038">#25038 nVersion=3</a></td>
      </tr>
      <tr class="Home-posts-post">
        <td class="Home-posts-post-date">08 Apr 2026</td>
        <td><a class="Home-posts-post-title" href="/v31-rc-testing">Testing 31.0 RCs</a></td>
      </tr>
    </table>
    """

    contexts = ingest_gnusha_irc.parse_review_contexts(html)

    assert contexts[date(2023, 2, 22)].kind == "github_pr"
    assert contexts[date(2023, 2, 22)].key == "bitcoin/bitcoin#25038"
    assert contexts[date(2026, 4, 8)].kind == "other"
    assert contexts[date(2026, 4, 8)].url == "https://bitcoincore.reviews/v31-rc-testing"


def test_parse_log_index_is_scoped_and_date_filtered():
    html = """
    <a href="2025-01-01.log">2025-01-01.log</a>
    <a href="2025-01-02.log">2025-01-02.log</a>
    <a href="notes.txt">notes</a>
    """

    files = ingest_gnusha_irc.parse_log_index(
        "bitcoin-core-dev",
        html,
        since=date(2025, 1, 2),
    )

    assert len(files) == 1
    assert files[0].log_date == date(2025, 1, 2)
    assert files[0].url == "https://gnusha.org/bitcoin-core-dev/2025-01-02.log"


def test_known_identity_aliases_map_to_one_canonical_person():
    sipa = ingest_gnusha_irc.known_identity_for_nick("sipa__")
    wumpus = ingest_gnusha_irc.known_identity_for_nick("wumpus")
    laanwj = ingest_gnusha_irc.known_identity_for_nick("laanwj")
    glozow = ingest_gnusha_irc.known_identity_for_nick("glozow")
    gzhao408 = ingest_gnusha_irc.known_identity_for_nick("gzhao408")

    assert sipa is not None
    assert sipa.display_name == "Pieter Wuille"
    assert sipa.github_username == "sipa"
    assert wumpus is laanwj
    assert glozow is gzhao408


def test_unknown_identity_uses_unique_exact_github_username_match():
    events, _ = ingest_gnusha_irc.parse_log(
        "bitcoin-core-dev",
        date(2025, 1, 1),
        "09:00 < michaelfolkson> hello",
    )
    cur = MagicMock()
    cur.fetchone.side_effect = [None, (953,)]
    cache = {}
    stats = Counter()

    person_id = ingest_gnusha_irc._resolve_person(cur, events[0], cache, stats)

    assert person_id == 953
    assert stats["people_linked_exact_github"] == 1
    assert cache["michaelfolkson"] == 953
    assert cur.execute.call_args_list[1].args == (
        ingest_gnusha_irc._SELECT_PERSON_BY_UNIQUE_GITHUB_SQL,
        {"github_username": "michaelfolkson"},
    )


def test_dry_run_never_opens_database_connection():
    index = '<a href="2025-01-01.log">2025-01-01.log</a>'
    meeting_html = "<table></table>"
    log = "09:00 < sipa> hello"

    def fake_fetch(url, *, throttle=False):
        if url == ingest_gnusha_irc.REVIEW_MEETINGS_URL:
            return meeting_html.encode()
        if url.endswith("/bitcoin-core-dev/"):
            return index.encode()
        if url.endswith("2025-01-01.log"):
            return log.encode()
        raise AssertionError(f"unexpected URL {url}")

    with (
        patch.object(ingest_gnusha_irc, "_fetch_bytes", side_effect=fake_fetch),
        patch.object(ingest_gnusha_irc, "get_connection") as get_connection,
    ):
        result = ingest_gnusha_irc.ingest(
            channels=("bitcoin-core-dev",),
            since_by_channel={"bitcoin-core-dev": date(2025, 1, 1)},
            dry_run=True,
        )

    get_connection.assert_not_called()
    assert result["files_fetched"] == 1
    assert result["kept"] == 1


def test_ingest_resolves_people_only_for_missing_source_lines():
    index = '<a href="2025-01-01.log">2025-01-01.log</a>'
    log = "09:00 < sipa> already stored"
    conn = MagicMock()
    cur = MagicMock()

    def fake_fetch(url, *, throttle=False):
        if url.endswith("/bitcoin-core-dev/"):
            return index.encode()
        if url.endswith("2025-01-01.log"):
            return log.encode()
        raise AssertionError(f"unexpected URL {url}")

    with (
        patch.object(ingest_gnusha_irc, "_fetch_bytes", side_effect=fake_fetch),
        patch.object(ingest_gnusha_irc, "_connect_and_lock", return_value=(conn, cur)),
        patch.object(ingest_gnusha_irc, "_existing_line_numbers", return_value={1}),
        patch.object(ingest_gnusha_irc, "_resolve_person") as resolve_person,
    ):
        result = ingest_gnusha_irc.ingest(
            channels=("bitcoin-core-dev",),
            since_by_channel={"bitcoin-core-dev": date(2025, 1, 1)},
        )

    resolve_person.assert_not_called()
    assert result["already_present"] == 1
    assert result.get("inserted", 0) == 0
    conn.commit.assert_called_once()
    cur.close.assert_called_once()
    conn.close.assert_called_once()


def test_event_insert_includes_required_raw_line_and_conflict_guard():
    event, _ = ingest_gnusha_irc.parse_log(
        "bitcoin-core-dev",
        date(2025, 1, 1),
        "09:00 < sipa> hello",
    )

    params = ingest_gnusha_irc._event_params(event[0], person_id=42)

    assert params["raw_line"] == "09:00 < sipa> hello"
    assert params["person_id"] == 42
    assert "ON CONFLICT (source, channel, log_date, line_number) DO NOTHING" in (
        ingest_gnusha_irc._INSERT_EVENT_SQL
    )
