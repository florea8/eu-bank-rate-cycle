from decimal import Decimal

from bankcycle.ingest import eba, eba_metadata

EXERCISE = 1999


def _row(item: str, amount: str | None) -> tuple:
    values = {col: "0" for col in eba.TR_OTH_COLUMNS}
    values.update(LEI_Code="TESTLEI", Period="199912", Item=item, Amount=amount, Footnote=None)
    return tuple(values[col] for col in eba.TR_OTH_COLUMNS)


def _amounts(conn) -> dict:
    rows = conn.execute(
        "SELECT item, amount FROM raw.eba_tr_oth WHERE exercise = %s", (EXERCISE,)
    ).fetchall()
    return dict(rows)


def test_replace_exercise_loads_rows(pg_conn):
    pg_conn.execute(eba.DDL)

    written = eba.replace_exercise(pg_conn, EXERCISE, "a" * 64, [_row("1", "1.5"), _row("2", None)])

    assert written == 2
    assert _amounts(pg_conn) == {"1": Decimal("1.5"), "2": None}


def test_reload_replaces_instead_of_appending(pg_conn):
    pg_conn.execute(eba.DDL)
    eba.replace_exercise(pg_conn, EXERCISE, "a" * 64, [_row("1", "1.5"), _row("2", "2")])

    eba.replace_exercise(pg_conn, EXERCISE, "b" * 64, [_row("1", "9")])

    assert _amounts(pg_conn) == {"1": Decimal("9")}


def test_already_loaded_matches_checksum(pg_conn):
    pg_conn.execute(eba.DDL)
    assert not eba.already_loaded(pg_conn, EXERCISE, "a" * 64)

    eba.replace_exercise(pg_conn, EXERCISE, "a" * 64, [_row("1", "1.5")])

    assert eba.already_loaded(pg_conn, EXERCISE, "a" * 64)
    assert not eba.already_loaded(pg_conn, EXERCISE, "b" * 64)


def _item(item: str, previous: dict) -> dict:
    return {"csv_file": "tr_oth.csv", "template": "Capital", "item": item, "category": "Capital",
            "label": "OWN FUNDS", "collection": None, "previous_items": previous}


def test_replace_rows_stores_jsonb_and_replaces(pg_conn):
    pg_conn.execute(eba_metadata.DDL)
    table = eba_metadata.ITEMS
    eba.replace_rows(pg_conn, table, EXERCISE, "a" * 64,
                     [_item("1", {"Item_TR_1998": "981"}), _item("2", {})])

    written = eba.replace_rows(pg_conn, table, EXERCISE, "b" * 64,
                               [_item("1", {"Item_TR_1998": "982"})])

    rows = pg_conn.execute(
        "SELECT item, previous_items ->> 'Item_TR_1998' FROM raw.eba_items WHERE exercise = %s",
        (EXERCISE,),
    ).fetchall()
    assert written == 1
    assert rows == [("1", "982")]
    assert eba.already_loaded(pg_conn, EXERCISE, "b" * 64, table)
