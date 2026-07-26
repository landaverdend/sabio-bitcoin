import psycopg2
import pytest
from unittest.mock import MagicMock, patch

from agents.shared import resolve


def _fake_conn(rows=(("row",),), execute_side_effect=None):
    cur = MagicMock()
    cur.fetchall.return_value = list(rows)
    if execute_side_effect is not None:
        cur.execute.side_effect = execute_side_effect
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


class TestRunQuery:
    def test_success_commits_and_returns_connection_to_pool(self):
        conn, cur = _fake_conn(rows=[(1,), (2,)])
        with (
            patch.object(resolve, "get_pooled_connection", return_value=conn),
            patch.object(resolve, "put_pooled_connection") as put_conn,
        ):
            result = resolve.run_query("SELECT 1", {})

        assert result == [(1,), (2,)]
        conn.commit.assert_called_once()
        # A healthy connection must go back to the pool for reuse, not be
        # thrown away -- that's the entire point of pooling.
        put_conn.assert_called_once_with(conn, discard=False)

    def test_retries_once_on_operational_error_then_succeeds(self):
        bad_conn, _ = _fake_conn(execute_side_effect=psycopg2.OperationalError("connection died"))
        good_conn, good_cur = _fake_conn(rows=[(42,)])

        with (
            patch.object(resolve, "get_pooled_connection", side_effect=[bad_conn, good_conn]),
            patch.object(resolve, "put_pooled_connection") as put_conn,
        ):
            result = resolve.run_query("SELECT 1", {})

        assert result == [(42,)]
        # The dead connection must be discarded (never handed back out to a
        # future caller broken); the recovered one goes back normally.
        assert put_conn.call_args_list == [
            ((bad_conn,), {"discard": True}),
            ((good_conn,), {"discard": False}),
        ]

    def test_raises_and_discards_both_after_two_operational_errors(self):
        conn1, _ = _fake_conn(execute_side_effect=psycopg2.OperationalError("first"))
        conn2, _ = _fake_conn(execute_side_effect=psycopg2.OperationalError("second"))

        with (
            patch.object(resolve, "get_pooled_connection", side_effect=[conn1, conn2]),
            patch.object(resolve, "put_pooled_connection") as put_conn,
        ):
            with pytest.raises(psycopg2.OperationalError):
                resolve.run_query("SELECT 1", {})

        assert put_conn.call_args_list == [
            ((conn1,), {"discard": True}),
            ((conn2,), {"discard": True}),
        ]

    def test_non_operational_error_rolls_back_but_keeps_the_connection(self):
        """A bad query doesn't mean the connection itself is broken --
        discarding it would needlessly shrink the pool over something a
        rollback already fixes."""
        conn, _ = _fake_conn(execute_side_effect=ValueError("bad query"))

        with (
            patch.object(resolve, "get_pooled_connection", return_value=conn),
            patch.object(resolve, "put_pooled_connection") as put_conn,
        ):
            with pytest.raises(ValueError):
                resolve.run_query("SELECT 1", {})

        conn.rollback.assert_called_once()
        put_conn.assert_called_once_with(conn, discard=False)


