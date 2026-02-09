"""Tests for facility registry CSV loader."""

from __future__ import annotations

import csv
from pathlib import Path

from asre.facility.registry_loader import load_facility_registry_csv


def _write_registry_csv(path: Path) -> None:
    rows = [
        {
            "canonical_id": "NPI:1111111111",
            "canonical_name": "Test Hospital",
            "npi": "1111111111",
            "ccn": "",
            "facility_type": "acute",
            "facility_type_raw": "",
            "aliases": '["TEST HOSP", "TEST HOSPITAL"]',
            "source": "nppes",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "state": "",
            "zip": "",
            "taxonomy_codes": "[]",
            "pos_category_code": "",
            "pos_subtype_code": "",
            "pos_provider_type_id": "",
            "pos_general_facility_type_code": "",
        },
        {
            "canonical_id": "CCN:999999",
            "canonical_name": "CCN Facility",
            "npi": "",
            "ccn": "999999",
            "facility_type": "snf",
            "facility_type_raw": "",
            "aliases": "",
            "source": "pos_hospital",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "state": "",
            "zip": "",
            "taxonomy_codes": "[]",
            "pos_category_code": "",
            "pos_subtype_code": "",
            "pos_provider_type_id": "",
            "pos_general_facility_type_code": "",
        },
    ]

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_load_facility_registry_csv_parses_aliases(tmp_path: Path) -> None:
    csv_path = tmp_path / "facility_registry.csv"
    _write_registry_csv(csv_path)

    config = load_facility_registry_csv(csv_path)

    assert len(config.facilities) == 2
    first = config.facilities[0]
    assert first.canonical_id == "NPI:1111111111"
    assert first.npi == "1111111111"
    assert first.facility_type == "acute"
    assert "TEST HOSP" in first.aliases


def test_load_facility_registry_respects_use_npi_registry(tmp_path: Path) -> None:
    csv_path = tmp_path / "facility_registry.csv"
    _write_registry_csv(csv_path)

    config = load_facility_registry_csv(csv_path, use_npi_registry=False)

    assert all(not fac.canonical_id.startswith("NPI:") for fac in config.facilities)
