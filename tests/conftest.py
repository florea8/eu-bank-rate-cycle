import logging

import pytest

from bankcycle import db, logging_conf, settings


@pytest.fixture
def pg_conn():
    """A real connection whose changes are rolled back after the test."""
    if not db.is_up():
        pytest.skip("PostgreSQL not reachable")
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def clean_env(monkeypatch):
    """Settings built only from what the test sets, never from the local .env."""
    monkeypatch.setattr(settings, "load_dotenv", lambda *a, **k: None)
    for name in ("DATA_DIR", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
                 "LOG_LEVEL", "SAMPLE_MODE", "ECB_START_PERIOD", "HTTP_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)
    settings.get_settings.cache_clear()
    yield monkeypatch
    settings.get_settings.cache_clear()


@pytest.fixture
def tmp_log_file(tmp_path, monkeypatch):
    log_file = tmp_path / "pipeline.jsonl"
    monkeypatch.setattr(logging_conf, "LOG_FILE", log_file)
    root = logging.getLogger()
    saved = root.handlers[:]
    yield log_file
    for handler in root.handlers:
        if handler not in saved:
            handler.close()
    root.handlers[:] = saved
