import hashlib

import pytest

from bankcycle.ingest import eba

CONTENT = b"LEI_Code,Period\nX,202506\n"
FILE = eba.EbaFile(exercise=2025, name="tr_oth.csv", url="https://example.test/tr_oth.csv",
                   sha256=hashlib.sha256(CONTENT).hexdigest())


def test_load_config_builds_urls():
    files = eba.load_config()
    names = {(f.exercise, f.name) for f in files}

    assert {(2024, "tr_oth.csv"), (2025, "tr_oth.csv"), (2025, "SDD.xlsx")} <= names
    for f in files:
        assert f.url.startswith("https://www.eba.europa.eu/assets/TE")
        assert f.url.endswith("/" + f.name)
        assert len(f.sha256) == 64


def test_local_path(tmp_path):
    assert FILE.local_path(tmp_path) == tmp_path / "eba" / "2025" / "tr_oth.csv"


def test_verify_accepts_the_pinned_file(tmp_path):
    path = tmp_path / "tr_oth.csv"
    path.write_bytes(CONTENT)

    eba.verify(FILE, path)


def test_verify_says_where_to_download_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Download it in a browser from https://example.test"):
        eba.verify(FILE, tmp_path / "tr_oth.csv")


def test_verify_rejects_a_different_file(tmp_path):
    path = tmp_path / "tr_oth.csv"
    path.write_bytes(b"another exercise's file")

    with pytest.raises(ValueError, match="is not the pinned file"):
        eba.verify(FILE, path)


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

    assert list(parsed) == list(eba.TR_OTH_COLUMNS.values())
    assert parsed["lei_code"] == "LEI1"
    assert parsed["amount"] == "7054.23"
    assert parsed["footnote"] is None


def test_parse_tr_oth_empty_amount_is_null(tmp_path):
    row = ["LEI1", "DE", "202506", "2520101", "OWN FUNDS", "0", "0", "0", "0", "",
           "0", "2", "7", "5", "Capital"]
    path = _write_csv(tmp_path / "tr_oth.csv", HEADER_2025, [row])

    (parsed,) = eba.parse_tr_oth(path)

    assert parsed["amount"] is None


def test_parse_tr_oth_2022_layout(tmp_path):
    header = [c for c in eba.TR_OTH_COLUMNS if c not in ("Footnote", "Row", "Column", "Sheet")]
    header.append("footnote")
    row = ["LEI1", "DE", "202206", "2220101", "OWN FUNDS", "0", "0", "0", "0", "7054.23",
           "0", "2", "A note"]
    path = _write_csv(tmp_path / "tr_oth.csv", header, [row])

    (parsed,) = eba.parse_tr_oth(path)

    assert parsed["footnote"] == "A note"
    assert parsed["sheet"] is None


def test_parse_tr_oth_reads_windows_1252(tmp_path):
    row = ["LEI1", "DE", "202106", "2121007", "Derivatives – Hedge accounting", "0", "0", "0",
           "0", "1.5", "0", "2", "7", "5", "Assets"]
    path = _write_csv(tmp_path / "tr_oth.csv", HEADER_2025, [row])
    path.write_bytes(path.read_text(encoding="utf-8").encode("cp1252"))

    (parsed,) = eba.parse_tr_oth(path)

    assert parsed["label"] == "Derivatives – Hedge accounting"


def test_parse_tr_oth_rejects_changed_header(tmp_path):
    header = [c for c in HEADER_2025 if c != "Amount"] + ["Value"]
    path = _write_csv(tmp_path / "tr_oth.csv", header, [])

    with pytest.raises(ValueError, match=r"missing columns \['Amount'\], unexpected columns \['Value'\]"):
        eba.parse_tr_oth(path)
