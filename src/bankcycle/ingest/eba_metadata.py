"""Parse the EBA dictionary: item codes (SDD.xlsx), banks and dimension codes (TR_Metadata.xlsx)."""
import re
from contextlib import closing
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

# Sheet header -> raw column. Columns that change every year go into a jsonb column instead.
SDD_COLUMNS = {
    "CSV": "csv_file",
    "Template": "template",
    "Item": "item",
    "Label": "label",
}
SDD_OPTIONAL = {"Category", "Collection"}  # Category from 2023, Collection from 2025
SDD_ALIASES = {"DERIVED_TEMPLATE": "Template"}  # the 2022 and 2023 name
PREVIOUS_ITEM = re.compile(r"^Item_\w+$")  # Item_TR_2024, and Item_ST_TR_16 in 2022

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


def _open(path: Path):
    return closing(openpyxl.load_workbook(path, read_only=True, data_only=True))


def _cell(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _read(
    ws: Worksheet, key: str, aliases: dict[str, str] | None = None
) -> tuple[list[str], list[dict]]:
    """Header and non-empty rows of a sheet. The header is the first row with a `key` cell:
    exercises put it on different rows and columns."""
    aliases = aliases or {}
    rows = ws.iter_rows(values_only=True)
    for row in rows:
        header = [str(h).strip() if h is not None else "" for h in row]
        header = [aliases.get(h, h) for h in header]
        if key in header:
            break
    else:
        raise ValueError(f"sheet {ws.title!r} has no header row with a {key!r} column")
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


def parse_items(path: Path) -> list[dict]:
    with _open(path) as wb:
        header, records = _read(wb["SDD"], key="Item", aliases=SDD_ALIASES)
    _check_header(f"{path} [SDD]", header, set(SDD_COLUMNS), SDD_OPTIONAL, PREVIOUS_ITEM)

    return [
        {
            **{col: r[h] for h, col in SDD_COLUMNS.items()},
            "category": r.get("Category"),
            "collection": r.get("Collection"),
            "previous_items": {h: v for h, v in r.items() if PREVIOUS_ITEM.match(h) and v},
        }
        for r in records
    ]


def parse_institutions(path: Path) -> list[dict]:
    with _open(path) as wb:
        header, records = _read(wb["List of Institutions"], key="LEI_Code")
    _check_header(
        f"{path} [List of Institutions]",
        header,
        set(INSTITUTION_COLUMNS),
        INSTITUTION_OPTIONAL,
        PREVIOUS_EXERCISE,
    )

    return [
        {
            **{col: r[h] for h, col in INSTITUTION_COLUMNS.items()},
            "footnotes": r.get("Footnotes"),
            "previous_exercises": {h: v for h, v in r.items() if PREVIOUS_EXERCISE.match(h) and v},
        }
        for r in records
    ]


def parse_dimension_codes(path: Path) -> list[dict]:
    codes = []
    with _open(path) as wb:
        for sheet in DIMENSION_SHEETS:
            header, records = _read(wb[sheet], key=sheet)
            _check_header(f"{path} [{sheet}]", header, {sheet, "Label"})
            codes += [{"dimension": sheet, "code": r[sheet], "label": r["Label"]} for r in records]
    return codes
