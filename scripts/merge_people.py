"""Merge two or more people rows that are actually the same person under
different identity keys (e.g. a mailing-list email and a BitcoinTalk
username -- nothing in the schema links those automatically, since they're
different unique keys with no shared column; that link is a human judgment
call, not something resolve() can infer).

Keeps one target row, repoints every messages.person_id pointing at the
others onto it, fills any of the target's null identity columns from the
others (email / bitcointalk_username / github_username / display_name),
then deletes the merged-away rows. Refuses to guess when two rows disagree
on the same non-null unique column (e.g. two different emails) -- merging
silently would drop one of them with no record of the conflict.
"""

from db.client import get_connection

_MERGE_COLUMNS = ("email", "display_name", "bitcointalk_username", "github_username")


def merge_people(target_id: int, *other_ids: int) -> dict:
    if not other_ids:
        raise ValueError("need at least one other_id to merge into target_id")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, display_name, bitcointalk_username, github_username "
                "FROM people WHERE id = ANY(%(ids)s)",
                {"ids": [target_id, *other_ids]},
            )
            rows = {r[0]: dict(zip(("id", *_MERGE_COLUMNS), r)) for r in cur.fetchall()}

            missing = set([target_id, *other_ids]) - rows.keys()
            if missing:
                raise ValueError(f"no such people id(s): {missing}")

            target = rows[target_id]
            for other_id in other_ids:
                other = rows[other_id]
                for col in ("email", "bitcointalk_username", "github_username"):
                    if target[col] and other[col] and target[col] != other[col]:
                        raise ValueError(
                            f"conflict on {col}: target {target_id}={target[col]!r} "
                            f"vs {other_id}={other[col]!r} -- resolve manually, refusing to guess"
                        )

            merged = dict(target)
            for other_id in other_ids:
                other = rows[other_id]
                for col in _MERGE_COLUMNS:
                    if not merged[col] and other[col]:
                        merged[col] = other[col]

            cur.execute(
                "UPDATE messages SET person_id = %(target_id)s WHERE person_id = ANY(%(other_ids)s)",
                {"target_id": target_id, "other_ids": list(other_ids)},
            )
            moved = cur.rowcount

            cur.execute(
                "UPDATE people SET email = %(email)s, display_name = %(display_name)s, "
                "bitcointalk_username = %(bitcointalk_username)s, github_username = %(github_username)s "
                "WHERE id = %(id)s",
                merged,
            )

            cur.execute("DELETE FROM people WHERE id = ANY(%(ids)s)", {"ids": list(other_ids)})
            deleted = cur.rowcount

        conn.commit()
        return {"target_id": target_id, "merged_row": merged, "messages_repointed": moved, "rows_deleted": deleted}
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    ids = [int(a) for a in sys.argv[1:]]
    if len(ids) < 2:
        print("usage: python3 scripts/merge_people.py <target_id> <other_id> [<other_id> ...]")
        sys.exit(1)
    print(merge_people(ids[0], *ids[1:]))
