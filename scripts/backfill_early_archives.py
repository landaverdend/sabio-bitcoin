"""Backfill the original 2008-2010 Bitcoin email chains, complete with replies.

Three sources, one channel each:
- cryptography (metzdowd): the whitepaper announcement + full discussion threads,
  from the list's own monthly mbox archives (Oct 2008 - Feb 2009, filtered to
  Bitcoin-subject messages). Real addresses and Message-Ids.
- bitcoin-list (SourceForge): the complete list (2008-2015), from the
  viresinnumeris.fr reconstruction of the deleted SF archives (via the Wayback
  Machine). SF truncated sender addresses ("satoshi@vi..."), so email stays NULL.
- p2p-research: archives are gone; the Nakamoto Institute's 9 curated messages
  are all that's recoverable.

Replaces the earlier NI-curated rows for cryptography/bitcoin-list (a Satoshi-
centric selection) with the full chains; deletes those rows on each run before
re-ingesting. Safe to re-run.
"""

import gzip
import hashlib
import json
import logging
import mailbox
import re
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backfill_mailing_list import _decode_mime_words, _extract_body, reconcile_people  # noqa: E402
from db.client import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_early_archives")

MESSAGE_BODY_CHARS = 4000

METZDOWD_BASE = "https://www.metzdowd.com/pipermail/cryptography"
METZDOWD_MONTHS = ("2008-October", "2008-November", "2008-December", "2009-January", "2009-February")
BITCOIN_LIST_URL = "https://viresinnumeris.fr/bitcoin-list-archive.txt"
NI_DATA_URL = (
    "https://raw.githubusercontent.com/nakamotoinstitute/nakamotoinstitute.org"
    "/master/server/data/emails.json"
)

_INSERT_SQL = """
INSERT INTO messages (channel, external_id, thread_id, author, email, title, body, url, posted_at, raw)
VALUES (%(channel)s, %(external_id)s, %(thread_id)s, %(author)s, %(email)s, %(title)s, %(body)s, %(url)s, %(posted_at)s, %(raw)s)
ON CONFLICT (channel, external_id) DO NOTHING
"""

# The NI-curated rows all carry a 'source_id' key in raw (every NI record has
# one; 'satoshi_id' exists only on Satoshi-authored records, which is why an
# earlier version of this predicate missed the replies). The full-chain rows
# ingested here don't have it. Scoped to the two superseded channels.
_DELETE_CURATED_SQL = """
DELETE FROM messages
WHERE channel IN ('cryptography', 'bitcoin-list') AND raw ? 'source_id'
"""

# Pipermail obfuscates senders as "user at host.com (Display Name)".
_PIPERMAIL_FROM_RE = re.compile(r"^\s*(\S+ at \S+)\s*\((.*)\)\s*$")

# viresinnumeris format: messages separated by "---" lines, each starting with
# a subject line then "From: <sender> - YYYY-MM-DD HH:MM:SS".
_VIN_HEADER_RE = re.compile(
    r"\s*(?P<subject>[^\n]+)\nFrom: (?P<from>.*?) - (?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\n(?P<body>.*)",
    re.S,
)


def _insert_rows(rows: list[dict], label: str) -> tuple[int, int]:
    inserted = skipped = 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(_INSERT_SQL, row)
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
        conn.commit()
    finally:
        conn.close()
    logger.info(f"{label}: inserted {inserted}, skipped {skipped}")
    return inserted, skipped


def _parse_pipermail_from(value: str) -> tuple[str | None, str | None]:
    m = _PIPERMAIL_FROM_RE.match(_decode_mime_words(value or ""))
    if m:
        return m.group(2).strip() or None, m.group(1).replace(" at ", "@")
    author, email = parseaddr(value or "")
    return author or None, email or None


