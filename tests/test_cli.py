import json

import pytest

from bankcycle import cli, db


def test_db_check_ok(monkeypatch, tmp_log_file):
    monkeypatch.setattr(db, "is_up", lambda: True)

    assert cli.main(["db-check"]) == 0

    event = json.loads(tmp_log_file.read_text(encoding="utf-8").splitlines()[-1])
    assert event["step"] == "db-check"
    assert event["status"] == "ok"


def test_db_check_down_returns_1(monkeypatch, tmp_log_file):
    monkeypatch.setattr(db, "is_up", lambda: False)

    assert cli.main(["db-check"]) == 1

    lines = tmp_log_file.read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line).get("status") == "failed" for line in lines)


def test_unknown_command_exits():
    with pytest.raises(SystemExit):
        cli.main(["nope"])
