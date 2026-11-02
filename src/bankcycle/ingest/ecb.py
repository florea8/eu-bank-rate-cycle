import csv
import io
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from bankcycle.ingest import http
from bankcycle.logging_conf import log_step
from bankcycle.settings import REPO_ROOT, get_settings

log = logging.getLogger(__name__)

SOURCES_FILE = REPO_ROOT / "config" / "sources.yaml"
REQUIRED_COLUMNS = {"KEY", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "TITLE"}


@dataclass(frozen=True)
class Series:
    id: str
    flow: str
    key: str


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


def save_raw(content: bytes, series_id: str, raw_dir: Path, run_date: date) -> Path:
    path = raw_dir / "ecb" / run_date.isoformat() / f"{series_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def run() -> None:
    s = get_settings()
    base_url, series_list = load_config()
    for series in series_list:
        with log_step(log, "ingest", source="ecb", file=series.id) as ctx:
            content = fetch(base_url, series, s.ecb_start_period)
            save_raw(content, series.id, s.data_dir / "raw", date.today())
            ctx["rows"] = len(parse(content))