def metzdowd_rows() -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory(prefix="metzdowd-") as tmp:
        for month in METZDOWD_MONTHS:
            url = f"{METZDOWD_BASE}/{month}.txt.gz"
            gz_path = Path(tmp) / f"{month}.txt.gz"
            txt_path = Path(tmp) / f"{month}.txt"
            urllib.request.urlretrieve(url, gz_path)
            txt_path.write_bytes(gzip.decompress(gz_path.read_bytes()))

            for msg in mailbox.mbox(txt_path):
                subject = _decode_mime_words(msg.get("Subject") or "")
                if "bitcoin" not in subject.lower():
                    continue
                author, email = _parse_pipermail_from(msg.get("From", ""))
                message_id = (msg.get("Message-Id") or "").strip()
                posted_at = None
                if msg.get("Date"):
                    try:
                        posted_at = parsedate_to_datetime(msg["Date"])
                    except (TypeError, ValueError):
                        pass
                rows.append({
                    "channel": "cryptography",
                    "external_id": message_id or f"{month}:{subject}:{msg.get('Date', '')}",
                    "thread_id": None,
                    "author": author,
                    "email": email,
                    "title": subject,
                    "body": _extract_body(msg, MESSAGE_BODY_CHARS),
                    # No canonical per-message URL is derivable from the mbox;
                    # point at the month archive with the message-id as fragment.
                    "url": f"{METZDOWD_BASE}/{month}/#{message_id.strip('<>')}",
                    "posted_at": posted_at,
                    "raw": Json({"source": "metzdowd", "month": month,
                                 "from": msg.get("From", ""), "message_id": message_id}),
                })
    return rows


def bitcoin_list_rows() -> list[dict]:
    with urllib.request.urlopen(BITCOIN_LIST_URL) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    # Re-join messages whose bodies contained a literal "---" divider: any block
    # that doesn't start with a subject + From header is a continuation.
    messages: list[dict] = []
    for block in re.split(r"\n---\n", text)[1:]:  # [0] is the file preamble
        m = _VIN_HEADER_RE.match(block)
        if m:
            messages.append(m.groupdict())
        elif messages:
            messages[-1]["body"] += "\n---\n" + block

    rows = []
    for msg in messages:
        author, truncated_email = parseaddr(msg["from"])
        digest = hashlib.sha1(f"{msg['subject']}|{msg['from']}|{msg['date']}".encode()).hexdigest()
        rows.append({
            "channel": "bitcoin-list",
            "external_id": digest,
            "thread_id": None,
            "author": author or None,
            # SF truncated addresses ("satoshi@vi...") aren't real -- keep them
            # in raw, but never as email, so people-linking can't key on garbage.
            "email": None,
            "title": msg["subject"],
            "body": msg["body"].strip()[:MESSAGE_BODY_CHARS],
            "url": f"{BITCOIN_LIST_URL}#{digest[:16]}",
            "posted_at": datetime.strptime(msg["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
            "raw": Json({"source": "viresinnumeris", "from": msg["from"],
                         "truncated_email": truncated_email}),
        })
    return rows


def p2p_research_rows() -> list[dict]:
    with urllib.request.urlopen(NI_DATA_URL) as resp:
        records = json.load(resp)
    rows = []
    for record in records:
        if record["source"] != "p2p-research":
            continue
        rows.append({
            "channel": "p2p-research",
            "external_id": record["url"],
            "thread_id": f"ni:{record['thread_id']}",
            "author": record.get("sent_from") or None,
            "email": None,
            "title": record.get("subject"),
            "body": (record.get("text") or "")[:MESSAGE_BODY_CHARS],
            "url": record["url"],
            "posted_at": datetime.fromisoformat(record["date"]),
            "raw": Json(record),
        })
    return rows


def backfill() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_DELETE_CURATED_SQL)
            if cur.rowcount:
                logger.info(f"removed {cur.rowcount} NI-curated rows superseded by full chains")
        conn.commit()
    finally:
        conn.close()

    _insert_rows(metzdowd_rows(), "cryptography (metzdowd, full chains)")
    _insert_rows(bitcoin_list_rows(), "bitcoin-list (viresinnumeris reconstruction)")
    _insert_rows(p2p_research_rows(), "p2p-research (NI curated)")

    conn = get_connection()
    try:
        reconcile_people(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    backfill()
