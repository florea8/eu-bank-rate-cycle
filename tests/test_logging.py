import json
import logging

import pytest

from bankcycle.logging_conf import JsonLineFormatter, log_step

log = logging.getLogger("bankcycle.test")


def test_log_step_ok_records_rows_and_duration(caplog):
    caplog.set_level(logging.INFO)
    with log_step(log, "load", source="ecb") as ctx:
        ctx["rows"] = 42

    record = caplog.records[-1]
    assert record.status == "ok"
    assert record.step == "load"
    assert record.source == "ecb"
    assert record.rows == 42
    assert record.duration_ms >= 0


def test_log_step_failure_is_logged_and_reraised(caplog):
    with pytest.raises(ValueError, match="bad file"):
        with log_step(log, "load"):
            raise ValueError("bad file")

    record = caplog.records[-1]
    assert record.levelname == "ERROR"
    assert record.status == "failed"


def test_json_line_formatter():
    record = logging.LogRecord("bankcycle", logging.INFO, __file__, 1, "done", None, None)
    record.step = "ingest"
    record.rows = 10

    payload = json.loads(JsonLineFormatter().format(record))

    assert payload["msg"] == "done"
    assert payload["level"] == "INFO"
    assert payload["step"] == "ingest"
    assert payload["rows"] == 10
    assert "file" not in payload
