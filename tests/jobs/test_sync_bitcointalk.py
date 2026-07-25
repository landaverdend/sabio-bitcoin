from unittest.mock import patch

from jobs import sync_bitcointalk


def test_main_runs_a_bounded_backfill():
    with patch.object(sync_bitcointalk, "backfill", return_value={"inserted": 3}) as backfill:
        sync_bitcointalk.main()

    # The whole point of this job over a plain `scrape_bitcointalk.py` run is
    # the bound -- an unbounded call here would silently turn a scheduled
    # sync back into a multi-hour full-board crawl.
    backfill.assert_called_once_with(max_topics=sync_bitcointalk.SYNC_TOPIC_LIMIT)
    assert sync_bitcointalk.SYNC_TOPIC_LIMIT > 0
