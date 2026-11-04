import openpyxl
import pytest

from bankcycle.ingest import eba_metadata

SDD_HEADER = ["CSV", "Template", "Collection", "Item", "Item_TR_2024", "Item_TR_2023",
              "Category", "Label"]
INSTITUTION_HEADER = ["Country", "Desc_country", "LEI_Code", "Name", "Finrep", "Fin_year_end",
                      "Footnotes", "TE_24", "LEI_Code_TE24"]


def _sdd(path, header=SDD_HEADER, rows=(), title=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SDD"
    if title:
        ws.append([None, None, None, None, "For reference, previous exercises' items"])
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _metadata(path, institutions=(), header=INSTITUTION_HEADER):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "List of Institutions"
    ws.append(["2025 EU-wide Transparency Exercise"])
    ws.append(header)
    for row in institutions:
        ws.append(row)
    for sheet in eba_metadata.DIMENSION_SHEETS:
        ws = wb.create_sheet(sheet)
        ws.append([sheet, "Label"])
        ws.append([0, "Total / No breakdown"])
        ws.append([None, None])
    wb.save(path)
    return path


def test_parse_sdd_keeps_previous_codes(tmp_path):
    path = _sdd(tmp_path / "SDD.xlsx", rows=[
        ["tr_oth.csv", "Capital", "TR2025", 2520101, 2420101, 2320101, "Capital", "OWN FUNDS"],
        ["tr_oth.csv", "Capital", "TR2025", 2520154, None, None, "Capital", "NEW ITEM"],
        [None] * 8,
    ])

    first, new = eba_metadata.parse_sdd(path)

    assert first == {
        "csv_file": "tr_oth.csv",
        "template": "Capital",
        "item": "2520101",
        "category": "Capital",
        "label": "OWN FUNDS",
        "collection": "TR2025",
        "previous_items": {"Item_TR_2024": "2420101", "Item_TR_2023": "2320101"},
    }
    assert new["previous_items"] == {}


def test_parse_sdd_without_collection(tmp_path):
    header = [c for c in SDD_HEADER if c != "Collection"]
    path = _sdd(tmp_path / "SDD.xlsx", header=header,
                rows=[["tr_oth.csv", "Capital", 2420101, 2320101, 2220101, "Capital", "OWN FUNDS"]])

    (item,) = eba_metadata.parse_sdd(path)

    assert item["collection"] is None
    assert item["item"] == "2420101"


def test_parse_sdd_2022_layout(tmp_path):
    header = ["CSV", "DERIVED_TEMPLATE", "Item", "Item_TR_2021", "Item_ST_TR_16", "Label"]
    path = _sdd(tmp_path / "SDD.xlsx", header=header, title=False,
                rows=[["tr_oth.csv", "Capital", 2220101, 2120101, 1690801, "OWN FUNDS"]])

    (item,) = eba_metadata.parse_sdd(path)

    assert item["template"] == "Capital"
    assert item["category"] is None
    assert item["previous_items"] == {"Item_TR_2021": "2120101", "Item_ST_TR_16": "1690801"}


def test_parse_sdd_rejects_changed_header(tmp_path):
    header = [c if c != "Label" else "Description" for c in SDD_HEADER]
    path = _sdd(tmp_path / "SDD.xlsx", header=header)

    with pytest.raises(ValueError, match=r"missing columns \['Label'\], unexpected columns \['Description'\]"):
        eba_metadata.parse_sdd(path)


def test_parse_metadata(tmp_path):
    path = _metadata(tmp_path / "TR_Metadata.xlsx", institutions=[
        ["AT", "Austria", "LEI1", "Bank One", "Yes - IFRS", "31-Dec", "", "1", "LEI1"],
        ["AT", "Austria", "LEI2", "Bank Two", "Yes - IFRS", "31-Dec", "A note", None, ""],
    ])

    institutions, codes = eba_metadata.parse_metadata(path)

    assert institutions[0] == {
        "lei_code": "LEI1",
        "country": "AT",
        "country_name": "Austria",
        "name": "Bank One",
        "finrep": "Yes - IFRS",
        "fin_year_end": "31-Dec",
        "footnotes": None,
        "previous_exercises": {"TE_24": "1", "LEI_Code_TE24": "LEI1"},
    }
    assert institutions[1]["footnotes"] == "A note"
    assert institutions[1]["previous_exercises"] == {}
    assert {c["dimension"] for c in codes} == set(eba_metadata.DIMENSION_SHEETS)
    assert codes[0] == {"dimension": "ASSETS_FV", "code": "0", "label": "Total / No breakdown"}


def test_parse_metadata_finds_offset_dimension_header(tmp_path):
    path = _metadata(tmp_path / "TR_Metadata.xlsx")
    wb = openpyxl.load_workbook(path)
    del wb["Exposure"]
    ws = wb.create_sheet("Exposure")
    ws.append([None, None, None])
    ws.append([None, None, "Exposure", "Label"])
    ws.append([None, None, None, None])
    ws.append([None, None, 101, "Central banks"])
    wb.save(path)

    _, codes = eba_metadata.parse_metadata(path)

    assert {"dimension": "Exposure", "code": "101", "label": "Central banks"} in codes


def test_parse_metadata_rejects_changed_header(tmp_path):
    header = [c for c in INSTITUTION_HEADER if c != "Name"]
    path = _metadata(tmp_path / "TR_Metadata.xlsx", header=header)

    with pytest.raises(ValueError, match=r"List of Institutions.*missing columns \['Name'\]"):
        eba_metadata.parse_metadata(path)
