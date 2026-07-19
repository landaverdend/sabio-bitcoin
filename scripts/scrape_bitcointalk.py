"""Ingest BitcoinTalk's Development & Technical Discussion board (board=6)
into `messages` (channel='bitcointalk'). No API exists, so this parses SMF's
HTML directly -- see list_topics()/list_posts() docstrings for the two
pagination levels and the real-HTML quirks already found and fixed (a
duplicate "jump here" anchor breaking first-post extraction, edited posts
appending "Last edit: ..." to the same date div with no separator).

robots.txt has no disallow rules, but there's also no stated crawl-delay --
REQUEST_DELAY below is a conservative default picked ourselves, not one the
site told us to use.

thread_id is the real SMF topic id here (unlike the mailing list, which only
approximates threads by subject-line matching). email stays NULL for every
row: BitcoinTalk hides member emails by default, verified empirically against
several real profiles (including board moderators) before building this.

Safe to re-run: existing posts are never overwritten (ON CONFLICT DO NOTHING).
"""

import argparse
import http.client
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scrape_bitcointalk")

BASE_URL = "https://bitcointalk.org/index.php"
BOARD_ID = 6  # Development & Technical Discussion
CHANNEL = "bitcointalk"
TOPICS_PER_PAGE = 40
POSTS_PER_PAGE = 20
MESSAGE_BODY_CHARS = 4000  # matches the other backfill scripts' cap -- some
# forum posts paste huge logs/code dumps (up to 18k+ chars seen in testing),
# and get_message() hands the full body straight to an LLM tool call.
REQUEST_DELAY = 2.0  # seconds between requests -- reverted from a faster 0.3s:
# the site is Cloudflare-fronted (confirmed via curl -- 3s time-to-first-byte
# on a single plain request), and the faster rate lines up with this scraper
# starting to hang indefinitely (connection accepted, response withheld --
# consistent with bot mitigation, since a non-browser client can't solve a
# JS challenge and just waits forever). Back to the original conservative
# value to stay under whatever threshold triggers that.
USER_AGENT = "sabio-bitcoin-research/0.1 (+local hackathon project; contact via github)"
COMMIT_EVERY_TOPICS = 20
FETCH_RETRIES = 4  # a run this long (thousands of requests) will hit the odd
# dropped connection -- retry a few times with backoff before giving up,
# rather than killing an hours-long crawl over one transient blip.
FETCH_RETRY_BACKOFF = 5.0  # seconds, multiplied by the attempt number
FETCH_TIMEOUT = 15  # seconds -- generous next to real response times (~3s
# observed directly against the site), but short enough that a stall doesn't
# read as an indefinite hang. urlopen blocks forever with no timeout set, so
# a stalled connection (server accepts but never responds, e.g. a WAF
# tarpitting a request it doesn't like) hangs the whole crawl silently
# instead of raising something the retry logic above can act on.

_ADVISORY_LOCK_KEY = 727100600  # arbitrary; just needs to be unique to this script

_TOPIC_LINK_RE = re.compile(r"topic=(\d+)\.0\b")
_DATE_FORMAT = "%B %d, %Y, %I:%M:%S %p"
# Edited posts append "Last edit: <date> by <user>" to the same div with no
# separator ("...01:19:33 PMLast edit: February..."), so the post date has to
# be extracted, not parsed as the whole div text.
_DATE_RE = re.compile(r"[A-Z][a-z]+ \d{1,2}, \d{4}, \d{2}:\d{2}:\d{2} [AP]M")
# SMF shows "Today"/"Yesterday at HH:MM:SS AM/PM" instead of an absolute date
# for recent posts (concatenated with no space, same root cause as the
# "Last edit" case above: "Todayat 04:18:58 AM"). No absolute timestamp is
# exposed anywhere else on the page, so this resolves relative to our own
# clock -- imprecise only in the narrow case of scraping right at a midnight
# boundary vs. the site's own "today".
_RELATIVE_DATE_RE = re.compile(r"(Today|Yesterday)\s*at\s*(\d{2}:\d{2}:\d{2})\s*([AP]M)")

_INSERT_SQL = """
INSERT INTO messages (channel, external_id, thread_id, author, email, person_id, title, body, url, posted_at, raw)
VALUES (%(channel)s, %(external_id)s, %(thread_id)s, %(author)s, NULL, %(person_id)s, %(title)s, %(body)s, %(url)s, %(posted_at)s, %(raw)s)
ON CONFLICT (channel, external_id) DO NOTHING
RETURNING id
"""

