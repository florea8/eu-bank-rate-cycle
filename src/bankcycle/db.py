import psycopg
from psycopg.conninfo import make_conninfo

from bankcycle.settings import REPO_ROOT, get_settings

INIT_SQL = REPO_ROOT / "db" / "init.sql"


def conninfo() -> str:
    s = get_settings()
    return make_conninfo(
        host=s.pghost,
        port=s.pgport,
        dbname=s.pgdatabase,
        user=s.pguser,
        password=s.pgpassword,
    )


def connect() -> psycopg.Connection:
    return psycopg.connect(conninfo())


def init(conn: psycopg.Connection) -> None:
    """Create the schemas and raw tables that don't exist yet."""
    conn.execute(INIT_SQL.read_text(encoding="utf-8"))


def is_up() -> bool:
    try:
        with psycopg.connect(conninfo(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False
