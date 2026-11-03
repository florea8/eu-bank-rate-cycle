from datetime import date
from pathlib import Path

import pytest
import requests
from tenacity import wait_none

from bankcycle.ingest import ecb, http

FIXTURE = Path(__file__).parent / "fixtures" / "ecb_dfr.csv"


def test_parse_real_response():
    rows = ecb.parse(FIXTURE.read_bytes())

    assert len(rows) == 4
    assert rows[0] == {
        "series_key": "FM.D.U2.EUR.4F.KR.DFR.LEV",
        "time_period": "2022-07-25",
        "obs_value": -0.5,
        "obs_status": "A",
        "title": "Deposit facility - date of changes (raw data) - Level",
    }
    assert [r["obs_value"] for r in rows] == [-0.5, -0.5, 0.0, 0.0]


def test_parse_fails_on_missing_columns():
    with pytest.raises(ValueError, match="OBS_VALUE"):
        ecb.parse(b"KEY,TIME_PERIOD,OBS_STATUS,TITLE\nX,2024-01-01,A,t\n")


def test_parse_empty_value_is_none():
    content = b"KEY,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE\nX,2024-01-01,,M,t\n"
    assert ecb.parse(content)[0]["obs_value"] is None


def test_save_raw_layout(tmp_path):
    path = ecb.save_raw(b"abc", "dfr", "2026-08", tmp_path, date(2026, 11, 3))
    assert path == tmp_path / "ecb" / "2026-11-03" / "dfr_from_2026-08.csv"
    assert path.read_bytes() == b"abc"


@pytest.mark.parametrize(
    "latest, expected",
    [
        (None, "2019-01"),
        ("2026-11-02", "2026-08"),
        ("2025-06", "2025-03"),
        ("2025-02-14", "2024-11"),
        ("2025-03", "2024-12"),
    ],
)
def test_incremental_start(latest, expected):
    assert ecb.incremental_start(latest, default="2019-01") == expected


def test_load_config_has_dfr():
    base_url, series = ecb.load_config()
    assert base_url.startswith("https://")
    assert ecb.Series("dfr", "FM", "D.U2.EUR.4F.KR.DFR.LEV") in series


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.url = "https://example.test/data"
        self.content = b"ok"


def _fake_get(statuses: list[int], calls: list[int]):
    def fake(url, params=None, timeout=None):
        calls.append(1)
        return FakeResponse(statuses[len(calls) - 1])
    return fake


def test_http_4xx_fails_without_retry(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(requests, "get", _fake_get([404], calls))
    get = http.get.retry_with(wait=wait_none())

    with pytest.raises(requests.HTTPError, match="404"):
        get("https://example.test/data")
    assert len(calls) == 1


def test_http_5xx_is_retried(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(requests, "get", _fake_get([503, 502, 200], calls))
    get = http.get.retry_with(wait=wait_none())

    assert get("https://example.test/data").content == b"ok"
    assert len(calls) == 3


def test_http_gives_up_after_4_attempts(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(requests, "get", _fake_get([500] * 4, calls))
    get = http.get.retry_with(wait=wait_none())

    with pytest.raises(requests.HTTPError, match="500"):
        get("https://example.test/data")
    assert len(calls) == 4