# Upsert-or-fetch: keyed on bitcointalk_username (db/migrations/0006) instead
# of email, since this channel never has one. No relay-address guard needed
# here (unlike the mailing list's people reconciliation): SMF usernames are
# already unique per account, so `author` is a clean 1:1 key as-is. Done per
# post, not as a batch pass at the end, so every message row gets its
# person_id set at insert time rather than needing a later linking step.
_UPSERT_PERSON_SQL = """
WITH ins AS (
    INSERT INTO people (bitcointalk_username, display_name)
    VALUES (%(username)s, %(username)s)
    ON CONFLICT (bitcointalk_username) DO NOTHING
    RETURNING id
)
SELECT id FROM ins
UNION ALL
SELECT id FROM people WHERE bitcointalk_username = %(username)s
LIMIT 1
"""


def _fetch(url: str) -> BeautifulSoup:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            break
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            if attempt == FETCH_RETRIES:
                raise
            wait = FETCH_RETRY_BACKOFF * attempt
            logger.warning(f"fetch failed ({exc!r}), retrying in {wait:.0f}s ({attempt}/{FETCH_RETRIES}): {url}")
            time.sleep(wait)
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(html, "html.parser")


def list_topics(page_offset: int = 0) -> list[dict]:
    """List topics on one board index page. page_offset is 0, 40, 80, ..."""
    soup = _fetch(f"{BASE_URL}?board={BOARD_ID}.{page_offset}")
    seen: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = _TOPIC_LINK_RE.search(href)
        if not m or ";all" in href or "#" in href:
            continue
        topic_id = m.group(1)
        title = _clean_text(a.get_text(strip=True))
        if topic_id not in seen and title and not title.isdigit():
            seen[topic_id] = {"topic_id": topic_id, "title": title, "url": href}
    return list(seen.values())


def walk_board_pages():
    """Yield each board page's topics in turn, starting at offset 0, stopping
    at the true end. SMF here never returns an empty page past the last one
    -- confirmed empirically: a way-out-of-range offset (e.g. 300000) returns
    the exact same topic set as the true last page, byte-for-byte, rather
    than signaling the end any other way (this is what caused
    discover_all_topics() to loop for hours: "stop on empty" never fired).
    So the real stop condition is "this page's topics are identical to the
    previous page's", not "this page is empty" -- the latter is kept too,
    in case some other out-of-range response shape shows up."""
    board_offset = 0
    prev_ids = None
    while True:
        topics = list_topics(page_offset=board_offset)
        if not topics:
            break
        ids = frozenset(t["topic_id"] for t in topics)
        if ids == prev_ids:
            break
        yield topics
        prev_ids = ids
        board_offset += TOPICS_PER_PAGE


def _parse_post_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text)
    if m:
        try:
            return datetime.strptime(m.group(0), _DATE_FORMAT)
        except ValueError:
            return None

    m = _RELATIVE_DATE_RE.search(text)
    if m:
        day_word, time_str, meridiem = m.groups()
        base_date = datetime.now().date()
        if day_word == "Yesterday":
            base_date -= timedelta(days=1)
        try:
            time_part = datetime.strptime(f"{time_str} {meridiem}", "%I:%M:%S %p").time()
        except ValueError:
            return None
        return datetime.combine(base_date, time_part)

    return None


def _clean_text(text: str | None) -> str | None:
    """Postgres text/JSON columns reject NUL bytes outright -- real forum
    posts occasionally embed one (e.g. pasted binary/garbled data), which
    would otherwise crash the insert with 'A string literal cannot contain
    NUL (0x00) characters.' before the query even reaches the DB."""
    return text.replace("\x00", "") if text else text


def list_posts(topic_id: str, page_offset: int = 0) -> list[dict]:
    """List posts on one topic page. page_offset is 0, 20, 40, ..."""
    soup = _fetch(f"{BASE_URL}?topic={topic_id}.{page_offset}")
    posts = []
    seen_msg_ids: set[str] = set()

    for anchor in soup.find_all("a", attrs={"name": re.compile(r"^msg\d+$")}):
        msg_id = anchor["name"][3:]
        if msg_id in seen_msg_ids:
            continue

        # The anchor sits right before its post's <tr>, but a page's very
        # first post also gets a duplicate "jump here" anchor at the very top
        # of the page, ahead of the pagination controls -- so the immediate
        # next <tr> isn't reliably the post row. Walk forward to the first
        # <tr> that actually contains a post (has td.poster_info).
        row = next(
            (r for r in anchor.find_all_next("tr") if r.select_one("td.poster_info")),
            None,
        )
        if row is None:
            continue
        seen_msg_ids.add(msg_id)

        author_link = row.select_one("td.poster_info a[href*='action=profile']")
        author = _clean_text(author_link.get_text(strip=True) if author_link else None)

        date_div = row.select_one("td.td_headerandpost div.smalltext")
        posted_at = _parse_post_date(date_div.get_text(strip=True)) if date_div else None

        subject_div = row.select_one("td.td_headerandpost div.subject")
        subject = _clean_text(subject_div.get_text(strip=True) if subject_div else None)

        body_div = row.select_one("div.post")
        for br in body_div.find_all("br") if body_div else []:
            br.replace_with("\n")
        body = _clean_text(body_div.get_text().strip()[:MESSAGE_BODY_CHARS] if body_div else "")

        posts.append({
            "msg_id": msg_id,
            "author": author,
            "subject": subject,
            "posted_at": posted_at,
            "body": body,
            "url": f"{BASE_URL}?topic={topic_id}.msg{msg_id}#msg{msg_id}",
        })
    return posts


