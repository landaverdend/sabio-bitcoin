"""Recurring bounded gnusha IRC sync.

Designed for cron/systemd timers. Every run refetches a fixed recent window
for both channels, so append-only current logs and ordinary scheduler downtime
are covered without depending on a database watermark. A watermark cannot
represent a successfully processed day containing zero human messages because
noise-only days deliberately insert no rows.

The ingester queries existing source line numbers before person reconciliation
or insertion and has an ``ON CONFLICT DO NOTHING`` backstop, so the overlap
never duplicates events. Run ``scripts/ingest_gnusha_irc.py`` once for full
history.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ingest_gnusha_irc import CHANNELS, LOG_TIMEZONE, ingest  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_irc")

SYNC_LOOKBACK_DAYS = 7


def main() -> None:
    today = datetime.now(LOG_TIMEZONE).date()
    since = today - timedelta(days=SYNC_LOOKBACK_DAYS)
    since_by_channel = {channel: since for channel in CHANNELS}
    logger.info("starting IRC sync through %s from %s", today, since_by_channel)
    result = ingest(since_by_channel=since_by_channel, until=today)
    logger.info("IRC sync done: %s", result)


if __name__ == "__main__":
    main()
