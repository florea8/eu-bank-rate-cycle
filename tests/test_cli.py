import json
from types import SimpleNamespace

import pytest
from dbt.cli import main as dbt_main

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


@pytest.fixture
def fake_dbt(monkeypatch):
    calls: list[list[str]] = []
    outcome = {"success": True}

    class FakeRunner:
        def invoke(self, args):
            calls.append(args)
            return SimpleNamespace(success=outcome["success"])

    monkeypatch.setattr(dbt_main, "dbtRunner", FakeRunner)
    return calls, outcome


def test_dbt_passes_args_and_project_dir(fake_dbt, tmp_log_file):
    calls, _ = fake_dbt

    assert cli.main(["dbt", "build", "--select", "staging"]) == 0

    (args,) = calls
    assert args[:3] == ["build", "--select", "staging"]
    assert args[args.index("--project-dir") + 1] == str(cli.DBT_DIR)
    assert args[args.index("--profiles-dir") + 1] == str(cli.DBT_DIR)


def test_dbt_failure_returns_1(fake_dbt, tmp_log_file):
    _, outcome = fake_dbt
    outcome["success"] = False

    assert cli.main(["dbt", "test"]) == 1
