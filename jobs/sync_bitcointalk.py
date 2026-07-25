"""Recurring incremental sync of the BitcoinTalk board -- meant to be run on
a schedule (cron/systemd timer; nothing in this repo triggers it
automatically yet), unlike scripts/scrape_bitcointalk.py's full backfill,
which is run once by hand.

Reuses scrape_bitcointalk.backfill() as-is rather than duplicating any
scraping/parsing logic: the board is sorted most-recent-activity-first (see
that module's walk_board_pages() docstring), so anything new or freshly
replied-to since the last run always surfaces within the first few pages --
a bounded topic scan near the top is enough to catch up, no separate
"stale streak" heuristic needed. Every post is still checked against the DB
by external_id before insert (backfill()'s own idempotency), so running this
on a tight schedule, or overlapping with a manual full backfill, is safe.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.scrape_bitcointalk import backfill  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_bitcointalk")

# 10 board pages (400 topics) -- generous headroom over the board's normal
# reply velocity. A tunable knob, not a fundamental limit; raise it if a run
# is ever found to be missing activity near the tail of the scan.
SYNC_TOPIC_LIMIT = 400


def main() -> None:
    logger.info(f"starting incremental sync (max_topics={SYNC_TOPIC_LIMIT})")
    result = backfill(max_topics=SYNC_TOPIC_LIMIT)
    logger.info(f"sync done: {result}")


if __name__ == "__main__":
    main()