class TestResolve:
    """resolve()'s own merge logic, not run_query's connection handling --
    mocks run_query directly and feeds it exactly the two-query shape resolve()
    now issues: the search itself, then one group-membership fetch for
    whichever canonical roots (db/migrations/0008) it matched."""

    def test_blank_query_returns_empty_without_querying(self):
        with patch.object(resolve, "run_query") as run_query:
            assert resolve.resolve("   ") == []
        run_query.assert_not_called()

    def test_no_matches_returns_empty_without_a_second_query(self):
        with patch.object(resolve, "run_query", return_value=[]) as run_query:
            assert resolve.resolve("nobody") == []
        run_query.assert_called_once()

    def test_single_unlinked_person_passes_through(self):
        search_rows = [
            ("person:7", "person", "Jane Dev -- jane@example.com", 1.0, "jane@example.com", None, "janedev", None),
        ]
        group_rows = [(7, None, "Jane Dev", "jane@example.com", None, "janedev")]
        with patch.object(resolve, "run_query", side_effect=[search_rows, group_rows]):
            candidates = resolve.resolve("jane")

        assert candidates == [{
            "id": "person:7",
            "type": "person",
            "label": "Jane Dev -- jane@example.com",
            "score": 1.0,
            "person_id": 7,
            "email": "jane@example.com",
            "bitcointalk_username": None,
            "github_username": "janedev",
        }]

    def test_merges_two_matched_rows_in_the_same_canonical_group(self):
        # Mirrors real data: a GitHub/email-linked root row (539) and a
        # BitcoinTalk-only row (8381, canonical_person_id=539) both
        # independently matching the same query, with no column in common.
        search_rows = [
            ("person:539", "person", "Gregory Maxwell -- gmaxwell@gmail.com", 0.9,
             "gmaxwell@gmail.com", None, "gmaxwell", None),
            ("person:8381", "person", "gmaxwell -- gmaxwell", 1.0,
             None, "gmaxwell", None, 539),
        ]
        group_rows = [
            (539, None, "Gregory Maxwell", "gmaxwell@gmail.com", None, "gmaxwell"),
            (8381, 539, "gmaxwell", None, "gmaxwell", None),
        ]
        with patch.object(resolve, "run_query", side_effect=[search_rows, group_rows]) as run_query:
            candidates = resolve.resolve("maxwell")

        # One merged candidate, not two fragments.
        assert candidates == [{
            "id": "person:539",
            "type": "person",
            "label": "Gregory Maxwell -- gmaxwell@gmail.com",
            "score": 1.0,  # max() of the two rows' scores
            "person_id": 539,  # the canonical root, not whichever row matched harder
            "email": "gmaxwell@gmail.com",  # only the root row has one
            "bitcointalk_username": "gmaxwell",  # only the linked row has one
            "github_username": "gmaxwell",
        }]
        # The group-membership fetch is scoped to the one root actually
        # matched, not every person row in the database.
        assert run_query.call_args_list[1].args[1] == {"roots": [539]}

    def test_distinct_people_are_not_merged(self):
        # Ian Maxwell and Gregory Maxwell share no canonical_person_id --
        # a naive name-similarity merge would wrongly conflate them.
        search_rows = [
            ("person:539", "person", "Gregory Maxwell -- gmaxwell@gmail.com", 0.9,
             "gmaxwell@gmail.com", None, "gmaxwell", None),
            ("person:999", "person", "Ian Maxwell -- Ian Maxwell", 0.6,
             None, "Ian Maxwell", None, None),
        ]
        group_rows = [
            (539, None, "Gregory Maxwell", "gmaxwell@gmail.com", None, "gmaxwell"),
            (999, None, "Ian Maxwell", None, "Ian Maxwell", None),
        ]
        with patch.object(resolve, "run_query", side_effect=[search_rows, group_rows]):
            candidates = resolve.resolve("maxwell")

        assert [c["person_id"] for c in candidates] == [539, 999]

    def test_limit_applies_after_merging_not_before(self):
        # Two raw matches that collapse into one group must not cost a slot
        # that a genuinely distinct third match would otherwise take.
        search_rows = [
            ("person:1", "person", "A -- a", 1.0, "a@example.com", None, None, None),
            ("person:2", "person", "A alt -- a", 0.95, None, "a-bt", None, 1),
            ("person:3", "person", "B -- b", 0.9, "b@example.com", None, None, None),
        ]
        group_rows = [
            (1, None, "A", "a@example.com", None, None),
            (2, 1, "A alt", None, "a-bt", None),
            (3, None, "B", "b@example.com", None, None),
        ]
        with patch.object(resolve, "run_query", side_effect=[search_rows, group_rows]):
            candidates = resolve.resolve("a", limit=2)

        assert [c["person_id"] for c in candidates] == [1, 3]
