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

from db.client import get_connection

# Score tiers, highest first: an exact unique identifier (email) = 1.0; an
# exact name/title match = _EXACT_NAME_SCORE (strong, but names collide so it
# stays below a unique id); a fuzzy match = _FUZZY_WEIGHT * similarity() (0..1),
# which caps below the exact tiers.
_EXACT_NAME_SCORE = 0.9
_FUZZY_WEIGHT = 0.6
_MAX_RESULTS = 30


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
_ENTITIES = (
    _Entity(type="person", table="people",
            label_expr="coalesce(display_name, '(unknown)') || ' -- ' || "
                        "coalesce(email, bitcointalk_username, github_username, '(no contact)')",
            exact_cols=("email", "bitcointalk_username", "github_username"),
            fuzzy_cols=("display_name", "email", "bitcointalk_username", "github_username"),
            extra_cols=("email", "bitcointalk_username", "github_username")),
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


def _build_resolve_sql() -> str:
    branches = [b for e in _ENTITIES for b in _branches(e)]
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
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


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
    """
    q = (query or "").strip()
    if not q:
        return []
    rows = run_query(_RESOLVE_SQL, {
        "q": q.lower(),
        "raw_q": q,
        "exact_name_score": _EXACT_NAME_SCORE,
        "fuzzy_weight": _FUZZY_WEIGHT,
        "limit": max(1, min(int(limit or 10), _MAX_RESULTS)),
    })
    candidates = []
    for id_, type_, label, score, email, bitcointalk_username, github_username in rows:
        candidates.append({
            "id": id_,
            "type": type_,
            "label": label,
            "score": round(float(score), 3),
            "person_id": int(id_.partition(":")[2]),
            "email": email,
            "bitcointalk_username": bitcointalk_username,
            "github_username": github_username,
        })
    return candidates
