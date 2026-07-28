"""DB-backed tools for clean Bitcoin Core IRC messages from gnusha.org."""

from typing import Optional

from agents.shared.resolve import MEMBER_IDS_CTE, run_query

_MAX_RESULTS = 30
_MAX_CONTEXT_EVENTS = 12
_CHANNELS = frozenset({"bitcoin-core-dev", "bitcoin-core-pr-reviews"})
_CONTEXT_KINDS = frozenset(
    {
        "github_pr",
        "github_issue",
        "bip",
        "commit",
        "weekly_meeting",
        "other",
    }
)


def _normalized_channel(channel: Optional[str]) -> Optional[str]:
    if channel is None:
        return None
    normalized = channel.strip().removeprefix("#")
    if normalized not in _CHANNELS:
        supported = ", ".join(f"#{name}" for name in sorted(_CHANNELS))
        raise ValueError(f"unsupported IRC channel; use one of: {supported}")
    return normalized


def _normalized_context_kind(context_kind: Optional[str]) -> Optional[str]:
    if context_kind is None:
        return None
    normalized = context_kind.strip().lower()
    if normalized not in _CONTEXT_KINDS:
        supported = ", ".join(sorted(_CONTEXT_KINDS))
        raise ValueError(f"unsupported IRC context kind; use one of: {supported}")
    return normalized


def _event_id(event_id: str) -> int:
    raw_id = str(event_id).removeprefix("irc_event:")
    if not raw_id.isdigit() or int(raw_id) < 1:
        raise ValueError("IRC event id must look like irc_event:123")
    return int(raw_id)


def _event_result(row: tuple) -> dict:
    title = row[12]
    if not title:
        title = f"#{row[1]} IRC — {row[2].isoformat()}"
    return {
        "id": f"irc_event:{row[0]}",
        "channel": row[1],
        "external_id": f"gnusha:{row[1]}:{row[2].isoformat()}:{row[3]}",
        "author": row[6],
        "email": None,
        "title": title,
        "body": row[8],
        "url": row[15],
        "posted_at": row[4].isoformat() if row[4] else None,
        "thread_id": row[11],
        "person_id": row[9],
        "person_display_name": row[10],
        "event_type": row[5],
        "normalized_nick": row[7],
        "context_kind": row[14],
        "context_key": row[11],
        "context_title": row[12],
        "context_url": row[13],
        "line_number": row[3],
        "log_date": row[2].isoformat(),
        "source_file_sha": row[16],
        "raw_line": row[17],
    }


_EVENT_SELECT = """
SELECT e.id, e.channel, e.log_date, e.line_number, e.posted_at,
       e.event_type, e.nick, e.normalized_nick, e.body, e.person_id,
       p.display_name, e.context_key, e.context_title, e.context_url,
       e.context_kind, e.source_url, e.source_file_sha, e.raw_line
FROM irc_events e
LEFT JOIN people p ON p.id = e.person_id
"""


