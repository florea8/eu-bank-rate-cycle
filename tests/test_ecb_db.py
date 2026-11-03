from bankcycle.ingest import ecb

KEY = "TEST.D.U2.EUR.X"


def _row(period: str, value: float, status: str = "A") -> dict:
    return {
        "series_key": KEY,
        "time_period": period,
        "obs_value": value,
        "obs_status": status,
        "title": "test series",
    }


def _values(conn) -> dict:
    rows = conn.execute(
        "SELECT time_period, obs_value FROM raw.ecb_observations WHERE series_key = %s",
        (KEY,),
    ).fetchall()
    return dict(rows)


def test_upsert_inserts_then_skips_unchanged(pg_conn):
    pg_conn.execute(ecb.DDL)
    rows = [_row("2022-07-26", -0.5), _row("2022-07-27", 0.0)]

    assert ecb.upsert(pg_conn, "test", rows) == 2
    assert ecb.upsert(pg_conn, "test", rows) == 0
    assert _values(pg_conn) == {"2022-07-26": -0.5, "2022-07-27": 0.0}


def test_upsert_applies_revisions(pg_conn):
    pg_conn.execute(ecb.DDL)
    ecb.upsert(pg_conn, "test", [_row("2022-07-27", 0.0)])

    written = ecb.upsert(pg_conn, "test", [_row("2022-07-27", 0.25), _row("2022-07-28", 0.25)])

    assert written == 2
    assert _values(pg_conn) == {"2022-07-27": 0.25, "2022-07-28": 0.25}


def test_latest_period(pg_conn):
    pg_conn.execute(ecb.DDL)
    assert ecb.latest_period(pg_conn, KEY) is None

    ecb.upsert(pg_conn, "test", [_row("2025-06-30", 2.0), _row("2024-01-02", 4.0)])

    assert ecb.latest_period(pg_conn, KEY) == "2025-06-30"
