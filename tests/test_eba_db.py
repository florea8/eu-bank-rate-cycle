from decimal import Decimal

from bankcycle.ingest import eba

EXERCISE = 1999


def _row(item: str, amount: str | None) -> dict:
    row = {col: "0" for col in eba.TR_OTH_COLUMNS.values()}
    row.update(lei_code="TESTLEI", period="199912", item=item, amount=amount, footnote=None)
    return row


def _amounts(conn) -> dict:
    rows = conn.execute(
        "SELECT item, amount FROM raw.eba_tr_oth WHERE exercise = %s", (EXERCISE,)
    ).fetchall()
    return dict(rows)


def test_replace_rows_loads_rows(pg_conn):
    rows = [_row("1", "1.5"), _row("2", None)]

    written = eba.replace_rows(pg_conn, "eba_tr_oth", EXERCISE, "a" * 64, rows)

    assert written == 2
    assert _amounts(pg_conn) == {"1": Decimal("1.5"), "2": None}


def test_reload_replaces_instead_of_appending(pg_conn):
    eba.replace_rows(pg_conn, "eba_tr_oth", EXERCISE, "a" * 64, [_row("1", "1.5"), _row("2", "2")])

    eba.replace_rows(pg_conn, "eba_tr_oth", EXERCISE, "b" * 64, [_row("1", "9")])

    assert _amounts(pg_conn) == {"1": Decimal("9")}


def test_already_loaded_matches_checksum(pg_conn):
    assert not eba.already_loaded(pg_conn, "eba_tr_oth", EXERCISE, "a" * 64)

    eba.replace_rows(pg_conn, "eba_tr_oth", EXERCISE, "a" * 64, [_row("1", "1.5")])

    assert eba.already_loaded(pg_conn, "eba_tr_oth", EXERCISE, "a" * 64)
    assert not eba.already_loaded(pg_conn, "eba_tr_oth", EXERCISE, "b" * 64)


def test_replace_rows_stores_dicts_as_jsonb(pg_conn):
    item = {"csv_file": "tr_oth.csv", "template": "Capital", "item": "1", "category": "Capital",
            "label": "OWN FUNDS", "collection": None, "previous_items": {"Item_TR_1998": "981"}}

    eba.replace_rows(pg_conn, "eba_items", EXERCISE, "a" * 64, [item])

    rows = pg_conn.execute(
        "SELECT item, previous_items ->> 'Item_TR_1998' FROM raw.eba_items WHERE exercise = %s",
        (EXERCISE,),
    ).fetchall()
    assert rows == [("1", "981")]
