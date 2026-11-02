import json
import logging
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime

from bankcycle.settings import REPO_ROOT, get_settings

LOG_FILE = REPO_ROOT / "logs" / "pipeline.jsonl"
EVENT_FIELDS = ("step", "source", "file", "rows", "duration_ms", "status")


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in EVENT_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(get_settings().log_level)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    )
    root.addHandler(console)

    jsonl = logging.FileHandler(LOG_FILE, encoding="utf-8")
    jsonl.setFormatter(JsonLineFormatter())
    root.addHandler(jsonl)

    for noisy in ("urllib3", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextmanager
def log_step(logger: logging.Logger, step: str, **fields) -> Generator[dict]:
    """Log one event per step with its duration. Set ctx["rows"] inside the block to record it."""
    ctx: dict = {}
    start = time.perf_counter()
    try:
        yield ctx
    except Exception:
        ms = round((time.perf_counter() - start) * 1000)
        logger.error(
            "%s failed",
            step,
            extra={"step": step, "status": "failed", "duration_ms": ms, **fields, **ctx},
        )
        raise
    ms = round((time.perf_counter() - start) * 1000)
    target = "/".join(str(fields[k]) for k in ("source", "file") if k in fields)
    label = f"{step} {target}" if target else step
    rows = f", {ctx['rows']} rows" if "rows" in ctx else ""
    logger.info(
        "%s ok%s (%d ms)",
        label,
        rows,
        ms,
        extra={"step": step, "status": "ok", "duration_ms": ms, **fields, **ctx},
    )
