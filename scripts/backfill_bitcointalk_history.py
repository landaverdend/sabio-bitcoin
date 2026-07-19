"""One-time historical backfill for BitcoinTalk board=6, oldest topic first.

scrape_bitcointalk.py walks the board in whatever order SMF's default view
gives (most-recent-activity, not creation order) -- perfect for an ongoing
cron job catching new posts cheaply, since new activity always bubbles to
page 0, but it has no guaranteed endpoint for a *complete* history: an old,
inactive topic can sit buried at any page offset indefinitely, and the
board reorders itself live while a long crawl is still walking it.

This script exists to establish that complete history exactly once. SMF
exposes no "sort by creation" option (verified against the board's actual
sort links: subject/starter/replies/views/last_post, nothing chronological),
so getting a stable oldest-first order means discovering every topic_id
first, then sorting ascending -- topic_id is assigned sequentially at
creation, making it the one ordering available that doesn't shift underfoot.

Run this once to backfill from the true beginning, then let
scrape_bitcointalk.py's cron job handle ongoing freshness from the
recency-sorted view -- these are two different problems and don't need to
share one code path.

Safe to stop and resume: shares scrape_bitcointalk.py's per-post
external_id check and advisory lock, so it can't run concurrently with the
regular crawler and won't re-insert what's already there either way.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import get_connection  # noqa: E402
from scrape_bitcointalk import (  # noqa: E402
    _ADVISORY_LOCK_KEY,
    COMMIT_EVERY_TOPICS,
    TOPICS_PER_PAGE,
    _already_ingested,
    _get_or_create_person,
    _INSERT_SQL,
    _post_to_row,
    all_posts_for_topic,
    walk_board_pages,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_bitcointalk_history")


def discover_all_topics() -> list[dict]:
    """Walk every board index page and collect every topic, regardless of
    the board's own (recency) sort order. Delegates the actual page-walking
    and end-of-board detection to walk_board_pages() -- see its docstring:
    SMF here never returns an empty page past the last one, it clamps to
    the last valid page instead, so "stop on empty" alone doesn't work."""
    topics: dict[str, dict] = {}
    for page_num, page_topics in enumerate(walk_board_pages()):
        for topic in page_topics:
            topics.setdefault(topic["topic_id"], topic)
        logger.info(f"discovered {len(topics)} topics so far "
                    f"(board_offset={page_num * TOPICS_PER_PAGE})")
    return list(topics.values())


def backfill_history(max_topics: int | None = None) -> dict:
    """Discover every topic once, sort oldest-first by topic_id, then walk
    each one's posts and upsert into `messages` -- same idempotent per-post
    logic as scrape_bitcointalk.py's ongoing crawler, just fed from a
    pre-sorted list instead of the live recency-sorted board view."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%(key)s)", {"key": _ADVISORY_LOCK_KEY})
            if not cur.fetchone()[0]:
                raise RuntimeError(
                    "scrape_bitcointalk.py (or another backfill_bitcointalk_history.py run) "
                    "is already running against this database -- check "
                    "`ps aux | grep bitcointalk` and kill it before retrying"
                )

            logger.info("discovering all topics on the board (one-time enumeration)...")
            all_topics = discover_all_topics()
            all_topics.sort(key=lambda t: int(t["topic_id"]))
            logger.info(f"discovered {len(all_topics)} topics total, processing oldest first")

            if max_topics is not None:
                all_topics = all_topics[:max_topics]

            topics_seen = posts_seen = inserted = skipped = 0
            for topic in all_topics:
                topics_seen += 1
                for post in all_posts_for_topic(topic["topic_id"]):
                    posts_seen += 1
                    if posts_seen % 200 == 0:
                        logger.info(f"still walking topic {topic['topic_id']} -- "
                                    f"posts_seen={posts_seen} inserted={inserted} skipped={skipped}")

                    if _already_ingested(cur, post["msg_id"]):
                        skipped += 1
                        continue

                    person_id = _get_or_create_person(cur, post["author"]) if post["author"] else None
                    cur.execute(_INSERT_SQL, _post_to_row(post, topic, person_id))
                    row = cur.fetchone()
                    if row:
                        inserted += 1
                        logger.info(f"inserted id={row[0]} -- {post['url']}")

                if topics_seen % COMMIT_EVERY_TOPICS == 0:
                    conn.commit()

            conn.commit()
    finally:
        conn.close()

    logger.info(f"done: topics={topics_seen} posts={posts_seen} inserted={inserted} skipped={skipped}")
    return {"topics": topics_seen, "posts": posts_seen, "inserted": inserted, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-time historical backfill of the BitcoinTalk board, oldest topic first."
    )
    parser.add_argument(
        "--max-topics", type=int, default=None,
        help="Stop after this many topics (default: no limit -- the whole board).",
    )
    args = parser.parse_args()
    backfill_history(max_topics=args.max_topics)


if __name__ == "__main__":
    main()
