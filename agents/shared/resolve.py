"""resolve() -- shared person lookup, usable by any agent.

Given a handle (name or email), find WHO it names. Not comms-specific: person
identity is a cross-cutting concern -- the repos agent needs it just as much
as the comms agent does, to turn "Gloria Zhao" into an email it can filter
git history by.

Message lookup ("find the message titled X") deliberately isn't here --
that's comms' search_messages(), which already covers it via full-text search
and is comms-specific, unlike identity.

SECURITY: registry values are interpolated into SQL as identifiers/expressions.
They are developer-defined config -- never populate them from user input. User
input is always passed as bound params.
"""

from dataclasses import dataclass

import psycopg2

from db.client import get_pooled_connection, put_pooled_connection

# Score tiers, highest first: an exact unique identifier (email) = 1.0; an
# exact name/title match = _EXACT_NAME_SCORE (strong, but names collide so it
# stays below a unique id); a fuzzy match = _FUZZY_WEIGHT * similarity() (0..1),
# which caps below the exact tiers.
_EXACT_NAME_SCORE = 0.9
_FUZZY_WEIGHT = 0.6
_MAX_RESULTS = 30

# Every row in the same canonical-person group as a given id
# (db/migrations/0008), root row (canonical_person_id IS NULL) included --
# shared by every caller that needs "which people rows count as this one
# person" starting from a single id: backend/people.py's endpoints and
# comms' search_messages(person_id=...) both need exactly this, so it lives
# here once instead of near-identical copies drifting apart.
MEMBER_IDS_CTE = """
    root AS (
        SELECT coalesce(canonical_person_id, id) AS root_id FROM people WHERE id = %(id)s
    ),
    member_ids AS (
        SELECT id FROM people, root WHERE people.id = root.root_id OR people.canonical_person_id = root.root_id
    )
"""


@dataclass(frozen=True)
class _Entity:
    type: str                      # agent-facing type + id prefix, e.g. "person"
    table: str
    label_expr: str                # SQL expression for the human label
    id_col: str = "id"
    exact_cols: tuple = ()         # unique identifiers (email, bitcointalk_username) -> score 1.0
    fuzzy_cols: tuple = ()         # trigram-matched cols -> exact 0.9 / fuzzy tiers
    extra_cols: tuple = ()         # raw columns surfaced to callers verbatim, not scored


# What resolve() can find: one row per reconciled person identity
# (db/migrations/0003_people.sql, extended by 0006 for channels with no
# email) -- already deduplicated across name-spelling variants, relay
# addresses excluded. A registry of one, but kept as a registry (not a
# hand-written query) so the three branches below (exact / exact-name /
# fuzzy) don't duplicate the id/label expressions, and so a second resolvable
# identity type stays a one-line addition if it's ever needed -- extra_cols
# assumes every entity in the registry shares the same extra_cols, which is
# fine for a registry of one but would need revisiting for a second entity.
#
# display_name is a single column, but the same person can post under a
# different name per channel (mailing-list signature vs BitcoinTalk handle
# vs GitHub profile name) -- person_aliases (0007) collects every name
# variant seen for a known person, so _alias_branches below extends the
# fuzzy match to all of them, not just whichever one happened to land in
# display_name.
_ENTITIES = (
    _Entity(type="person", table="people",
            label_expr="coalesce(display_name, '(unknown)') || ' -- ' || "
                        "coalesce(email, bitcointalk_username, github_username, '(no contact)')",
            exact_cols=("email", "bitcointalk_username", "github_username"),
            fuzzy_cols=("display_name", "email", "bitcointalk_username", "github_username"),
            extra_cols=("email", "bitcointalk_username", "github_username", "canonical_person_id")),
)


