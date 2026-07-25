"""People endpoints -- list and detail views for the people table, which
canonicalizes identities across the mailing list, BitcoinTalk, and GitHub.

Commit history isn't served from here: the Person detail page reuses
/repo/commits?author=<display_name> directly, since git commit authorship
already lives in the git object database (see backend/repo.py) rather than
this table.

canonical_person_id (db/migrations/0008) lets several rows be flagged as the
same real person without merging them -- a GitHub-linked email row and a
BitcoinTalk-only row with no email can be the same human with zero shared
column to auto-join on. Every query here groups by coalesce(canonical_person_id,
id) so a person with N rows shows as one profile with combined message counts,
not N confusingly duplicate entries."""

from fastapi import APIRouter, HTTPException

from agents.shared.resolve import run_query

router = APIRouter(prefix="/people", tags=["people"])

PEOPLE_PAGE_SIZE = 30
MESSAGES_PAGE_SIZE = 20

# Every row in the same canonical group as a given row, root row (the one
# with canonical_person_id IS NULL) included. Reused by all three endpoints
# below so "which rows count as this person" is defined in exactly one place.
_GROUP_CTE = """
    person_groups AS (
        SELECT id AS root_id, id AS member_id FROM people WHERE canonical_person_id IS NULL
        UNION ALL
        SELECT canonical_person_id AS root_id, id AS member_id FROM people WHERE canonical_person_id IS NOT NULL
    )
"""

# Same grouping, scoped to a single :id's group via a root lookup -- used by
# get_person and get_person_messages, which start from one person_id rather
# than listing every group like list_people does.
_MEMBER_IDS_CTE = """
    root AS (
        SELECT coalesce(canonical_person_id, id) AS root_id FROM people WHERE id = %(id)s
    ),
    member_ids AS (
        SELECT id FROM people, root WHERE people.id = root.root_id OR people.canonical_person_id = root.root_id
    )
"""


def _merge_field(rows: list[tuple], col_index: int):
    """First non-null value across a group's rows, root row preferred --
    rows must already be ordered root-first (see callers)."""
    for row in rows:
        if row[col_index] is not None:
            return row[col_index]
    return None


