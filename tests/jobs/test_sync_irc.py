from datetime import date
from unittest.mock import patch

from jobs import sync_irc


def test_main_runs_bounded_incremental_ingestion():
    today = date(2026, 7, 28)
    expected_since = {
        "bitcoin-core-dev": date(2026, 7, 21),
        "bitcoin-core-pr-reviews": date(2026, 7, 21),
    }
    with (
        patch.object(sync_irc, "ingest", return_value={"inserted": 2}) as ingest,
        patch.object(sync_irc, "datetime") as mocked_datetime,
    ):
        mocked_datetime.now.return_value.date.return_value = today
        sync_irc.main()

    ingest.assert_called_once_with(since_by_channel=expected_since, until=today)
    assert sync_irc.SYNC_LOOKBACK_DAYS == 7
