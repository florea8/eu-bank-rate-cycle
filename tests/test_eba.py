import hashlib

import pytest
import requests

from bankcycle.ingest import eba, http

CONTENT = b"LEI_Code,Period\nX,202506\n"
SHA = hashlib.sha256(CONTENT).hexdigest()


def _file(sha: str | None = SHA) -> eba.EbaFile:
    return eba.EbaFile(exercise=2025, name="tr_oth.csv", url="https://example.test/tr_oth.csv",
                       sha256=sha)


@pytest.fixture
def fake_download(monkeypatch):
    calls: list[str] = []

    def fake(url, dest, content=CONTENT):
        calls.append(url)
        dest.write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    monkeypatch.setattr(http, "download", fake)
    return calls


def test_load_config_builds_urls():
    files = eba.load_config()
    names = {(f.exercise, f.name) for f in files}

    assert {(2024, "tr_oth.csv"), (2025, "tr_oth.csv"), (2025, "SDD.xlsx")} <= names
    for f in files:
        assert f.url.startswith("https://www.eba.europa.eu/assets/TE")
        assert f.url.endswith("/" + f.name)
        assert f.sha256 is not None and len(f.sha256) == 64


def test_local_path(tmp_path):
    assert _file().local_path(tmp_path) == tmp_path / "eba" / "2025" / "tr_oth.csv"


def test_downloads_when_missing(tmp_path, fake_download):
    assert eba.fetch_file(_file(), tmp_path) is True
    assert _file().local_path(tmp_path).read_bytes() == CONTENT
    assert len(fake_download) == 1


def test_skips_when_checksum_matches(tmp_path, fake_download):
    eba.fetch_file(_file(), tmp_path)
    assert eba.fetch_file(_file(), tmp_path) is False
    assert len(fake_download) == 1


def test_force_downloads_again(tmp_path, fake_download):
    eba.fetch_file(_file(), tmp_path)
    assert eba.fetch_file(_file(), tmp_path, force=True) is True
    assert len(fake_download) == 2


def test_redownloads_corrupted_file(tmp_path, fake_download):
    path = _file().local_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"truncated")

    assert eba.fetch_file(_file(), tmp_path) is True
    assert path.read_bytes() == CONTENT


def test_checksum_mismatch_fails_and_keeps_nothing(tmp_path, fake_download):
    with pytest.raises(ValueError, match="checksum mismatch"):
        eba.fetch_file(_file(sha="0" * 64), tmp_path)

    folder = tmp_path / "eba" / "2025"
    assert list(folder.iterdir()) == []


def test_403_explains_manual_download(tmp_path, monkeypatch):
    def refused(url, dest):
        resp = requests.Response()
        resp.status_code = 403
        raise requests.HTTPError("HTTP 403", response=resp)

    monkeypatch.setattr(http, "download", refused)

    with pytest.raises(RuntimeError, match="Download it in a browser") as exc_info:
        eba.fetch_file(_file(), tmp_path)
    assert str(_file().local_path(tmp_path)) in str(exc_info.value)


def test_unpinned_file_is_kept_with_warning(tmp_path, fake_download, caplog):
    assert eba.fetch_file(_file(sha=None), tmp_path) is True
    assert SHA in caplog.text


HEADER_2025 = [c for c in eba.TR_OTH_COLUMNS if c != "Footnote"]


def _write_csv(path, header, rows):
    lines = [",".join(f'"{c}"' for c in header)] + [",".join(f'"{v}"' for v in r) for r in rows]
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def test_parse_tr_oth_without_footnote(tmp_path):
    row = ["LEI1", "DE", "202506", "2520101", "OWN FUNDS", "0", "0", "0", "0", "7054.23",
           "0", "2", "7", "5", "Capital"]
    path = _write_csv(tmp_path / "tr_oth.csv", HEADER_2025, [row])

    (parsed,) = eba.parse_tr_oth(path)

    assert len(parsed) == len(eba.TR_OTH_COLUMNS)
    assert parsed[0] == "LEI1"
    assert parsed[list(eba.TR_OTH_COLUMNS).index("Amount")] == "7054.23"
    assert parsed[list(eba.TR_OTH_COLUMNS).index("Footnote")] is None


def test_parse_tr_oth_empty_amount_is_null(tmp_path):
    row = ["LEI1", "DE", "202506", "2520101", "OWN FUNDS", "0", "0", "0", "0", "",
           "0", "2", "7", "5", "Capital"]
    path = _write_csv(tmp_path / "tr_oth.csv", HEADER_2025, [row])

    (parsed,) = eba.parse_tr_oth(path)

    assert parsed[list(eba.TR_OTH_COLUMNS).index("Amount")] is None


def test_parse_tr_oth_rejects_changed_header(tmp_path):
    header = [c for c in HEADER_2025 if c != "Amount"] + ["Value"]
    path = _write_csv(tmp_path / "tr_oth.csv", header, [])

    with pytest.raises(ValueError, match=r"missing columns \['Amount'\], unexpected columns \['Value'\]"):
        eba.parse_tr_oth(path)
