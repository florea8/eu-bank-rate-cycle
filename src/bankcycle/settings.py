import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_FILE = REPO_ROOT / "config" / "sources.yaml"


def load_sources() -> dict:
    """What to download, per source, from config/sources.yaml."""
    return yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    pghost: str
    pgport: int
    pgdatabase: str
    pguser: str
    pgpassword: str
    log_level: str
    ecb_start_period: str
    http_timeout_s: int


@lru_cache
def get_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    return Settings(
        data_dir=data_dir,
        pghost=os.getenv("PGHOST", "localhost"),
        pgport=int(os.getenv("PGPORT", "5432")),
        pgdatabase=os.getenv("PGDATABASE", "bankcycle"),
        pguser=os.getenv("PGUSER", "bankcycle"),
        pgpassword=os.getenv("PGPASSWORD", ""),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        ecb_start_period=os.getenv("ECB_START_PERIOD", "2019-01"),
        http_timeout_s=int(os.getenv("HTTP_TIMEOUT_S", "60")),
    )