def search_irc(
    query: Optional[str] = None,
    person_id: Optional[int] = None,
    nick: Optional[str] = None,
    channel: Optional[str] = None,
    context_kind: Optional[str] = None,
    context_key: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    order: str = "relevance",
    limit: int = 10,
) -> list[dict]:
    """Search clean human IRC messages ingested from gnusha.org.

    The archive contains only #bitcoin-core-dev and
    #bitcoin-core-pr-reviews. Join/part/quit events, log markers, meeting
    boundary commands, known bots, and empty messages were removed during
    ingestion.

    All filters are optional and combine with AND:
      query: full-text search over the IRC message body.
      person_id: scope to a resolved person and every row in their canonical
        identity group.
      nick: exact case-insensitive IRC nickname.
      channel: bitcoin-core-dev or bitcoin-core-pr-reviews, with or without #.
      context_kind: github_pr, github_issue, bip, commit, weekly_meeting, or other.
      context_key: exact primary topic, such as bitcoin/bitcoin#31664 or bip:324.
      after, before: ISO dates; inclusive after and exclusive before.
      order: relevance, asc, or desc.

    Returns short discovery snippets. Pass a hit's id to get_irc_event for one
    complete message or get_irc_context for the surrounding exchange.
    """
    q = (query or "").strip() or None
    normalized_channel = _normalized_channel(channel)
    normalized_kind = _normalized_context_kind(context_kind)
    params: dict = {"limit": max(1, min(int(limit or 10), _MAX_RESULTS))}
    filters = ["e.source = 'gnusha'"]
    cte = ""

    if q:
        filters.append("e.search_vector @@ websearch_to_tsquery('english', %(q)s)")
        params["q"] = q
        score_expr = (
            "LEAST(1.0, ts_rank_cd("
            "e.search_vector, websearch_to_tsquery('english', %(q)s)))"
        )
    else:
        score_expr = "NULL::real"
    if person_id is not None:
        cte = f"WITH {MEMBER_IDS_CTE}"
        filters.append("e.person_id IN (SELECT id FROM member_ids)")
        params["id"] = person_id
    if nick:
        filters.append("e.normalized_nick = lower(%(nick)s)")
        params["nick"] = nick.strip().lstrip("~&@%+")
    if normalized_channel:
        filters.append("e.channel = %(channel)s")
        params["channel"] = normalized_channel
    if normalized_kind:
        filters.append("e.context_kind = %(context_kind)s")
        params["context_kind"] = normalized_kind
    if context_key:
        filters.append("e.context_key = %(context_key)s")
        params["context_key"] = context_key.strip()
    if after:
        filters.append("e.posted_at >= %(after)s::timestamptz")
        params["after"] = after
    if before:
        filters.append("e.posted_at < %(before)s::timestamptz")
        params["before"] = before

    if order == "asc":
        order_sql = "e.posted_at ASC, e.line_number ASC"
    elif order == "desc":
        order_sql = "e.posted_at DESC, e.line_number DESC"
    else:
        order_sql = (
            "score DESC NULLS LAST, e.posted_at DESC, e.line_number DESC"
            if q
            else "e.posted_at DESC, e.line_number DESC"
        )

    sql = f"""
{cte}
SELECT e.id, e.channel, e.nick, e.person_id, e.posted_at, e.event_type,
       left(e.body, 240) AS snippet, e.context_kind, e.context_key,
       e.context_title, e.context_url, e.source_url, {score_expr} AS score
FROM irc_events e
WHERE {" AND ".join(filters)}
ORDER BY {order_sql}
LIMIT %(limit)s
"""
    rows = run_query(sql, params)
    return [
        {
            "id": f"irc_event:{row[0]}",
            "channel": row[1],
            "nick": row[2],
            "person_id": row[3],
            "posted_at": row[4].isoformat() if row[4] else None,
            "event_type": row[5],
            "snippet": row[6],
            "context_kind": row[7],
            "context_key": row[8],
            "context_title": row[9],
            "context_url": row[10],
            "source_url": row[11],
            "score": round(float(row[12]), 3) if row[12] is not None else None,
        }
        for row in rows
    ]


def get_irc_event(event_id: str) -> dict:
    """Fetch one complete IRC message from a search_irc hit."""
    pk = _event_id(event_id)
    rows = run_query(_EVENT_SELECT + " WHERE e.id = %(pk)s", {"pk": pk})
    if not rows:
        raise ValueError(f"no IRC event with id {pk}")
    return _event_result(rows[0])


def get_irc_context(
    event_id: str,
    before: int = 4,
    after: int = 4,
) -> dict:
    """Fetch a clean human-message transcript around one search_irc hit.

    Context stays within the same channel and daily Gnusha log. `before` and
    `after` count retained human messages, not raw log lines, so filtered bot
    and connection noise never consumes the context window.
    """
    pk = _event_id(event_id)
    before_count = max(0, min(int(before or 0), _MAX_CONTEXT_EVENTS))
    after_count = max(0, min(int(after or 0), _MAX_CONTEXT_EVENTS))
    focus_rows = run_query(
        """
        SELECT source, channel, log_date
        FROM irc_events
        WHERE id = %(pk)s
        """,
        {"pk": pk},
    )
    if not focus_rows:
        raise ValueError(f"no IRC event with id {pk}")
    source, channel, log_date = focus_rows[0]

    sql = """
WITH ranked AS (
    SELECT e.id, e.channel, e.log_date, e.line_number, e.posted_at,
           e.event_type, e.nick, e.normalized_nick, e.body, e.person_id,
           p.display_name, e.context_key, e.context_title, e.context_url,
           e.context_kind, e.source_url, e.source_file_sha, e.raw_line,
           row_number() OVER (ORDER BY e.line_number) AS sequence
    FROM irc_events e
    LEFT JOIN people p ON p.id = e.person_id
    WHERE e.source = %(source)s
      AND e.channel = %(channel)s
      AND e.log_date = %(log_date)s
),
focus AS (
    SELECT sequence FROM ranked WHERE id = %(pk)s
)
SELECT id, channel, log_date, line_number, posted_at, event_type, nick,
       normalized_nick, body, person_id, display_name, context_key,
       context_title, context_url, context_kind, source_url, source_file_sha,
       raw_line
FROM ranked, focus
WHERE ranked.sequence BETWEEN focus.sequence - %(before)s
                          AND focus.sequence + %(after)s
ORDER BY line_number
"""
    rows = run_query(
        sql,
        {
            "pk": pk,
            "source": source,
            "channel": channel,
            "log_date": log_date,
            "before": before_count,
            "after": after_count,
        },
    )
    events = [_event_result(row) for row in rows]
    return {
        "focus_id": f"irc_event:{pk}",
        "channel": channel,
        "log_date": log_date.isoformat(),
        "events": events,
    }
