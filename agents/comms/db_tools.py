"""DB-backed tools specific to comms: message content search, not identity
resolution (see agents/shared/resolve.py for that -- it's used by other
agents too, not comms-specific)."""

import re
from typing import Optional

from agents.shared.resolve import run_query

_MAX_RESULTS = 30
_MAX_THREAD_MESSAGES = 50

# Mailing-list threads keep the same core subject through "Re:"/"Fwd:" reply
# prefixes and "[list-tag]" markers, so stripping those and substring-matching
# reconstructs a thread without a populated thread_id column. Approximate: two
# unrelated threads sharing a subject would be merged.
_SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:(?:Re|Fwd?|AW)\s*:\s*|\[[^\]]*\]\s*)+", re.IGNORECASE)


def _normalize_subject(title: Optional[str]) -> str:
    if not title:
        return ""
    return _SUBJECT_PREFIX_RE.sub("", title).strip().lower()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_messages(
    query: Optional[str] = None,
    person_id: Optional[int] = None,
    author: Optional[str] = None,
    email: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    order: str = "relevance",
    limit: int = 10,
) -> list[dict]:
    """Search/list messages, filterable by topic, sender, and/or date range.

    All filters are optional and combine with AND:
      query: full-text search over title+body (stemmed, e.g. "taproot" matches
        "taproots"). Omit to just list by sender and/or date instead.
      person_id: scope to one resolved identity -- from a resolve() 'person:...'
        candidate. Preferred over author/email: it already covers that person's
        known name-spelling variants.
      author, email: fallback sender scoping for senders resolve() doesn't
        cover (e.g. relay addresses) -- exact match on the raw message fields.
      after, before: ISO date strings (e.g. "2015-01-01"); inclusive of
        `after`, exclusive of `before`.
      order: 'relevance' (default; falls back to newest-first without a query),
        'asc' (oldest first), or 'desc' (newest first).

    Returns summaries with a short body snippet -- pass a hit's id to
    get_message for full content. For "who is X", use resolve instead.
    """
    q = (query or "").strip() or None
    params: dict = {"limit": max(1, min(int(limit or 10), _MAX_RESULTS))}
    filters: list[str] = []

    if q:
        filters.append("search_vector @@ websearch_to_tsquery('english', %(q)s)")
        params["q"] = q
        score_expr = "LEAST(1.0, ts_rank_cd(search_vector, websearch_to_tsquery('english', %(q)s)))"
    else:
        score_expr = "NULL::real"
    if person_id is not None:
        filters.append("person_id = %(person_id)s")
        params["person_id"] = person_id
    if author:
        filters.append("author = %(author)s")
        params["author"] = author
    if email:
        filters.append("email = %(email)s")
        params["email"] = email
    if after:
        filters.append("posted_at >= %(after)s::timestamptz")
        params["after"] = after
    if before:
        filters.append("posted_at < %(before)s::timestamptz")
        params["before"] = before

    if order == "asc":
        order_sql = "posted_at ASC"
    elif order == "desc":
        order_sql = "posted_at DESC"
    else:  # relevance -- meaningless without a query, so fall back to newest-first
        order_sql = "score DESC NULLS LAST, posted_at DESC" if q else "posted_at DESC"

    where = " AND ".join(filters) if filters else "TRUE"
    sql = f"""
SELECT id, title, author, email, person_id, posted_at, left(body, 200) AS snippet,
       {score_expr} AS score
FROM messages
WHERE {where}
ORDER BY {order_sql}
LIMIT %(limit)s
"""
    rows = run_query(sql, params)
    return [
        {
            "id": f"message:{r[0]}",
            "title": r[1],
            "author": r[2],
            "email": r[3],
            "person_id": r[4],
            "posted_at": r[5].isoformat() if r[5] else None,
            "snippet": r[6],
            "score": round(float(r[7]), 3) if r[7] is not None else None,
        }
        for r in rows
    ]


def get_message(message_id: str) -> dict:
    """Fetch full content for a message, given a 'message:<id>' id from resolve()/search_messages()."""
    pk = message_id.removeprefix("message:")
    rows = run_query(
        "SELECT id, author, email, title, body, url, posted_at, thread_id, person_id "
        "FROM messages WHERE id = %(pk)s",
        {"pk": pk},
    )
    if not rows:
        raise ValueError(f"no message with id {pk}")
    r = rows[0]
    return {
        "id": r[0],
        "author": r[1],
        "email": r[2],
        "title": r[3],
        "body": r[4],
        "url": r[5],
        "posted_at": r[6].isoformat() if r[6] else None,
        "thread_id": r[7],
        "person_id": r[8],
    }


def get_thread(message_id: str, limit: int = _MAX_THREAD_MESSAGES) -> list[dict]:
    """Find the discussion thread a message belongs to, oldest first.

    Approximate: matches by core subject line (stripping "Re:"/"[list-tag]"
    prefixes), since thread linkage isn't otherwise tracked.
    """
    pk = message_id.removeprefix("message:")
    rows = run_query("SELECT title FROM messages WHERE id = %(pk)s", {"pk": pk})
    if not rows:
        raise ValueError(f"no message with id {pk}")
    core_subject = _normalize_subject(rows[0][0])
    if not core_subject:
        return []

    rows = run_query(
        "SELECT id, title, author, posted_at, left(body, 200) AS snippet "
        "FROM messages WHERE lower(title) LIKE %(pattern)s ESCAPE '\\' "
        "ORDER BY posted_at ASC LIMIT %(limit)s",
        {
            "pattern": f"%{_escape_like(core_subject)}%",
            "limit": max(1, min(int(limit or _MAX_THREAD_MESSAGES), _MAX_THREAD_MESSAGES)),
        },
    )
    return [
        {
            "id": f"message:{r[0]}",
            "title": r[1],
            "author": r[2],
            "posted_at": r[3].isoformat() if r[3] else None,
            "snippet": r[4],
        }
        for r in rows
    ]
