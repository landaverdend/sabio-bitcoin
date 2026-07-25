import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    # TCP keepalives: without these, a connection that goes silently dead
    # mid-query (network blip, Neon pooler dropping it without a clean FIN)
    # can leave a blocking call waiting forever with no error raised --
    # confirmed in production, where scrape_bitcointalk.py hung for 1.5+
    # hours with an ESTABLISHED-looking socket and zero CPU/log activity.
    # These make the OS probe an idle connection and force an
    # OperationalError once it's actually dead, which the existing
    # reconnect-retry logic already handles.
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
