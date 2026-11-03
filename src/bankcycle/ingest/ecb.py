import csv
import io
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg
import yaml

from bankcycle import db
from bankcycle.ingest import http
from bankcycle.logging_conf import log_step
from bankcycle.settings import REPO_ROOT, get_settings

log = logging.getLogger(__name__)

SOURCES_FILE = REPO_ROOT / "config" / "sources.yaml"
REQUIRED_COLUMNS = {"KEY", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "TITLE"}
REVISION_OVERLAP_MONTHS = 3

DDL = """
CREATE TABLE IF NOT EXISTS raw.ecb_observations (
    series_id   text NOT NULL,
    series_key  text NOT NULL,
    time_period text NOT NULL,
    obs_value   double precision,
    obs_status  text,
    title       text,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (series_key, time_period)
)
"""

UPSERT = """
INSERT INTO raw.ecb_observations
    (series_id, series_key, time_period, obs_value, obs_status, title)
VALUES
    (%(series_id)s, %(series_key)s, %(time_period)s, %(obs_value)s, %(obs_status)s, %(title)s)
ON CONFLICT (series_key, time_period) DO UPDATE SET
    series_id  = EXCLUDED.series_id,
    obs_value  = EXCLUDED.obs_value,
    obs_status = EXCLUDED.obs_status,
    title      = EXCLUDED.title,
    loaded_at  = now()
WHERE (ecb_observations.obs_value, ecb_observations.obs_status)
      IS DISTINCT FROM (EXCLUDED.obs_value, EXCLUDED.obs_status)
"""


@dataclass(frozen=True)
class Series:
    id: str
    flow: str
    key: str

    @property
    def full_key(self) -> str:
        return f"{self.flow}.{self.key}"


def load_config(path: Path = SOURCES_FILE) -> tuple[str, list[Series]]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))["ecb"]
    series = [Series(id=s["id"], flow=s["flow"], key=s["key"]) for s in cfg["series"]]
    return cfg["base_url"], series


def fetch(base_url: str, series: Series, start_period: str) -> bytes:
    url = f"{base_url}/data/{series.flow}/{series.key}"
    resp = http.get(url, params={"format": "csvdata", "startPeriod": start_period})
    return resp.content


def parse(content: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"ECB response is missing columns: {sorted(missing)}")

    return [
        {
            "series_key": row["KEY"],
            "time_period": row["TIME_PERIOD"],
            "obs_value": float(row["OBS_VALUE"]) if row["OBS_VALUE"] else None,
            "obs_status": row["OBS_STATUS"],
            "title": row["TITLE"],
        }
        for row in reader
    ]


def save_raw(
    content: bytes, series_id: str, start_period: str, raw_dir: Path, run_date: date
) -> Path:
    path = raw_dir / "ecb" / run_date.isoformat() / f"{series_id}_from_{start_period}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def incremental_start(latest_period: str | None, default: str) -> str:
    """Month to request from: the latest loaded month minus the revision overlap."""
    if latest_period is None:
        return default
    year, month = int(latest_period[:4]), int(latest_period[5:7])
    index = year * 12 + (month - 1) - REVISION_OVERLAP_MONTHS
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def latest_period(conn: psycopg.Connection, series_key: str) -> str | None:
    row = conn.execute(
        "SELECT max(time_period) FROM raw.ecb_observations WHERE series_key = %s",
        (series_key,),
    ).fetchone()
    return row[0] if row else None


def upsert(conn: psycopg.Connection, series_id: str, rows: list[dict]) -> int:
    """Insert new observations and update revised ones. Returns rows written."""
    with conn.cursor() as cur:
        cur.executemany(UPSERT, [{"series_id": series_id, **r} for r in rows])
        return cur.rowcount


def run() -> None:
    s = get_settings()
    base_url, series_list = load_config()
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        for series in series_list:
            with log_step(log, "ingest", source="ecb", file=series.id) as ctx:
                start = incremental_start(latest_period(conn, series.full_key), s.ecb_start_period)
                log.info("ecb/%s: requesting from %s", series.id, start)
                content = fetch(base_url, series, start)
                save_raw(content, series.id, start, s.data_dir / "raw", date.today())
                ctx["rows"] = upsert(conn, series.id, parse(content))
            conn.commit()