def _branches(entity: _Entity) -> list[str]:
    """Generate the exact + fuzzy SELECT branches for one entity. All branches
    emit the same (id, type, label, score, *extra_cols) shape so they UNION
    cleanly.

    `%%` is an escaped literal `%` (the pg_trgm operator); `%(name)s` are bound
    params filled at execute(). exact_cols/fuzzy_cols may contain NULL columns
    per row (e.g. a forum-only person has no email) -- `lower(NULL)` and
    `NULL %% ...` both just evaluate to NULL/false, so those rows are
    harmlessly excluded from that branch rather than erroring.
    """
    id_expr = f"'{entity.type}:' || {entity.id_col}::text"
    extra = "".join(f", {c}" for c in entity.extra_cols)
    out: list[str] = []

    if entity.exact_cols:
        where = " OR ".join(f"lower({c}) = %(q)s" for c in entity.exact_cols)
        out.append(
            f"    SELECT {id_expr} AS id, '{entity.type}' AS type, "
            f"{entity.label_expr} AS label, 1.0 AS score{extra}\n"
            f"    FROM {entity.table} WHERE {where}"
        )

    if entity.fuzzy_cols:
        exact = " OR ".join(f"lower({c}) = %(q)s" for c in entity.fuzzy_cols)
        out.append(
            f"    SELECT {id_expr}, '{entity.type}', {entity.label_expr}, %(exact_name_score)s{extra}\n"
            f"    FROM {entity.table} WHERE {exact}"
        )
        match = " OR ".join(f"{c} %% %(raw_q)s" for c in entity.fuzzy_cols)
        sims = ", ".join(f"similarity({c}, %(raw_q)s)" for c in entity.fuzzy_cols)
        sim_expr = f"GREATEST({sims})" if len(entity.fuzzy_cols) > 1 else sims
        out.append(
            f"    SELECT {id_expr}, '{entity.type}', {entity.label_expr}, "
            f"%(fuzzy_weight)s * {sim_expr}{extra}\n"
            f"    FROM {entity.table} WHERE {match}"
        )
    return out


def _alias_branches(entity: _Entity) -> list[str]:
    """Same shape as _branches' fuzzy pair, but matching against a joined
    person_aliases row instead of a column on entity.table directly --
    person_aliases has no columns that collide with people's, so the join
    needs no table-qualifying."""
    id_expr = f"'{entity.type}:' || {entity.id_col}::text"
    extra = "".join(f", {c}" for c in entity.extra_cols)
    join = f"FROM {entity.table} JOIN person_aliases ON person_aliases.person_id = {entity.id_col}"
    return [
        f"    SELECT {id_expr}, '{entity.type}', {entity.label_expr}, %(exact_name_score)s{extra}\n"
        f"    {join} WHERE lower(alias) = %(q)s",
        f"    SELECT {id_expr}, '{entity.type}', {entity.label_expr}, "
        f"%(fuzzy_weight)s * similarity(alias, %(raw_q)s){extra}\n"
        f"    {join} WHERE alias %% %(raw_q)s",
    ]


def _build_resolve_sql() -> str:
    branches = [b for e in _ENTITIES for b in _branches(e)] + _alias_branches(_ENTITIES[0])
    union = "\n    UNION ALL\n".join(branches)
    extra_select = "".join(f", {c}" for c in _ENTITIES[0].extra_cols)
    return f"""
WITH matches AS (
{union}
),
ranked AS (
    SELECT DISTINCT ON (id) id, type, label, score{extra_select}
    FROM matches
    ORDER BY id, score DESC
)
SELECT id, type, label, score{extra_select}
FROM ranked
ORDER BY score DESC, label
LIMIT %(limit)s
"""


# Built once at import from the registry.
_RESOLVE_SQL = _build_resolve_sql()


def run_query(sql: str, params: dict) -> list[tuple]:
    """Every query here is a read (people.py's routes, resolve()'s own
    lookup) -- the commit on success just closes out the implicit
    transaction psycopg2 opens per query, so the connection goes back to
    the pool idle rather than "idle in transaction".

    Retries once on OperationalError -- a pooled connection gone stale
    between requests (Neon's pooler dropping an idle one, same failure mode
    already seen and handled in the scraper) is routine, not a reason to
    fail the request. Any other exception (e.g. bad SQL) rolls back and
    still returns the connection to the pool -- it's the query that's
    broken, not the connection, so discarding a perfectly good connection
    would be wrong."""
    for attempt in range(2):
        conn = get_pooled_connection()
        healthy = True
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            conn.commit()
            return rows
        except psycopg2.OperationalError:
            healthy = False
            if attempt == 1:
                raise
        except Exception:
            conn.rollback()
            raise
        finally:
            put_pooled_connection(conn, discard=not healthy)


