"""Link IRC-only people rows to existing canonical contributor entities.

IRC exposes a nickname but no durable account identifier. The ingester's
curated mappings cover aliases such as ``sipa`` -> Pieter Wuille, while an
exact case-insensitive IRC-nick/GitHub-username match is also strong enough
to link automatically when every matching row belongs to one canonical
person group.

This reconciliation is deliberately non-destructive: the IRC row keeps its
``irc_nick`` and every ``irc_events.person_id`` reference. We only set the
row's ``canonical_person_id`` to the existing contributor root, so all
canonical-group-aware searches and people views include both identities.

Safe to rerun. Preview by default; pass ``--apply`` to commit:

    python3 scripts/reconcile_irc_people.py
    python3 scripts/reconcile_irc_people.py --apply
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import get_connection  # noqa: E402
from scripts.ingest_gnusha_irc import (  # noqa: E402
    _ADVISORY_LOCK_KEY,
    known_identity_for_nick,
)


_SOURCE_ROWS_SQL = """
SELECT p.id, p.irc_nick, count(e.id) AS event_count
FROM people p
LEFT JOIN irc_events e ON e.person_id = p.id
WHERE p.irc_nick IS NOT NULL
  AND p.canonical_person_id IS NULL
GROUP BY p.id, p.irc_nick
ORDER BY event_count DESC, p.id
"""

_GITHUB_ROOTS_SQL = """
SELECT lower(github_username), coalesce(canonical_person_id, id) AS root_id
FROM people
WHERE github_username IS NOT NULL
"""


@dataclass(frozen=True)
class Candidate:
    source_id: int
    irc_nick: str
    target_id: int
    target_github_username: str
    reason: str
    event_count: int


def _github_roots(rows: list[tuple[str, int]]) -> dict[str, set[int]]:
    roots: dict[str, set[int]] = defaultdict(set)
    for username, root_id in rows:
        roots[username.casefold()].add(root_id)
    return dict(roots)


def _find_candidates(
    source_rows: list[tuple[int, str, int]],
    roots_by_github: dict[str, set[int]],
) -> tuple[list[Candidate], Counter]:
    candidates: list[Candidate] = []
    stats: Counter = Counter()
    stats["sources_considered"] = len(source_rows)

    for source_id, irc_nick, event_count in source_rows:
        identity = known_identity_for_nick(irc_nick)
        if identity is not None:
            github_username = identity.github_username
            reason = "curated_alias"
        else:
            github_username = irc_nick
            reason = "exact_github_username"

        roots = roots_by_github.get(github_username.casefold(), set())
        if not roots:
            stats["without_github_match"] += 1
            continue
        if len(roots) != 1:
            stats["ambiguous_github_match"] += 1
            continue

        target_id = next(iter(roots))
        if target_id == source_id:
            stats["already_canonical_root"] += 1
            continue

        candidates.append(
            Candidate(
                source_id=source_id,
                irc_nick=irc_nick,
                target_id=target_id,
                target_github_username=github_username,
                reason=reason,
                event_count=event_count,
            )
        )
        stats[f"{reason}_candidates"] += 1
        stats["events_reconciled"] += event_count

    stats["candidates"] = len(candidates)
    return candidates, stats


def _apply_candidate(cur, candidate: Candidate) -> bool:
    # Recheck both ends under row locks so a repeated or concurrent run cannot
    # create a canonical chain. The shared ingestion advisory lock prevents
    # the normal IRC job from creating more source rows during this pass.
    cur.execute(
        "SELECT canonical_person_id FROM people WHERE id = %(id)s FOR UPDATE",
        {"id": candidate.source_id},
    )
    source = cur.fetchone()
    if source is None or source[0] is not None:
        return False

    cur.execute(
        "SELECT canonical_person_id FROM people WHERE id = %(id)s FOR UPDATE",
        {"id": candidate.target_id},
    )
    target = cur.fetchone()
    if target is None or target[0] is not None:
        return False

    # Normally an IRC-only source has no children. Flatten them if it does so
    # the schema's one-level canonical-group invariant remains true.
    cur.execute(
        """
        UPDATE people
        SET canonical_person_id = %(target_id)s
        WHERE canonical_person_id = %(source_id)s
        """,
        {
            "source_id": candidate.source_id,
            "target_id": candidate.target_id,
        },
    )
    cur.execute(
        """
        UPDATE people
        SET canonical_person_id = %(target_id)s
        WHERE id = %(source_id)s
          AND canonical_person_id IS NULL
        """,
        {
            "source_id": candidate.source_id,
            "target_id": candidate.target_id,
        },
    )
    return cur.rowcount == 1


def reconcile(*, apply: bool = False) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(%(key)s)",
                {"key": _ADVISORY_LOCK_KEY},
            )
            if not cur.fetchone()[0]:
                raise RuntimeError(
                    "IRC ingestion is running; wait for it to finish before reconciling people"
                )

            cur.execute(_SOURCE_ROWS_SQL)
            source_rows = cur.fetchall()
            cur.execute(_GITHUB_ROOTS_SQL)
            roots_by_github = _github_roots(cur.fetchall())
            candidates, stats = _find_candidates(source_rows, roots_by_github)

            if apply:
                for candidate in candidates:
                    if _apply_candidate(cur, candidate):
                        stats["linked"] += 1
                    else:
                        stats["skipped_after_recheck"] += 1
                conn.commit()
            else:
                conn.rollback()

        return {
            "mode": "apply" if apply else "preview",
            **dict(stats),
            "matches": [asdict(candidate) for candidate in candidates],
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link safe IRC-only identities to canonical contributor people."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit links; omit to preview without changing the database",
    )
    args = parser.parse_args()
    print(json.dumps(reconcile(apply=args.apply), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
