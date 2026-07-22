"""One-time data migration: copy everything from the local Postgres
(docker-compose) into the Supabase-hosted database DATABASE_URL now points
at. Run `make migrate` against Supabase first -- this only copies rows, it
doesn't create the schema.

Copies people before messages (messages.person_id references people.id),
preserving original ids via OVERRIDING SYSTEM VALUE so the foreign key
still lines up, then resets each table's identity sequence so future
ordinary inserts continue past the copied ids. Skips search_vector -- it's
a STORED generated column, Postgres computes it from title/body on insert,
inserting into it directly would error.

Safe to re-run: every insert is ON CONFLICT (id) DO NOTHING.
"""

import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

# The source cursor deserializes messages.raw (jsonb) into a plain dict --
# psycopg2 has no built-in adapter for dict on the write side, it needs to
# know to re-serialize it as JSON rather than fail with "can't adapt type
# 'dict'". Registering this globally is simpler than special-casing the one
# column in _copy_table.
psycopg2.extensions.register_adapter(dict, Json)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_data_to_supabase")

BATCH_SIZE = 1000

# Order matters: people before messages (FK). search_vector is deliberately
# excluded -- see module docstring.
_TABLES = [
    ("people", ["id", "email", "display_name", "created_at", "github_username", "bitcointalk_username"]),
    ("messages", ["id", "channel", "external_id", "thread_id", "author", "email", "title", "body",
                  "url", "posted_at", "ingested_at", "raw", "person_id"]),
]


def _local_connection():
    return psycopg2.connect(
        host="localhost",
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def _target_connection():
    # Force session-mode pooling (port 5432) instead of whatever's in
    # DATABASE_URL (likely 6543, transaction mode) -- a long-lived script
    # holding one connection across many sequential batches hit
    # "cannot execute INSERT in a read-only transaction" partway through
    # a real run on transaction mode, consistent with Supavisor recycling
    # the backend mid-session. Session mode keeps one fixed backend for
    # the whole connection, which this bulk copy actually needs; the app's
    # own DATABASE_URL is untouched, this only affects this script.
    url = os.environ["DATABASE_URL"].replace(":6543/", ":5432/")
    return psycopg2.connect(url, connect_timeout=10)


def _copy_table(source_conn, target_conn, table: str, columns: list[str]) -> int:
    col_list = ", ".join(columns)
    insert_sql = (
        f"INSERT INTO {table} ({col_list}) OVERRIDING SYSTEM VALUE VALUES %s "
        f"ON CONFLICT (id) DO NOTHING"
    )

    copied = 0
    with source_conn.cursor(name=f"read_{table}") as read_cur, target_conn.cursor() as write_cur:
        read_cur.itersize = BATCH_SIZE
        read_cur.execute(f"SELECT {col_list} FROM {table} ORDER BY id")
        while True:
            rows = read_cur.fetchmany(BATCH_SIZE)
            if not rows:
                break
            execute_values(write_cur, insert_sql, rows)
            target_conn.commit()
            copied += len(rows)
            logger.info(f"{table}: copied {copied} rows so far")

    with target_conn.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
        )
        target_conn.commit()

    return copied


def main() -> None:
    source = _local_connection()
    target = _target_connection()
    try:
        with target.cursor() as cur:
            cur.execute("SELECT to_regclass('public.messages')")
            if cur.fetchone()[0] is None:
                raise RuntimeError(
                    "target database has no `messages` table -- run `make migrate` "
                    "against it first, this script only copies data"
                )

        for table, columns in _TABLES:
            total = _copy_table(source, target, table, columns)
            logger.info(f"done: {table} -- {total} rows copied")
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
