import argparse
import logging
import mailbox
import sys
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_mailing_list")

BASE_URL = "https://gnusha.org/pi/bitcoindev"
CHANNEL = "mailing_list"
MESSAGE_BODY_CHARS = 4000
_COMMIT_EVERY = 500

_INSERT_SQL = """
INSERT INTO messages (channel, external_id, thread_id, author, email, title, body, url, posted_at, raw)
VALUES (%(channel)s, %(external_id)s, %(thread_id)s, %(author)s, %(email)s, %(title)s, %(body)s, %(url)s, %(posted_at)s, %(raw)s)
ON CONFLICT (channel, external_id) DO NOTHING
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
        "subject": msg.get("Subject", ""),
        "from": msg.get("From", ""),
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
    finally:
        conn.close()

    logger.info(f"done: processed {seen}, inserted {inserted}, skipped {skipped}")
    return {"processed": seen, "inserted": inserted, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill the messages table from a local bitcoin-dev mbox export "
        "(e.g. https://gnusha.org/pi/bitcoindev/all.mbox.gz, gunzipped)."
    )
    parser.add_argument("mbox_path", help="Path to a local .mbox file")
    args = parser.parse_args()
    backfill(args.mbox_path)


if __name__ == "__main__":
    main()
