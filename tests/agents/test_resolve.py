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
