"""Tests for facility registry builder combining NPPES and POS sources."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from asre.facility.registry_builder import build_combined_registry


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def test_build_combined_registry(tmp_path: Path) -> None:
    nppes_path = tmp_path / "nppes.csv"
    other_path = tmp_path / "othername.csv"
    pos_hosp_path = tmp_path / "pos_hosp.csv"
    pos_iqies_path = tmp_path / "pos_iqies.csv"
    out_path = tmp_path / "facility_registry.csv"

    # Minimal NPPES sample with one org + one individual
    nppes_header = [
        "NPI",
        "Entity Type Code",
        "Provider Organization Name (Legal Business Name)",
        "Provider Other Organization Name",
        "Provider First Line Business Practice Location Address",
        "Provider Business Practice Location Address City Name",
        "Provider Business Practice Location Address State Name",
        "Provider Business Practice Location Address Postal Code",
        "Healthcare Provider Taxonomy Code_1",
    ]
    nppes_rows = [
        ["1234567890", "2", "Alpha Hospital", "Alpha Hosp", "1 Main St", "Boston", "MA", "02110", "282N00000X"],
        ["9999999999", "1", "John Doe", "", "", "", "", "", ""],
    ]
    _write_csv(nppes_path, nppes_header, nppes_rows)

    other_header = ["NPI", "Provider Other Organization Name", "Provider Other Organization Name Type Code"]
    other_rows = [["1234567890", "Alpha Health System", "01"]]
    _write_csv(other_path, other_header, other_rows)

    pos_hosp_header = [
        "PRVDR_CTGRY_SBTYP_CD",
        "PRVDR_CTGRY_CD",
        "CITY_NAME",
        "FAC_NAME",
        "PRVDR_NUM",
        "STATE_CD",
        "ST_ADR",
        "ZIP_CD",
        "GNRL_FAC_TYPE_CD",
        "MLT_FAC_ORG_NAME",
    ]
    pos_hosp_rows = [
        ["01", "01", "Boston", "Beta Medical Center", "010001", "MA", "2 Main St", "02111", "01", "Beta Health"],
    ]
    _write_csv(pos_hosp_path, pos_hosp_header, pos_hosp_rows)

    pos_iqies_header = [
        "prvdr_num",
        "fac_name",
        "prvdr_type_id",
        "gnrl_fac_type_cd",
        "mlt_fac_org_name",
        "st_adr",
        "city_name",
        "state_cd",
        "zip_cd",
    ]
    pos_iqies_rows = [
        ["330001", "Gamma Hospice", "HSPC", "HSPC", "Gamma Health", "3 Main St", "Denver", "CO", "80202"],
    ]
    _write_csv(pos_iqies_path, pos_iqies_header, pos_iqies_rows)

    build_combined_registry(
        nppes_path=nppes_path,
        othername_path=other_path,
        pos_hospital_path=pos_hosp_path,
        pos_iqies_path=pos_iqies_path,
        output_path=out_path,
    )

    rows = list(csv.DictReader(out_path.open()))
    # Expect 3 rows: 1 NPPES org + 2 POS
    assert len(rows) == 3

    nppes_row = next(r for r in rows if r["source"] == "nppes")
    assert nppes_row["canonical_id"] == "NPI:1234567890"
    assert nppes_row["canonical_name"] == "Alpha Hospital"
    aliases = json.loads(nppes_row["aliases"]) if nppes_row["aliases"] else []
    assert "Alpha Hosp" in aliases
    assert "Alpha Health System" in aliases

    pos_hosp_row = next(r for r in rows if r["source"] == "pos_hospital")
    assert pos_hosp_row["ccn"] == "010001"
    assert pos_hosp_row["canonical_name"] == "Beta Medical Center"
    assert pos_hosp_row["facility_type"] == "acute"

    pos_iqies_row = next(r for r in rows if r["source"] == "pos_iqies")
    assert pos_iqies_row["ccn"] == "330001"
    assert pos_iqies_row["canonical_name"] == "Gamma Hospice"