def all_posts_for_topic(topic_id: str):
    """Yield every post in a topic, walking pagination until a page comes back short."""
    offset = 0
    while True:
        posts = list_posts(topic_id, page_offset=offset)
        yield from posts
        if len(posts) < POSTS_PER_PAGE:
            return
        offset += POSTS_PER_PAGE


def _post_to_row(post: dict, topic: dict, person_id: int | None) -> dict:
    return {
        "channel": CHANNEL,
        "external_id": post["msg_id"],
        "thread_id": topic["topic_id"],
        "author": post["author"],
        "person_id": person_id,
        "title": post["subject"] or topic["title"],
        "body": post["body"],
        "url": post["url"],
        "posted_at": post["posted_at"],
        "raw": Json({**post, "posted_at": post["posted_at"].isoformat() if post["posted_at"] else None,
                     "topic_id": topic["topic_id"], "topic_title": topic["title"]}),
    }


def _already_ingested(cur, external_id: str) -> bool:
    cur.execute(
        "SELECT 1 FROM messages WHERE channel = %(channel)s AND external_id = %(external_id)s",
        {"channel": CHANNEL, "external_id": external_id},
    )
    return cur.fetchone() is not None


def _get_or_create_person(cur, username: str) -> int:
    """The person this BitcoinTalk username belongs to, creating one if this
    is the first post we've seen from them."""
    cur.execute(_UPSERT_PERSON_SQL, {"username": username})
    return cur.fetchone()[0]


def backfill(max_topics: int | None = None) -> dict:
    """Walk the board page by page (whatever order SMF's default view gives
    us -- most-recent-activity first, not creation order) and upsert every
    post as its topic is reached. No upfront discovery pass: ordering isn't
    a real requirement here, since every post is checked against the DB by
    external_id before insert either way, so this is resumable and idempotent
    regardless of what order topics get processed in -- stop it any time,
    rerun later, it picks up wherever it left off (ON CONFLICT DO NOTHING is
    a backstop for the same reason, not the primary mechanism)."""
    topics_seen = posts_seen = inserted = skipped = 0

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # A second concurrent run (e.g. a Ctrl+C that didn't actually
            # kill the first process, or just starting it twice) doesn't
            # error -- it silently contends for locks on the same rows as
            # the first run, which looks exactly like a hang and is what
            # actually happened here. Fail fast instead: an advisory lock is
            # session-scoped, so it's released automatically if this process
            # dies, no manual cleanup needed.
            cur.execute("SELECT pg_try_advisory_lock(%(key)s)", {"key": _ADVISORY_LOCK_KEY})
            if not cur.fetchone()[0]:
                raise RuntimeError(
                    "another scrape_bitcointalk.py is already running against this database "
                    "-- check `ps aux | grep scrape_bitcointalk` and kill it before retrying"
                )

            for page_num, topics in enumerate(walk_board_pages()):
                if max_topics is not None and topics_seen >= max_topics:
                    break
                # The board is sorted by most-recent-activity, not creation
                # time, so a resumed run re-walks the same already-ingested
                # active topics first -- that's all-skip, zero-insert, and
                # previously produced zero log output for long stretches,
                # which is indistinguishable from actually being stuck. One
                # line per page fixes that regardless of insert activity.
                logger.info(f"board page offset={page_num * TOPICS_PER_PAGE}: {len(topics)} topics "
                            f"(so far: topics={topics_seen} inserted={inserted} skipped={skipped})")

                for topic in topics:
                    if max_topics is not None and topics_seen >= max_topics:
                        break
                    topics_seen += 1
                    for post in all_posts_for_topic(topic["topic_id"]):
                        posts_seen += 1
                        # A single topic can run thousands of posts long (seen
                        # in testing) -- without this, an all-skip topic that
                        # size produces the same "is it stuck?" silence as the
                        # per-page heartbeat above was just added to fix.
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
        description="Ingest the BitcoinTalk Development & Technical Discussion board."
    )
    parser.add_argument(
        "--max-topics", type=int, default=None,
        help="Stop after this many topics (default: no limit -- the whole board).",
    )
    args = parser.parse_args()
    backfill(max_topics=args.max_topics)


if __name__ == "__main__":
    main()
