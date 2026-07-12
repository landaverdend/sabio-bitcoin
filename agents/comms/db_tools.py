"""DB-backed search tools for the comms agent.

resolve() is generated from a small entity registry (the trustsell ontology
pattern): each entity declares its table, label expression, and which columns
get exact vs fuzzy matching, and the SQL is assembled from those declarations
at import time. Adding a resolvable entity is a registry entry, not a new
hand-written query.

SECURITY: registry values are interpolated into SQL as identifiers/expressions.
They are developer-defined config -- never populate them from user input. User
input is always passed as bound params.
"""

import re
from dataclasses import dataclass
from typing import Optional

from db.client import get_connection

# Score tiers, highest first: an exact unique identifier (email) = 1.0; an
# exact name/title match = _EXACT_NAME_SCORE (strong, but names collide so it
# stays below a unique id); a fuzzy match = _FUZZY_WEIGHT * similarity() (0..1),
# which caps below the exact tiers.
_EXACT_NAME_SCORE = 0.9
_FUZZY_WEIGHT = 0.6
_MAX_RESULTS = 30
_MAX_THREAD_MESSAGES = 50


@dataclass(frozen=True)
class _Entity:
    type: str                      # agent-facing type + id prefix, e.g. "person"
    table: str
    label_expr: str                # SQL expression for the human label
    id_col: str = "id"
    exact_cols: tuple = ()         # unique identifiers (email) -> score 1.0
    fuzzy_cols: tuple = ()         # trigram-matched cols -> exact 0.9 / fuzzy tiers


# What resolve() can find:
# - person: one row per reconciled identity (db/migrations/0003_people.sql) --
#   already deduplicated across name-spelling variants, relay addresses excluded.
# - message: found by title only. Content search is deliberately NOT a resolve
#   branch: ts_rank scores don't compare fairly against trigram similarity, and
#   merging them once buried a real sender match under dozens of messages that
#   merely mentioned the queried word. That lives in search_messages() instead.
_ENTITIES = (
    _Entity(type="person", table="people",
            label_expr="coalesce(display_name, '(unknown)') || ' -- ' || email",
            exact_cols=("email",), fuzzy_cols=("display_name", "email")),
    _Entity(type="message", table="messages",
            label_expr="title || ' -- ' || coalesce(author, '(unknown)')",
            fuzzy_cols=("title",)),
)


def _branches(entity: _Entity) -> list[str]:
    """Generate the exact + fuzzy SELECT branches for one entity. All branches
    emit the same (id, type, label, score) shape so they UNION cleanly.

    `%%` is an escaped literal `%` (the pg_trgm operator); `%(name)s` are bound
    params filled at execute().
    """
    id_expr = f"'{entity.type}:' || {entity.id_col}::text"
    out: list[str] = []

    if entity.exact_cols:
        where = " OR ".join(f"lower({c}) = %(q)s" for c in entity.exact_cols)
        out.append(
            f"    SELECT {id_expr} AS id, '{entity.type}' AS type, "
            f"{entity.label_expr} AS label, 1.0 AS score\n"
            f"    FROM {entity.table} WHERE {where}"
        )

    if entity.fuzzy_cols:
        exact = " OR ".join(f"lower({c}) = %(q)s" for c in entity.fuzzy_cols)
        out.append(
            f"    SELECT {id_expr}, '{entity.type}', {entity.label_expr}, %(exact_name_score)s\n"
            f"    FROM {entity.table} WHERE {exact}"
        )
        match = " OR ".join(f"{c} %% %(raw_q)s" for c in entity.fuzzy_cols)
        sims = ", ".join(f"similarity({c}, %(raw_q)s)" for c in entity.fuzzy_cols)
        sim_expr = f"GREATEST({sims})" if len(entity.fuzzy_cols) > 1 else sims
        out.append(
            f"    SELECT {id_expr}, '{entity.type}', {entity.label_expr}, "
            f"%(fuzzy_weight)s * {sim_expr}\n"
            f"    FROM {entity.table} WHERE {match}"
        )
    return out


def _build_resolve_sql() -> str:
    branches = [b for e in _ENTITIES for b in _branches(e)]
    union = "\n    UNION ALL\n".join(branches)
    return f"""
WITH matches AS (
{union}
),
ranked AS (
    SELECT DISTINCT ON (id) id, type, label, score
    FROM matches
    ORDER BY id, score DESC
)
SELECT id, type, label, score
FROM ranked
ORDER BY score DESC, label
LIMIT %(limit)s
"""


# Built once at import from the registry.
_RESOLVE_SQL = _build_resolve_sql()

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


def _query(sql: str, params: dict) -> list[tuple]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def resolve(query: str, limit: int = 10) -> list[dict]:
    """Find the person or specific message a human phrase might refer to.

    Searches known people (name/email) and message titles across the local
    bitcoin-dev mailing list archive. Returns a ranked list of candidates to
    disambiguate between -- it does NOT fetch content. A 'person:...'
    candidate's person_id feeds straight into search_messages; a 'message:...'
    candidate's id feeds into get_message. Not every sender resolves to a
    person (shared/relay addresses are excluded) -- if nothing matches a name,
    fall back to search_messages(author=...) over the raw sender field.
    For "find messages about X" (topic, not a specific person or message),
    use search_messages instead.
    """
    q = (query or "").strip()
    if not q:
        return []
    rows = _query(_RESOLVE_SQL, {
        "q": q.lower(),
        "raw_q": q,
        "exact_name_score": _EXACT_NAME_SCORE,
        "fuzzy_weight": _FUZZY_WEIGHT,
        "limit": max(1, min(int(limit or 10), _MAX_RESULTS)),
    })
    candidates = []
    for id_, type_, label, score in rows:
        candidate = {"id": id_, "type": type_, "label": label, "score": round(float(score), 3)}
        if type_ == "person":
            candidate["person_id"] = int(id_.partition(":")[2])
        candidates.append(candidate)
    return candidates


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
    rows = _query(sql, params)
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
    rows = _query(
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
    rows = _query("SELECT title FROM messages WHERE id = %(pk)s", {"pk": pk})
    if not rows:
        raise ValueError(f"no message with id {pk}")
    core_subject = _normalize_subject(rows[0][0])
    if not core_subject:
        return []

    rows = _query(
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
