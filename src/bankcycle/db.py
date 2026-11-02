import psycopg
from psycopg.conninfo import make_conninfo

from bankcycle.settings import get_settings


def conninfo() -> str:
    s = get_settings()
    return make_conninfo(
        host=s.pghost,
        port=s.pgport,
        dbname=s.pgdatabase,
        user=s.pguser,
        password=s.pgpassword,
    )


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conninfo(), autocommit=autocommit)


def is_up() -> bool:
    try:
        with psycopg.connect(conninfo(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False
