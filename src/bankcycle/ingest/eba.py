import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import requests
import yaml

from bankcycle.ingest import http
from bankcycle.logging_conf import log_step
from bankcycle.settings import REPO_ROOT, get_settings

log = logging.getLogger(__name__)

SOURCES_FILE = REPO_ROOT / "config" / "sources.yaml"


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


def run(force: bool = False) -> None:
    raw_dir = get_settings().data_dir / "raw"
    for file in load_config():
        with log_step(log, "ingest", source="eba", file=f"{file.exercise}/{file.name}"):
            if not fetch_file(file, raw_dir, force=force):
                log.info("eba/%s/%s: already downloaded, checksum matches", file.exercise, file.name)
