"""Scrape BitcoinTalk's Development & Technical Discussion board (board=6).

No API exists, so this parses SMF's HTML directly. Two levels of pagination:
board index (40 topics/page, offset step 40) and each topic's posts (20
posts/page, offset step 20). robots.txt has no disallow rules, but there's
also no stated crawl-delay -- REQUEST_DELAY below is a conservative default
picked ourselves, not one the site told us to use.

Currently print-only: prints what it would ingest instead of writing to the
database, so the extraction logic can be checked against real output before
any data lands in `messages`. No DB writes happen in this version.
"""

import re
import time
import urllib.request
from datetime import datetime

from bs4 import BeautifulSoup

BASE_URL = "https://bitcointalk.org/index.php"
BOARD_ID = 6  # Development & Technical Discussion
TOPICS_PER_PAGE = 40
REQUEST_DELAY = 2.0  # seconds between requests -- our own conservative choice
USER_AGENT = "sabio-bitcoin-research/0.1 (+local hackathon project; contact via github)"

_TOPIC_LINK_RE = re.compile(r"topic=(\d+)\.0\b")
_DATE_FORMAT = "%B %d, %Y, %I:%M:%S %p"
# Edited posts append "Last edit: <date> by <user>" to the same div with no
# separator ("...01:19:33 PMLast edit: February..."), so the post date has to
# be extracted, not parsed as the whole div text.
_DATE_RE = re.compile(r"[A-Z][a-z]+ \d{1,2}, \d{4}, \d{2}:\d{2}:\d{2} [AP]M")


def _fetch(url: str) -> BeautifulSoup:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8", errors="replace")
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
        title = a.get_text(strip=True)
        if topic_id not in seen and title and not title.isdigit():
            seen[topic_id] = {"topic_id": topic_id, "title": title, "url": href}
    return list(seen.values())


def _parse_post_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), _DATE_FORMAT)
    except ValueError:
        return None


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
        author = author_link.get_text(strip=True) if author_link else None

        date_div = row.select_one("td.td_headerandpost div.smalltext")
        posted_at = _parse_post_date(date_div.get_text(strip=True)) if date_div else None

        body_div = row.select_one("div.post")
        for br in body_div.find_all("br") if body_div else []:
            br.replace_with("\n")
        body = body_div.get_text().strip() if body_div else ""

        posts.append({
            "msg_id": msg_id,
            "author": author,
            "posted_at": posted_at,
            "body": body,
            "url": f"{BASE_URL}?topic={topic_id}.msg{msg_id}#msg{msg_id}",
        })
    return posts


if __name__ == "__main__":
    print(f"=== board {BOARD_ID}, page 1 topics ===")
    topics = list_topics(page_offset=0)
    print(f"found {len(topics)} topics\n")
    for t in topics[:10]:
        print(t)

    print(f"\n=== first topic's posts (page 1) ===")
    first = topics[0]
    print(f"topic: {first['title']} (id={first['topic_id']})\n")
    posts = list_posts(first["topic_id"], page_offset=0)
    print(f"found {len(posts)} posts\n")
    for p in posts:
        print(f"[{p['posted_at']}] {p['author']} (msg{p['msg_id']})")
        print(f"  {p['body'][:150]!r}")
        print(f"  {p['url']}")
        print()
