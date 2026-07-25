import os
import threading

import psycopg2
from dotenv import load_dotenv
from psycopg2 import pool as _pool

load_dotenv()

_CONNECT_KWARGS = dict(
    connect_timeout=10,
    # TCP keepalives: without these, a connection that goes silently dead
    # mid-query (network blip, Neon pooler dropping it without a clean FIN)
    # can leave a blocking call waiting forever with no error raised --
    # confirmed in production, where scrape_bitcointalk.py hung for 1.5+
    # hours with an ESTABLISHED-looking socket and zero CPU/log activity.
    # These make the OS probe an idle connection and force an
    # OperationalError once it's actually dead, which the existing
    # reconnect-retry logic already handles.
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=3,
)


def get_connection():
    """A dedicated connection for code that holds it for a whole run (the
    scripts/ backfills, the jobs/ sync scripts -- each already has its own
    reconnect/retry handling built around owning one connection start to
    finish). Request-serving code that opens a connection per query should
    use get_pooled_connection() instead -- see its docstring for why."""
    return psycopg2.connect(os.environ["DATABASE_URL"], **_CONNECT_KWARGS)


# Built lazily (not at import time) so importing this module never opens a
# connection on its own -- only get_pooled_connection()'s first real call
# does, matching get_connection()'s existing lazy-per-call behavior.
_POOL: _pool.ThreadedConnectionPool | None = None
_POOL_LOCK = threading.Lock()


def get_pooled_connection():
    """A connection borrowed from a small process-wide pool, for code that
    opens/closes a connection per query rather than holding one for a whole
    run -- namely agents/shared/resolve.run_query(), the only DB access path
    for every backend/people.py route and every comms/repos agent tool that
    touches the DB.

    Opening a fresh connection to Neon costs ~1-1.2s (TCP+TLS+auth,
    confirmed by timing get_connection() directly) -- that was the actual
    cause of "the people page takes forever", not a missing LIMIT/OFFSET
    (people.py was already paginated; list_people alone fires two of these
    per request). Reusing a small pool of already-open connections avoids
    paying that cost on every single request.

    Pairs with put_pooled_connection() -- always return what you borrow,
    even on error, or the pool exhausts and later callers block forever
    waiting for a connection that's never coming back."""
    global _POOL
    if _POOL is None:
        # FastAPI runs sync routes in a thread pool, so several requests can
        # reach this check before any of them finishes constructing the
        # pool -- without the lock, each sees _POOL is None and builds its
        # own ThreadedConnectionPool, the last one winning the module-level
        # global. A connection checked out from an earlier, now-orphaned
        # pool instance then gets returned to the surviving one, which never
        # checked it out and rejects it (psycopg2.pool.PoolError: trying to
        # put unkeyed connection) -- reproduced via concurrent requests hitting
        # backend/people.py right after server startup.
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = _pool.ThreadedConnectionPool(1, 10, os.environ["DATABASE_URL"], **_CONNECT_KWARGS)
    return _POOL.getconn()


def put_pooled_connection(conn, *, discard: bool = False) -> None:
    """discard=True permanently closes this connection instead of returning
    it to the pool -- for when the caller already knows it's dead (e.g. a
    query on it just raised OperationalError), so a broken connection
    doesn't get handed back out to the next request."""
    if _POOL is not None:
        _POOL.putconn(conn, close=discard)
