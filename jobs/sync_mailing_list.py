"""Recurring incremental sync of the bitcoin-dev mailing list -- meant to be
run on a schedule (cron/systemd timer; nothing triggers it automatically
yet). Unlike scripts/backfill_mailing_list.py, which downloads and walks the
entire ~95MB archive every time, this fetches only messages posted since the
newest one already in the DB.

Deliberately stateless -- this is meant to run somewhere with no durable
local disk between invocations (a cloud job runner, not a machine we control
long-term), so there's no local mirror or checkpoint file written to survive
between runs. The DB is the only thing guaranteed to persist, so the "since"
watermark is derived from it directly (MAX(posted_at) for this channel)
rather than anything on the filesystem.

The archive (a public-inbox instance) doesn't publish a documented API for
"just the new messages", but its own search UI can export a date-filtered
query as mbox.gz -- POSTing "q=d:<since>..&x=m" with the "results only"
mbox-download button submitted (confirmed by hand against the live site;
this is the exact request the web UI's own download button makes, nothing
more). That keeps each run's download to a handful of KB instead of the
full archive.

A short overlap window is subtracted from the watermark before querying, to
cover messages that land slightly out of Date-header order (the archive is
fed by a mailing list relay, not guaranteed strictly monotonic). This makes
some runs re-fetch a handful of already-ingested messages -- harmless, since
backfill()'s ON CONFLICT DO NOTHING (same as the full backfill) makes
reprocessing them a no-op.
"""

import gzip
import logging
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import get_connection  # noqa: E402
from scripts.backfill_mailing_list import BASE_URL, CHANNEL, backfill  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_mailing_list")

USER_AGENT = "sabio-bitcoin-research/0.1 (+local hackathon project; contact via github)"
FETCH_TIMEOUT = 60

# See module docstring -- cheap to over-cover since re-fetched messages are a
# no-op on insert, so this favors safety over precision.
OVERLAP = timedelta(days=2)


def _current_watermark():
    """The newest posted_at already ingested for this channel, or None if
    nothing has been ingested yet (i.e. the full backfill hasn't run)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT max(posted_at) FROM messages WHERE channel = %(channel)s",
                {"channel": CHANNEL},
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def _download_since(since) -> Path:
    """POSTs the archive's own search-results mbox-download button for
    everything from `since` onward, decompresses the response, and writes it
    to a temp file scoped to this process -- mailbox.mbox needs a real path,
    but nothing here is meant to outlive this run."""
    query = f"d:{since.strftime('%Y-%m-%d')}.."
    url = f"{BASE_URL}/?" + urllib.parse.urlencode({"q": query, "x": "m"})
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode({"z": "results only"}).encode(),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        compressed = resp.read()

    tmp_dir = Path(tempfile.mkdtemp(prefix="bitcoindev-sync-"))
    mbox_path = tmp_dir / "since.mbox"
    mbox_path.write_bytes(gzip.decompress(compressed))
    return mbox_path


def main() -> None:
    watermark = _current_watermark()
    if watermark is None:
        logger.warning(
            "no mailing_list messages in the DB yet -- run "
            "scripts/backfill_mailing_list.py once first, this job only syncs forward from there"
        )
        return

    since = watermark - OVERLAP
    logger.info(f"syncing messages since {since.isoformat()} (watermark={watermark.isoformat()})")
    mbox_path = _download_since(since)
    result = backfill(str(mbox_path))
    logger.info(f"sync done: {result}")


if __name__ == "__main__":
    main()
