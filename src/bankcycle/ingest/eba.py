import csv
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from bankcycle.ingest import eba_metadata
from bankcycle.logging_conf import log_step
from bankcycle.settings import get_settings, load_sources

log = logging.getLogger(__name__)

# CSV header -> raw column. "Row" and "Column" are renamed because COLUMN is reserved in SQL.
TR_OTH_COLUMNS = {
    "LEI_Code": "lei_code",
    "NSA": "nsa",
    "Period": "period",
    "Item": "item",
    "Label": "label",
    "ASSETS_FV": "assets_fv",
    "ASSETS_Stages": "assets_stages",
    "Exposure": "exposure",
    "Financial_instruments": "financial_instruments",
    "Amount": "amount",
    "Fin_end_year": "fin_end_year",
    "n_quarters": "n_quarters",
    "Footnote": "footnote",
    "Row": "sheet_row",
    "Column": "sheet_column",
    "Sheet": "sheet",
}
# Footnote is missing in 2025; Row, Column and Sheet only exist from 2023.
OPTIONAL_COLUMNS = {"Footnote", "Row", "Column", "Sheet"}
HEADER_ALIASES = {"footnote": "Footnote"}  # the 2021 and 2022 spelling


@dataclass(frozen=True)
class EbaFile:
    exercise: int
    name: str
    url: str
    sha256: str

    def local_path(self, raw_dir: Path) -> Path:
        return raw_dir / "eba" / str(self.exercise) / self.name


def load_config() -> list[EbaFile]:
    cfg = load_sources()["eba"]
    return [
        EbaFile(
            exercise=ex["year"],
            name=name,
            url=f"{ex['base_url'].rstrip('/')}/{name}",
            sha256=sha,
        )
        for ex in cfg["exercises"]
        for name, sha in ex["files"].items()
    ]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(file: EbaFile, path: Path) -> None:
    """EBA refuses scripted downloads, so the files are saved by hand. Check that this one
    is in place and is the pinned version."""
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Download it in a browser from {file.url}")
    digest = sha256_of(path)
    if digest != file.sha256:
        raise ValueError(
            f"{path} is not the pinned file (SHA-256 {digest}, expected {file.sha256}). "
            f"Download it again from {file.url}"
        )


def read_text(path: Path) -> str:
    """The 2021 file is saved as Windows-1252, the later ones as UTF-8."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def parse_tr_oth(path: Path) -> list[dict]:
    """One dict per row, keyed by raw column. Empty cells become NULL."""
    reader = csv.DictReader(io.StringIO(read_text(path), newline=""))
    reader.fieldnames = [HEADER_ALIASES.get(h, h) for h in reader.fieldnames or []]
    header = set(reader.fieldnames)
    missing = set(TR_OTH_COLUMNS) - OPTIONAL_COLUMNS - header
    unexpected = header - set(TR_OTH_COLUMNS)
    if missing or unexpected:
        raise ValueError(
            f"{path}: missing columns {sorted(missing)}, unexpected columns {sorted(unexpected)}"
        )
    return [{col: row.get(h) or None for h, col in TR_OTH_COLUMNS.items()} for row in reader]


# Source file -> the raw tables it fills, each with the parser that returns its rows.
LOADERS = {
    "tr_oth.csv": {"eba_tr_oth": parse_tr_oth},
    "SDD.xlsx": {"eba_items": eba_metadata.parse_items},
    "TR_Metadata.xlsx": {"eba_institutions": eba_metadata.parse_institutions},
}


def already_loaded(conn: psycopg.Connection, table: str, exercise: int, sha256: str) -> bool:
    query = sql.SQL("SELECT 1 FROM {} WHERE exercise = %s AND source_sha256 = %s LIMIT 1")
    row = conn.execute(query.format(sql.Identifier("raw", table)), (exercise, sha256)).fetchone()
    return row is not None


def replace_rows(
    conn: psycopg.Connection, table: str, exercise: int, sha256: str, rows: list[dict]
) -> int:
    """Swap one exercise's rows in a raw table for the given ones. The caller commits."""
    target = sql.Identifier("raw", table)
    conn.execute(sql.SQL("DELETE FROM {} WHERE exercise = %s").format(target), (exercise,))
    if not rows:
        return 0
    columns = sql.SQL(", ").join(map(sql.Identifier, ["exercise", *rows[0], "source_sha256"]))
    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(target, columns)
    with conn.cursor() as cur, cur.copy(copy_sql) as copy:
        for row in rows:
            values = (Jsonb(v) if isinstance(v, dict) else v for v in row.values())
            copy.write_row((exercise, *values, sha256))
    return len(rows)


def load_file(conn: psycopg.Connection, file: EbaFile, path: Path) -> int:
    """Load one verified file into its raw tables, unless this version is already there."""
    written = 0
    for table, parse in LOADERS[file.name].items():
        if not already_loaded(conn, table, file.exercise, file.sha256):
            written += replace_rows(conn, table, file.exercise, file.sha256, parse(path))
    if not written:
        log.info("eba/%s/%s: this file is already loaded", file.exercise, file.name)
    return written


def run(conn: psycopg.Connection) -> None:
    raw_dir = get_settings().data_dir / "raw"
    for file in load_config():
        path = file.local_path(raw_dir)
        with log_step(log, "load", source="eba", file=f"{file.exercise}/{file.name}") as ctx:
            verify(file, path)
            ctx["rows"] = load_file(conn, file, path)
        conn.commit()