@router.get("")
def list_people(q: str | None = None, page: int = 1) -> dict:
    """Paginated people list, optionally filtered by a name/email/username
    search, ordered by message count so the most active people surface
    first. Grouped by canonical person: a search matches if any row in a
    person's group matches, and the displayed fields are the first non-null
    value per column across the group (root row preferred)."""
    page = max(1, page)
    offset = (page - 1) * PEOPLE_PAGE_SIZE

    search_exists = ""
    params: dict = {"limit": PEOPLE_PAGE_SIZE, "offset": offset}
    if q:
        search_exists = """
            AND EXISTS (
                SELECT 1 FROM person_groups pg2 JOIN people p2 ON p2.id = pg2.member_id
                WHERE pg2.root_id = fields.root_id AND (
                    p2.display_name ILIKE %(q)s OR p2.email ILIKE %(q)s
                    OR p2.github_username ILIKE %(q)s OR p2.bitcointalk_username ILIKE %(q)s
                )
            )
        """
        params["q"] = f"%{q}%"

    rows = run_query(
        f"""
        WITH {_GROUP_CTE},
        fields AS (
            SELECT pg.root_id,
                   (array_agg(p.display_name ORDER BY (p.id = pg.root_id) DESC)
                       FILTER (WHERE p.display_name IS NOT NULL))[1] AS display_name,
                   (array_agg(p.email ORDER BY (p.id = pg.root_id) DESC)
                       FILTER (WHERE p.email IS NOT NULL))[1] AS email,
                   (array_agg(p.github_username ORDER BY (p.id = pg.root_id) DESC)
                       FILTER (WHERE p.github_username IS NOT NULL))[1] AS github_username,
                   (array_agg(p.bitcointalk_username ORDER BY (p.id = pg.root_id) DESC)
                       FILTER (WHERE p.bitcointalk_username IS NOT NULL))[1] AS bitcointalk_username,
                   count(*) - 1 AS linked_count
            FROM person_groups pg JOIN people p ON p.id = pg.member_id
            GROUP BY pg.root_id
        ),
        msgcounts AS (
            SELECT pg.root_id, count(m.id) AS message_count
            FROM person_groups pg LEFT JOIN messages m ON m.person_id = pg.member_id
            GROUP BY pg.root_id
        )
        SELECT fields.root_id, fields.display_name, fields.email, fields.github_username,
               fields.bitcointalk_username, msgcounts.message_count, fields.linked_count,
               count(*) OVER() AS total_count
        FROM fields JOIN msgcounts ON msgcounts.root_id = fields.root_id
        WHERE true {search_exists}
        ORDER BY msgcounts.message_count DESC, fields.root_id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    )
    if rows:
        total = rows[0][7]
    else:
        # Same reasoning as before this endpoint was grouped: an empty page
        # has no row to carry count(*) OVER() on, so fall back to a real
        # count of matching *groups* (not raw people rows).
        fallback_exists = search_exists.replace("fields.root_id", "pg.root_id") if q else ""
        total = run_query(
            f"""
            WITH {_GROUP_CTE}
            SELECT count(DISTINCT pg.root_id) FROM person_groups pg
            WHERE true {fallback_exists}
            """,
            params,
        )[0][0]

    people = [
        {
            "id": r[0],
            "display_name": r[1],
            "email": r[2],
            "github_username": r[3],
            "bitcointalk_username": r[4],
            "message_count": r[5],
            "linked_count": r[6],
        }
        for r in rows
    ]

    return {"page": page, "page_size": PEOPLE_PAGE_SIZE, "total": total, "people": people}


@router.get("/{person_id}")
def get_person(person_id: int) -> dict:
    """Person detail plus a per-channel message-count breakdown -- the
    Person page's tab bar is built from this (a channel with zero messages
    just doesn't get a tab) rather than discovering emptiness after the
    fact by fetching each channel's messages.

    Grouped by canonical person: display fields are merged across the whole
    group (first non-null per column, root row preferred), channel counts
    sum every row in the group, and `identities` lists each raw row so the
    page can show "also known as" rather than hiding the other emails/
    usernames entirely."""
    member_rows = run_query(
        f"""
        WITH {_MEMBER_IDS_CTE}
        SELECT id, display_name, email, github_username, bitcointalk_username
        FROM people, root
        WHERE people.id = root.root_id OR people.canonical_person_id = root.root_id
        ORDER BY (people.id = root.root_id) DESC, people.id
        """,
        {"id": person_id},
    )
    if not member_rows:
        raise HTTPException(status_code=404, detail=f"person not found: {person_id}")

    channel_rows = run_query(
        f"""
        WITH {_MEMBER_IDS_CTE}
        SELECT channel, count(*) FROM messages
        WHERE person_id IN (SELECT id FROM member_ids)
        GROUP BY channel ORDER BY count(*) DESC
        """,
        {"id": person_id},
    )
    channels = [{"channel": r[0], "count": r[1]} for r in channel_rows]

    return {
        "id": member_rows[0][0],
        "display_name": _merge_field(member_rows, 1),
        "email": _merge_field(member_rows, 2),
        "github_username": _merge_field(member_rows, 3),
        "bitcointalk_username": _merge_field(member_rows, 4),
        "channels": channels,
        "identities": [
            {"id": r[0], "display_name": r[1], "email": r[2], "github_username": r[3], "bitcointalk_username": r[4]}
            for r in member_rows
        ],
    }


@router.get("/{person_id}/messages")
def get_person_messages(person_id: int, page: int = 1, q: str | None = None, channel: str | None = None) -> dict:
    """Paginated messages for a person (every row in their canonical group,
    not just person_id itself), optionally full-text filtered by q and/or
    scoped to one channel (e.g. "bitcointalk") -- the latter backs the
    per-channel tabs on the Person page. Same search_vector/
    websearch_to_tsquery machinery as agents/comms/db_tools.py's
    search_messages -- ranked by relevance while a query is active,
    otherwise newest first."""
    page = max(1, page)
    offset = (page - 1) * MESSAGES_PAGE_SIZE

    where = "WHERE person_id IN (SELECT id FROM member_ids)"
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

    rows = run_query(
        f"""
        WITH {_MEMBER_IDS_CTE}
        SELECT id, channel, title, author, posted_at, url, left(body, 280), count(*) OVER() AS total_count
        FROM messages
        {where}
        ORDER BY {order_sql}
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    )
    if rows:
        total = rows[0][7]
    else:
        total = run_query(f"WITH {_MEMBER_IDS_CTE} SELECT count(*) FROM messages {where}", params)[0][0]
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
