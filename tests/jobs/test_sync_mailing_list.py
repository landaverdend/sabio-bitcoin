import gzip
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from jobs import sync_mailing_list


def _mock_conn(fetchone_result):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_result
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


class TestCurrentWatermark:
    def test_returns_max_posted_at(self):
        watermark = datetime(2026, 7, 12, 18, 34, 40, tzinfo=timezone.utc)
        conn, cur = _mock_conn((watermark,))
        with patch.object(sync_mailing_list, "get_connection", return_value=conn):
            result = sync_mailing_list._current_watermark()

        assert result == watermark
        # Scoped to this channel -- a shared `messages` table also holds
        # bitcointalk rows, which must never leak into this query.
        (sql, params), _ = cur.execute.call_args
        assert params == {"channel": sync_mailing_list.CHANNEL}
        assert sync_mailing_list.CHANNEL == "mailing_list"
        conn.close.assert_called_once()

    def test_returns_none_when_nothing_ingested_yet(self):
        conn, _ = _mock_conn((None,))
        with patch.object(sync_mailing_list, "get_connection", return_value=conn):
            result = sync_mailing_list._current_watermark()
        assert result is None

    def test_closes_connection_even_on_error(self):
        conn, cur = _mock_conn(None)
        cur.execute.side_effect = RuntimeError("boom")
        with patch.object(sync_mailing_list, "get_connection", return_value=conn):
            try:
                sync_mailing_list._current_watermark()
            except RuntimeError:
                pass
        conn.close.assert_called_once()


class TestDownloadSince:
    def test_builds_date_query_and_writes_decompressed_mbox(self, tmp_path):
        since = datetime(2026, 7, 10, tzinfo=timezone.utc)
        body = b"From mboxrd@z Thu Jan  1 00:00:00 1970\nSubject: test\n\nhello\n"
        fake_resp = MagicMock()
        fake_resp.read.return_value = gzip.compress(body)
        fake_resp.__enter__.return_value = fake_resp

        with (
            patch.object(sync_mailing_list.tempfile, "mkdtemp", return_value=str(tmp_path)),
            patch.object(sync_mailing_list.urllib.request, "urlopen", return_value=fake_resp) as urlopen,
        ):
            result = sync_mailing_list._download_since(since)

        req = urlopen.call_args[0][0]
        # x=m selects mbox output; the actual date-range filter (the whole
        # point of this being incremental rather than a full re-download)
        # lives in "q" -- a regression here silently turns this back into a
        # full-archive fetch.
        assert req.full_url == f"{sync_mailing_list.BASE_URL}/?q=d%3A2026-07-10..&x=m"
        assert req.data == b"z=results+only"
        assert result.read_bytes() == body


class TestMain:
    def test_no_watermark_skips_sync_entirely(self):
        with (
            patch.object(sync_mailing_list, "_current_watermark", return_value=None),
            patch.object(sync_mailing_list, "_download_since") as download,
            patch.object(sync_mailing_list, "backfill") as backfill,
        ):
            sync_mailing_list.main()

        # No prior data means there's no channel row to derive a query date
        # from -- must bail out rather than guess a start date and either
        # re-download the whole archive or silently query nothing useful.
        download.assert_not_called()
        backfill.assert_not_called()

    def test_syncs_from_watermark_minus_overlap(self):
        watermark = datetime(2026, 7, 24, 1, 45, tzinfo=timezone.utc)
        mbox_path = MagicMock()
        with (
            patch.object(sync_mailing_list, "_current_watermark", return_value=watermark),
            patch.object(sync_mailing_list, "_download_since", return_value=mbox_path) as download,
            patch.object(sync_mailing_list, "backfill", return_value={"inserted": 1}) as backfill,
        ):
            sync_mailing_list.main()

        (since_arg,), _ = download.call_args
        assert since_arg == watermark - sync_mailing_list.OVERLAP
        backfill.assert_called_once_with(str(mbox_path))
