"""Backfill the messages + people tables from the bitcoin-dev mailing list archive.

With no arguments, downloads the full archive (https://gnusha.org/pi/bitcoindev/
all.mbox.gz, ~95MB) to a temp dir, decompresses it, and ingests it. Pass a local
.mbox path to skip the download.

Safe to re-run: existing messages are never overwritten (ON CONFLICT DO NOTHING),
and the people reconciliation pass at the end is idempotent.
"""

import argparse
import gzip
import logging
import mailbox
import shutil
import sys
import tempfile
import urllib.request
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_mailing_list")

BASE_URL = "https://gnusha.org/pi/bitcoindev"
ARCHIVE_URL = f"{BASE_URL}/all.mbox.gz"
CHANNEL = "mailing_list"
MESSAGE_BODY_CHARS = 4000
_COMMIT_EVERY = 500

_INSERT_SQL = """
INSERT INTO messages (channel, external_id, thread_id, author, email, title, body, url, posted_at, raw)
VALUES (%(channel)s, %(external_id)s, %(thread_id)s, %(author)s, %(email)s, %(title)s, %(body)s, %(url)s, %(posted_at)s, %(raw)s)
ON CONFLICT (channel, external_id) DO NOTHING
"""

# People reconciliation, mirroring db/migrations/0003_people.sql: one person per
# email, display_name = the most common author spelling, skipping shared/relay
# addresses (more than 5 distinct spellings under one email -- grounded in the
# real data, where only the Google Groups relay address exceeds that). Existing
# people are left untouched (ON CONFLICT DO NOTHING), so a person's display_name
# never churns after creation.
_INSERT_PEOPLE_SQL = """
INSERT INTO people (email, display_name)
SELECT email, mode() WITHIN GROUP (ORDER BY author)
FROM messages
WHERE email IS NOT NULL
GROUP BY email
HAVING count(DISTINCT author) <= 5
ON CONFLICT (email) DO NOTHING
"""

_LINK_MESSAGES_SQL = """
UPDATE messages m SET person_id = p.id
FROM people p
WHERE m.person_id IS NULL AND m.email = p.email
"""


def _decode_payload(payload: bytes, charset: str | None) -> str:
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError):
        # Real-world mail has malformed/unrecognized charset labels (e.g. "cp 874"
        # with a stray space) that raise LookupError before decoding even starts.
        return payload.decode("utf-8", errors="replace")


def _extract_body(msg, max_chars: int) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = _decode_payload(payload, part.get_content_charset())
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = _decode_payload(payload, msg.get_content_charset())
    return body.strip()[:max_chars]


def _decode_mime_words(value: str) -> str:
    """Decode RFC 2047 encoded-word headers (e.g. "=?utf-8?b?...?=") to plain text.

    Real headers routinely mix this with non-encoded ASCII, so decode_header
    returns a list of (fragment, charset) pairs to join, not a single blob.
    """
    if not value:
        return value
    parts = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            parts.append(_decode_payload(text, charset))
        else:
            parts.append(text)
    return "".join(parts)


def _permalink_from_message_id(message_id: str) -> str | None:
    stripped = message_id.strip().strip("<>")
    if not stripped:
        return None
    return f"{BASE_URL}/{stripped.replace('/', '%2F')}/"


def _mbox_message_to_dict(msg) -> dict | None:
    message_id = msg.get("Message-Id", "")
    permalink = _permalink_from_message_id(message_id)
    if not permalink:
        return None
    return {
        "subject": _decode_mime_words(msg.get("Subject", "")),
        "from": _decode_mime_words(msg.get("From", "")),
        "date": msg.get("Date", ""),
        "message_id": message_id,
        "in_reply_to": msg.get("In-Reply-To", ""),
        "body": _extract_body(msg, MESSAGE_BODY_CHARS),
        "permalink": permalink,
    }


def _message_to_row(msg: dict) -> dict:
    author, email_addr = parseaddr(msg.get("from", ""))
    posted_at = None
    if msg.get("date"):
        try:
            posted_at = parsedate_to_datetime(msg["date"])
        except (TypeError, ValueError):
            posted_at = None

    return {
        "channel": CHANNEL,
        "external_id": msg.get("message_id") or msg["permalink"],
        "thread_id": None,
        "author": author or None,
        "email": email_addr or None,
        "title": msg.get("subject"),
        "body": msg.get("body", ""),
        "url": msg["permalink"],
        "posted_at": posted_at,
        "raw": Json(msg),
    }


def _upsert_message(cur, msg: dict) -> bool:
    cur.execute(_INSERT_SQL, _message_to_row(msg))
    return bool(cur.rowcount)


def download_archive(dest_dir: Path) -> Path:
    gz_path = dest_dir / "all.mbox.gz"
    mbox_path = dest_dir / "all.mbox"
    logger.info(f"downloading {ARCHIVE_URL} ...")
    urllib.request.urlretrieve(ARCHIVE_URL, gz_path)
    logger.info(f"downloaded {gz_path.stat().st_size / 1_000_000:.0f} MB, decompressing...")
    with gzip.open(gz_path, "rb") as src, open(mbox_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    gz_path.unlink()
    logger.info(f"decompressed to {mbox_path} ({mbox_path.stat().st_size / 1_000_000:.0f} MB)")
    return mbox_path


def reconcile_people(conn) -> dict:
    """Create people for any new emails and link unlinked messages to them."""
    with conn.cursor() as cur:
        cur.execute(_INSERT_PEOPLE_SQL)
        people_created = cur.rowcount
        cur.execute(_LINK_MESSAGES_SQL)
        messages_linked = cur.rowcount
    conn.commit()
    logger.info(f"reconciled people: created {people_created}, linked {messages_linked} messages")
    return {"people_created": people_created, "messages_linked": messages_linked}


def backfill(mbox_path: str) -> dict:
    mbox = mailbox.mbox(mbox_path)
    seen = inserted = skipped = 0

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for msg in mbox:
                seen += 1
                row_msg = _mbox_message_to_dict(msg)
                if row_msg is None:
                    skipped += 1
                    continue
                if _upsert_message(cur, row_msg):
                    inserted += 1
                else:
                    skipped += 1

                if seen % _COMMIT_EVERY == 0:
                    conn.commit()
                    logger.info(f"processed {seen} (inserted={inserted}, skipped={skipped})")

            conn.commit()

        reconciled = reconcile_people(conn)
    finally:
        conn.close()

    logger.info(f"done: processed {seen}, inserted {inserted}, skipped {skipped}")
    return {"processed": seen, "inserted": inserted, "skipped": skipped, **reconciled}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill the messages and people tables from the bitcoin-dev "
        "mailing list archive. Downloads the full archive when no local .mbox is given."
    )
    parser.add_argument(
        "mbox_path", nargs="?", default=None,
        help=f"Path to a local .mbox file (default: download {ARCHIVE_URL})",
    )
    args = parser.parse_args()

    if args.mbox_path:
        backfill(args.mbox_path)
    else:
        with tempfile.TemporaryDirectory(prefix="bitcoindev-mbox-") as tmp:
            backfill(str(download_archive(Path(tmp))))


if __name__ == "__main__":
    main()