def _first_non_null(rows: list[tuple], col_index: int):
    """First non-null value at col_index across a group's member rows, root
    row (people.id == the group's root_id) preferred -- rows must already be
    sorted root-first, same convention as backend/people.py's _merge_field."""
    for row in rows:
        if row[col_index] is not None:
            return row[col_index]
    return None


def resolve(query: str, limit: int = 10) -> list[dict]:
    """Find the person a human name, email, BitcoinTalk username, or GitHub
    username might refer to.

    Searches known people across the local bitcoin-dev mailing list archive,
    git history, BitcoinTalk, and linked GitHub accounts. Returns a ranked
    list of candidates to disambiguate between -- not every sender resolves
    to a person (shared/relay addresses are excluded). email,
    bitcointalk_username, and github_username are each null when that
    candidate has no identity of that kind (e.g. a forum-only poster has no
    email, and github_username is only set for people GitHub actually
    confirmed as linked to a commit email) -- check before using one to
    filter another tool (e.g. comms' search_messages, git commits by author
    email, or a GitHub PR search by author).

    A real person can have more than one row (db/migrations/0008 -- a
    GitHub-linked email row and a BitcoinTalk-only row have no column to
    auto-join on, so both can independently match the same query) -- when
    that happens this returns one merged candidate for the group instead of
    several fragments, with email/bitcointalk_username/github_username
    filled in from whichever row in the group actually has each one.
    """
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(int(limit or 10), _MAX_RESULTS))
    rows = run_query(_RESOLVE_SQL, {
        "q": q.lower(),
        "raw_q": q,
        "exact_name_score": _EXACT_NAME_SCORE,
        "fuzzy_weight": _FUZZY_WEIGHT,
        # Always the hard ceiling, not just this call's own limit -- rows get
        # merged into fewer canonical-group candidates below, so truncating
        # before merging could drop a genuinely distinct match to make room
        # for a duplicate of one already kept.
        "limit": _MAX_RESULTS,
    })
    if not rows:
        return []

    best_score: dict[int, float] = {}
    root_order: list[int] = []
    for id_, _type, _label, score, *_extra, canonical_person_id in rows:
        root_id = canonical_person_id or int(id_.partition(":")[2])
        if root_id not in best_score:
            root_order.append(root_id)
        best_score[root_id] = max(best_score.get(root_id, 0.0), float(score))

    group_rows = run_query(
        """
        SELECT id, canonical_person_id, display_name, email, bitcointalk_username, github_username
        FROM people
        WHERE id = ANY(%(roots)s) OR canonical_person_id = ANY(%(roots)s)
        """,
        {"roots": root_order},
    )
    members: dict[int, list[tuple]] = {}
    for member_row in group_rows:
        root_id = member_row[1] or member_row[0]
        members.setdefault(root_id, []).append(member_row)
    for member_rows in members.values():
        member_rows.sort(key=lambda r: r[1] is not None)  # root row (canonical_person_id IS NULL) first

    candidates = []
    for root_id in sorted(root_order, key=lambda r: -best_score[r])[:lim]:
        member_rows = members.get(root_id, [])
        display_name = _first_non_null(member_rows, 2)
        email = _first_non_null(member_rows, 3)
        bitcointalk_username = _first_non_null(member_rows, 4)
        github_username = _first_non_null(member_rows, 5)
        candidates.append({
            "id": f"person:{root_id}",
            "type": "person",
            "label": f"{display_name or '(unknown)'} -- "
                     f"{email or bitcointalk_username or github_username or '(no contact)'}",
            "score": round(best_score[root_id], 3),
            "person_id": root_id,
            "email": email,
            "bitcointalk_username": bitcointalk_username,
            "github_username": github_username,
        })
    return candidates
