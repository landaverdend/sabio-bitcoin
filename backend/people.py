"""People endpoints -- list and detail views for the people table, which
canonicalizes identities across the mailing list, BitcoinTalk, and GitHub.

Commit history isn't served from here: the Person detail page reuses
/repo/commits?author=<display_name> directly, since git commit authorship
already lives in the git object database (see backend/repo.py) rather than
this table."""

from fastapi import APIRouter, HTTPException

from agents.shared.resolve import run_query

router = APIRouter(prefix="/people", tags=["people"])

PEOPLE_PAGE_SIZE = 30
MESSAGES_PAGE_SIZE = 20


def _person_dict(row: tuple) -> dict:
    return {
        "id": row[0],
        "display_name": row[1],
        "email": row[2],
        "github_username": row[3],
        "bitcointalk_username": row[4],
    }


@router.get("")
def list_people(q: str | None = None, page: int = 1) -> dict:
    """Paginated people list, optionally filtered by a name/email/username
    search, ordered by message count so the most active people surface
    first."""
    page = max(1, page)
    offset = (page - 1) * PEOPLE_PAGE_SIZE

    where = ""
    params: dict = {"limit": PEOPLE_PAGE_SIZE, "offset": offset}
    if q:
        where = """
            WHERE p.display_name ILIKE %(q)s OR p.email ILIKE %(q)s
               OR p.github_username ILIKE %(q)s OR p.bitcointalk_username ILIKE %(q)s
        """
        params["q"] = f"%{q}%"

    total = run_query(f"SELECT count(*) FROM people p {where}", params)[0][0]

    rows = run_query(
        f"""
        SELECT p.id, p.display_name, p.email, p.github_username, p.bitcointalk_username,
               count(m.id) AS message_count
        FROM people p
        LEFT JOIN messages m ON m.person_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY message_count DESC, p.id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    )
    people = [{**_person_dict(r), "message_count": r[5]} for r in rows]

    return {"page": page, "page_size": PEOPLE_PAGE_SIZE, "total": total, "people": people}


@router.get("/{person_id}")
def get_person(person_id: int) -> dict:
    """Person detail plus a per-channel message-count breakdown -- the
    Person page's tab bar is built from this (a channel with zero messages
    just doesn't get a tab) rather than discovering emptiness after the
    fact by fetching each channel's messages."""
    rows = run_query(
        "SELECT id, display_name, email, github_username, bitcointalk_username FROM people WHERE id = %(id)s",
        {"id": person_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"person not found: {person_id}")

    channel_rows = run_query(
        "SELECT channel, count(*) FROM messages WHERE person_id = %(id)s GROUP BY channel ORDER BY count(*) DESC",
        {"id": person_id},
    )
    channels = [{"channel": r[0], "count": r[1]} for r in channel_rows]

    return {**_person_dict(rows[0]), "channels": channels}


@router.get("/{person_id}/messages")
def get_person_messages(person_id: int, page: int = 1, q: str | None = None, channel: str | None = None) -> dict:
    """Paginated messages for a person, optionally full-text filtered by q
    and/or scoped to one channel (e.g. "bitcointalk") -- the latter backs
    the per-channel tabs on the Person page. Same search_vector/
    websearch_to_tsquery machinery as agents/comms/db_tools.py's
    search_messages -- ranked by relevance while a query is active,
    otherwise newest first."""
    page = max(1, page)
    offset = (page - 1) * MESSAGES_PAGE_SIZE

    where = "WHERE person_id = %(id)s"
    params: dict = {"id": person_id, "limit": MESSAGES_PAGE_SIZE, "offset": offset}
    order_sql = "posted_at DESC NULLS LAST"
    if channel:
        where += " AND channel = %(channel)s"
        params["channel"] = channel
    if q:
        where += " AND search_vector @@ websearch_to_tsquery('english', %(q)s)"
        params["q"] = q
        order_sql = (
            "ts_rank_cd(search_vector, websearch_to_tsquery('english', %(q)s)) DESC, "
            "posted_at DESC NULLS LAST"
        )

    total = run_query(f"SELECT count(*) FROM messages {where}", params)[0][0]

    rows = run_query(
        f"""
        SELECT id, channel, title, author, posted_at, url, left(body, 280)
        FROM messages
        {where}
        ORDER BY {order_sql}
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    )
    messages = [
        {
            "id": r[0],
            "channel": r[1],
            "title": r[2],
            "author": r[3],
            "posted_at": r[4].isoformat() if r[4] else None,
            "url": r[5],
            "snippet": r[6],
        }
        for r in rows
    ]

    return {"page": page, "page_size": MESSAGES_PAGE_SIZE, "total": total, "messages": messages}
