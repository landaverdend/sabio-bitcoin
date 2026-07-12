import gzip
import mailbox
import os
import tempfile
import xml.etree.ElementTree as ET
from email import message_from_bytes

import requests

BASE_URL = "https://gnusha.org/pi/bitcoindev"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_MAX_RESULTS = 30
_MESSAGE_BODY_CHARS = 4000
_THREAD_MESSAGE_BODY_CHARS = 1200
_MAX_THREAD_MESSAGES = 15


def _require_local_permalink(permalink: str) -> str:
    if not permalink.startswith(BASE_URL):
        raise ValueError(f"permalink must be a {BASE_URL} URL, got: {permalink}")
    return permalink.rstrip("/")


def _extract_body(msg, max_chars: int) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return body.strip()[:max_chars]


def _parse_atom_entries(xml_bytes: bytes, max_results: int) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    results = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        link_el = entry.find(f"{_ATOM_NS}link")
        author_el = entry.find(f"{_ATOM_NS}author/{_ATOM_NS}name")
        results.append({
            "title": (entry.findtext(f"{_ATOM_NS}title") or "").strip(),
            "author": (author_el.text if author_el is not None else "").strip(),
            "updated": entry.findtext(f"{_ATOM_NS}updated"),
            "permalink": link_el.get("href") if link_el is not None else None,
        })
        if len(results) >= max_results:
            break
    return results


def search_mailing_list(query: str, max_results: int = 10) -> list[dict]:
    """Search the bitcoin-dev mailing list archive, newest match first."""
    max_results = min(max_results, _MAX_RESULTS)
    resp = requests.get(f"{BASE_URL}/", params={"q": query, "x": "A"}, timeout=15)
    resp.raise_for_status()
    return _parse_atom_entries(resp.content, max_results)


def get_recent_messages(max_count: int = 10) -> list[dict]:
    """List the most recently posted messages on the bitcoin-dev mailing list."""
    max_count = min(max_count, _MAX_RESULTS)
    resp = requests.get(f"{BASE_URL}/new.atom", timeout=15)
    resp.raise_for_status()
    return _parse_atom_entries(resp.content, max_count)


def get_message(permalink: str) -> dict:
    """Fetch and parse a single mailing list message given its permalink URL."""
    url = _require_local_permalink(permalink) + "/raw"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    msg = message_from_bytes(resp.content)

    return {
        "subject": msg.get("Subject", ""),
        "from": msg.get("From", ""),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-Id", ""),
        "in_reply_to": msg.get("In-Reply-To", ""),
        "body": _extract_body(msg, _MESSAGE_BODY_CHARS),
        "permalink": permalink,
    }


def get_thread(permalink: str, max_messages: int = _MAX_THREAD_MESSAGES) -> list[dict]:
    """Fetch and parse an entire discussion thread given the permalink of any message in it, in order."""
    max_messages = min(max_messages, _MAX_THREAD_MESSAGES)
    url = _require_local_permalink(permalink) + "/t.mbox.gz"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    raw_mbox = gzip.decompress(resp.content)

    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as f:
        f.write(raw_mbox)
        tmp_path = f.name

    try:
        mbox = mailbox.mbox(tmp_path)
        messages = []
        for msg in mbox:
            messages.append({
                "subject": msg.get("Subject", ""),
                "from": msg.get("From", ""),
                "date": msg.get("Date", ""),
                "body": _extract_body(msg, _THREAD_MESSAGE_BODY_CHARS),
            })
            if len(messages) >= max_messages:
                break
        return messages
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    for r in search_mailing_list("taproot", max_results=3):
        print(r["title"], "-", r["author"])
