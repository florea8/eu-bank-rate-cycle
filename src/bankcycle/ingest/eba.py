import csv
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg
import requests
import yaml
from psycopg import sql
from psycopg.types.json import Jsonb

from bankcycle import db
from bankcycle.ingest import eba_metadata, http
from bankcycle.logging_conf import log_step
from bankcycle.settings import REPO_ROOT, get_settings

log = logging.getLogger(__name__)

SOURCES_FILE = REPO_ROOT / "config" / "sources.yaml"

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
HEADER_ALIASES = {"footnote": "Footnote"}  # the 2022 spelling

DDL = """
CREATE TABLE IF NOT EXISTS raw.eba_tr_oth (
    exercise              integer NOT NULL,
    lei_code              text NOT NULL,
    nsa                   text,
    period                text NOT NULL,
    item                  text NOT NULL,
    label                 text,
    assets_fv             text NOT NULL,
    assets_stages         text NOT NULL,
    exposure              text NOT NULL,
    financial_instruments text NOT NULL,
    amount                numeric,
    fin_end_year          text,
    n_quarters            text,
    footnote              text,
    sheet_row             text,
    sheet_column          text,
    sheet                 text,
    source_sha256         text NOT NULL,
    loaded_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exercise, lei_code, period, item,
                 assets_fv, assets_stages, exposure, financial_instruments)
)
"""

COPY = (
    "COPY raw.eba_tr_oth (exercise, "
    + ", ".join(TR_OTH_COLUMNS.values())
    + ", source_sha256) FROM STDIN"
)

TR_OTH = sql.Identifier("raw", "eba_tr_oth")
FILE_TABLES = {
    "tr_oth.csv": (TR_OTH,),
    "SDD.xlsx": (eba_metadata.ITEMS,),
    "TR_Metadata.xlsx": (eba_metadata.INSTITUTIONS, eba_metadata.DIMENSION_CODES),
}


@dataclass(frozen=True)
class EbaFile:
    exercise: int
    name: str
    url: str
    sha256: str | None

    def local_path(self, raw_dir: Path) -> Path:
        return raw_dir / "eba" / str(self.exercise) / self.name


def load_config(path: Path = SOURCES_FILE) -> list[EbaFile]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))["eba"]
    return [
        EbaFile(
            exercise=ex["year"],
            name=name,
            url=f"{ex['base_url'].rstrip('/')}/{name}",
            sha256=sha or None,
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


def fetch_file(file: EbaFile, raw_dir: Path, force: bool = False) -> bool:
    """Download one file unless a verified copy exists. Returns True if it downloaded."""
    path = file.local_path(raw_dir)
    if not force and file.sha256 and path.exists() and sha256_of(path) == file.sha256:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        digest = http.download(file.url, part)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            raise RuntimeError(
                f"EBA refused the download (403). Download it in a browser from {file.url} "
                f"and save it as {path}; the next run verifies its checksum and skips the download."
            ) from exc
        raise

    if file.sha256 is None:
        log.warning("%s has no pinned checksum; got %s", file.url, digest)
    elif digest != file.sha256:
        part.unlink()
        raise ValueError(f"checksum mismatch for {file.url}: expected {file.sha256}, got {digest}")

    part.replace(path)
    return True


def parse_tr_oth(path: Path) -> list[tuple]:
    """Rows in TR_OTH_COLUMNS order. Empty cells become NULL."""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [HEADER_ALIASES.get(h, h) for h in reader.fieldnames or []]
        header = set(reader.fieldnames)
        missing = set(TR_OTH_COLUMNS) - OPTIONAL_COLUMNS - header
        unexpected = header - set(TR_OTH_COLUMNS)
        if missing or unexpected:
            raise ValueError(
                f"{path}: missing columns {sorted(missing)}, unexpected columns {sorted(unexpected)}"
            )
        return [tuple(row.get(col) or None for col in TR_OTH_COLUMNS) for row in reader]


def already_loaded(
    conn: psycopg.Connection, exercise: int, sha256: str, table: sql.Identifier = TR_OTH
) -> bool:
    query = sql.SQL("SELECT 1 FROM {} WHERE exercise = %s AND source_sha256 = %s LIMIT 1")
    row = conn.execute(query.format(table), (exercise, sha256)).fetchone()
    return row is not None


def replace_exercise(
    conn: psycopg.Connection, exercise: int, sha256: str, rows: list[tuple]
) -> int:
    """Swap one exercise's rows for the given ones. The caller commits."""
    conn.execute("DELETE FROM raw.eba_tr_oth WHERE exercise = %s", (exercise,))
    with conn.cursor() as cur, cur.copy(COPY) as copy:
        for row in rows:
            copy.write_row((exercise, *row, sha256))
    return len(rows)


def replace_rows(
    conn: psycopg.Connection, table: sql.Identifier, exercise: int, sha256: str, rows: list[dict]
) -> int:
    """Like replace_exercise, for the small dictionary tables. Dict values are stored as jsonb."""
    conn.execute(sql.SQL("DELETE FROM {} WHERE exercise = %s").format(table), (exercise,))
    if not rows:
        return 0
    columns = ["exercise", *rows[0], "source_sha256"]
    insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        table,
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() * len(columns)),
    )
    params = [
        (exercise, *(Jsonb(v) if isinstance(v, dict) else v for v in row.values()), sha256)
        for row in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(insert, params)
    return len(rows)


def load_file(conn: psycopg.Connection, file: EbaFile, path: Path) -> int:
    """Load one downloaded file into its raw tables, unless this version is already there."""
    sha256 = sha256_of(path)
    if all(already_loaded(conn, file.exercise, sha256, t) for t in FILE_TABLES[file.name]):
        log.info("eba/%s/%s: this file is already loaded", file.exercise, file.name)
        return 0

    if file.name == "tr_oth.csv":
        return replace_exercise(conn, file.exercise, sha256, parse_tr_oth(path))
    if file.name == "SDD.xlsx":
        items = eba_metadata.parse_sdd(path)
        return replace_rows(conn, eba_metadata.ITEMS, file.exercise, sha256, items)

    institutions, codes = eba_metadata.parse_metadata(path)
    return replace_rows(
        conn, eba_metadata.INSTITUTIONS, file.exercise, sha256, institutions
    ) + replace_rows(conn, eba_metadata.DIMENSION_CODES, file.exercise, sha256, codes)


def run(force: bool = False) -> None:
    raw_dir = get_settings().data_dir / "raw"
    files = load_config()
    for file in files:
        with log_step(log, "ingest", source="eba", file=f"{file.exercise}/{file.name}"):
            if not fetch_file(file, raw_dir, force=force):
                log.info("eba/%s/%s: already downloaded, checksum matches", file.exercise, file.name)

    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute(eba_metadata.DDL)
        conn.commit()
        for file in files:
            with log_step(log, "load", source="eba", file=f"{file.exercise}/{file.name}") as ctx:
                ctx["rows"] = load_file(conn, file, file.local_path(raw_dir))
            conn.commit()
