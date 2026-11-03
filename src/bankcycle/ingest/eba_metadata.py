"""Parse the EBA dictionary: item codes (SDD.xlsx), banks and dimension codes (TR_Metadata.xlsx)."""
import re
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet
from psycopg import sql

ITEMS = sql.Identifier("raw", "eba_items")
INSTITUTIONS = sql.Identifier("raw", "eba_institutions")
DIMENSION_CODES = sql.Identifier("raw", "eba_dimension_codes")

DDL = """
CREATE TABLE IF NOT EXISTS raw.eba_items (
    exercise       integer NOT NULL,
    csv_file       text NOT NULL,
    template       text NOT NULL,
    item           text NOT NULL,
    category       text,
    label          text,
    collection     text,
    previous_items jsonb NOT NULL,
    source_sha256  text NOT NULL,
    loaded_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, csv_file, template, item)
);
CREATE TABLE IF NOT EXISTS raw.eba_institutions (
    exercise           integer NOT NULL,
    lei_code           text NOT NULL,
    country            text,
    country_name       text,
    name               text,
    finrep             text,
    fin_year_end       text,
    footnotes          text,
    previous_exercises jsonb NOT NULL,
    source_sha256      text NOT NULL,
    loaded_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, lei_code)
);
CREATE TABLE IF NOT EXISTS raw.eba_dimension_codes (
    exercise      integer NOT NULL,
    dimension     text NOT NULL,
    code          text NOT NULL,
    label         text,
    source_sha256 text NOT NULL,
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, dimension, code)
)
"""

# Sheet header -> raw column. Columns that change every year go into a jsonb column instead.
SDD_COLUMNS = {
    "CSV": "csv_file",
    "Template": "template",
    "Item": "item",
    "Category": "category",
    "Label": "label",
}
SDD_OPTIONAL = {"Collection"}  # only from the 2025 exercise
PREVIOUS_ITEM = re.compile(r"^Item_TR_\w+$")

INSTITUTION_COLUMNS = {
    "LEI_Code": "lei_code",
    "Country": "country",
    "Desc_country": "country_name",
    "Name": "name",
    "Finrep": "finrep",
    "Fin_year_end": "fin_year_end",
}
INSTITUTION_OPTIONAL = {"Footnotes"}  # only from the 2025 exercise
PREVIOUS_EXERCISE = re.compile(r"^(TE|TR|LEI_Code)_\w+$")

# The breakdowns used in tr_oth.csv. The other sheets describe files we don't load.
DIMENSION_SHEETS = ("ASSETS_FV", "ASSETS_Stages", "Exposure", "Financial_instruments", "Fin_end_year")


def _cell(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _read(ws: Worksheet, header_row: int) -> tuple[list[str], list[dict]]:
    """Header and non-empty rows of a sheet whose header is on row header_row (0-based)."""
    rows = ws.iter_rows(values_only=True)
    for _ in range(header_row):
        next(rows)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    records = []
    for row in rows:
        record = {h: _cell(v) for h, v in zip(header, row) if h}
        if any(record.values()):
            records.append(record)
    return header, records


def _check_header(
    where: str,
    header: list[str],
    required: set[str],
    optional: set[str] = frozenset(),
    extra: re.Pattern | None = None,
) -> None:
    columns = {h for h in header if h}
    missing = required - columns
    unexpected = {
        c for c in columns - required - optional if not (extra and extra.match(c))
    }
    if missing or unexpected:
        raise ValueError(
            f"{where}: missing columns {sorted(missing)}, unexpected columns {sorted(unexpected)}"
        )


def parse_sdd(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        header, records = _read(wb["SDD"], header_row=1)
    finally:
        wb.close()
    _check_header(f"{path} [SDD]", header, set(SDD_COLUMNS), SDD_OPTIONAL, PREVIOUS_ITEM)

    return [
        {
            **{col: r[h] for h, col in SDD_COLUMNS.items()},
            "collection": r.get("Collection"),
            "previous_items": {h: v for h, v in r.items() if PREVIOUS_ITEM.match(h) and v},
        }
        for r in records
    ]


def parse_metadata(path: Path) -> tuple[list[dict], list[dict]]:
    """Institutions and dimension codes, read from one open workbook."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        header, records = _read(wb["List of Institutions"], header_row=1)
        _check_header(
            f"{path} [List of Institutions]",
            header,
            set(INSTITUTION_COLUMNS),
            INSTITUTION_OPTIONAL,
            PREVIOUS_EXERCISE,
        )
        institutions = [
            {
                **{col: r[h] for h, col in INSTITUTION_COLUMNS.items()},
                "footnotes": r.get("Footnotes"),
                "previous_exercises": {
                    h: v for h, v in r.items() if PREVIOUS_EXERCISE.match(h) and v
                },
            }
            for r in records
        ]

        codes = []
        for sheet in DIMENSION_SHEETS:
            header, records = _read(wb[sheet], header_row=0)
            _check_header(f"{path} [{sheet}]", header, {sheet, "Label"})
            codes += [{"dimension": sheet, "code": r[sheet], "label": r["Label"]} for r in records]
    finally:
        wb.close()
    return institutions, codes
