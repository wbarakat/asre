"""Build a combined facility registry from NPPES and CMS POS sources."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


OUTPUT_COLUMNS: list[str] = [
    "canonical_id",
    "canonical_name",
    "npi",
    "ccn",
    "facility_type",
    "facility_type_raw",
    "aliases",
    "source",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "zip",
    "taxonomy_codes",
    "pos_category_code",
    "pos_subtype_code",
    "pos_provider_type_id",
    "pos_general_facility_type_code",
]


def build_combined_registry(
    *,
    nppes_path: Path,
    othername_path: Path | None,
    pos_hospital_path: Path | None,
    pos_iqies_path: Path | None,
    output_path: Path,
    limit: int | None = None,
) -> None:
    """Write a combined facility registry CSV.

    Emits organization NPIs from NPPES and CCNs from POS files into a
    single registry. Does not attempt to crosswalk NPI<->CCN.
    """
    othernames = _load_othernames(othername_path) if othername_path else {}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for row in iter_nppes_orgs(nppes_path, othernames=othernames, limit=limit):
            writer.writerow(row)

        if pos_hospital_path is not None:
            for row in iter_pos_hospital(pos_hospital_path, limit=limit):
                writer.writerow(row)

        if pos_iqies_path is not None:
            for row in iter_pos_iqies(pos_iqies_path, limit=limit):
                writer.writerow(row)


def _load_othernames(path: Path) -> dict[str, set[str]]:
    """Load NPPES other organization names by NPI."""
    aliases: dict[str, set[str]] = {}
    if path is None or not path.exists():
        return aliases
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            npi = (row.get("NPI") or "").strip()
            name = (row.get("Provider Other Organization Name") or "").strip()
            if not npi or not name:
                continue
            aliases.setdefault(npi, set()).add(name)
    return aliases


def iter_nppes_orgs(
    nppes_path: Path,
    *,
    othernames: dict[str, set[str]] | None = None,
    limit: int | None = None,
) -> Iterable[dict[str, str]]:
    """Iterate organization NPIs from the NPPES file as registry rows."""
    othernames = othernames or {}
    with nppes_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            entity = (row.get("Entity Type Code") or "").strip()
            if entity != "2":
                continue

            npi = (row.get("NPI") or "").strip()
            if not npi:
                continue

            name = (row.get("Provider Organization Name (Legal Business Name)") or "").strip()
            if not name:
                name = (row.get("Provider Other Organization Name") or "").strip()
            if not name:
                continue

            aliases: set[str] = set()
            other_name = (row.get("Provider Other Organization Name") or "").strip()
            if other_name and other_name != name:
                aliases.add(other_name)
            aliases.update(othernames.get(npi, set()))

            taxonomy_codes = _extract_taxonomy_codes(row)

            yield _make_row(
                canonical_id=f"NPI:{npi}",
                canonical_name=name,
                npi=npi,
                ccn="",
                facility_type="",
                facility_type_raw="",
                aliases=aliases,
                source="nppes",
                address_line1=(row.get("Provider First Line Business Practice Location Address") or "").strip(),
                address_line2=(row.get("Provider Second Line Business Practice Location Address") or "").strip(),
                city=(row.get("Provider Business Practice Location Address City Name") or "").strip(),
                state=(row.get("Provider Business Practice Location Address State Name") or "").strip(),
                zip_code=(row.get("Provider Business Practice Location Address Postal Code") or "").strip(),
                taxonomy_codes=taxonomy_codes,
                pos_category_code="",
                pos_subtype_code="",
                pos_provider_type_id="",
                pos_general_facility_type_code="",
            )

            count += 1
            if limit is not None and count >= limit:
                break


def iter_pos_hospital(
    path: Path,
    *,
    limit: int | None = None,
) -> Iterable[dict[str, str]]:
    """Iterate hospital POS rows as registry rows."""
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            ccn = (row.get("PRVDR_NUM") or "").strip()
            name = (row.get("FAC_NAME") or "").strip()
            if not ccn or not name:
                continue

            category = (row.get("PRVDR_CTGRY_CD") or "").strip()
            subtype = (row.get("PRVDR_CTGRY_SBTYP_CD") or "").strip()
            general_type = (row.get("GNRL_FAC_TYPE_CD") or "").strip()
            facility_type = _map_pos_hospital_type(category, subtype)

            aliases: set[str] = set()
            alt_name = (row.get("MLT_FAC_ORG_NAME") or "").strip()
            if alt_name and alt_name != name:
                aliases.add(alt_name)

            yield _make_row(
                canonical_id=f"CCN:{ccn}",
                canonical_name=name,
                npi="",
                ccn=ccn,
                facility_type=facility_type,
                facility_type_raw=f"{category}:{subtype}" if category or subtype else "",
                aliases=aliases,
                source="pos_hospital",
                address_line1=(row.get("ST_ADR") or "").strip(),
                address_line2="",
                city=(row.get("CITY_NAME") or "").strip(),
                state=(row.get("STATE_CD") or "").strip(),
                zip_code=(row.get("ZIP_CD") or "").strip(),
                taxonomy_codes=[],
                pos_category_code=category,
                pos_subtype_code=subtype,
                pos_provider_type_id="",
                pos_general_facility_type_code=general_type,
            )

            count += 1
            if limit is not None and count >= limit:
                break


def iter_pos_iqies(
    path: Path,
    *,
    limit: int | None = None,
) -> Iterable[dict[str, str]]:
    """Iterate iQIES POS rows as registry rows."""
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            ccn = (row.get("prvdr_num") or "").strip()
            name = (row.get("fac_name") or "").strip()
            if not ccn or not name:
                continue

            provider_type = (row.get("prvdr_type_id") or "").strip()
            general_type = (row.get("gnrl_fac_type_cd") or "").strip()

            aliases: set[str] = set()
            alt_name = (row.get("mlt_fac_org_name") or "").strip()
            if alt_name and alt_name != name:
                aliases.add(alt_name)

            yield _make_row(
                canonical_id=f"CCN:{ccn}",
                canonical_name=name,
                npi="",
                ccn=ccn,
                facility_type="",
                facility_type_raw=general_type,
                aliases=aliases,
                source="pos_iqies",
                address_line1=(row.get("st_adr") or "").strip(),
                address_line2="",
                city=(row.get("city_name") or "").strip(),
                state=(row.get("state_cd") or "").strip(),
                zip_code=(row.get("zip_cd") or "").strip(),
                taxonomy_codes=[],
                pos_category_code="",
                pos_subtype_code="",
                pos_provider_type_id=provider_type,
                pos_general_facility_type_code=general_type,
            )

            count += 1
            if limit is not None and count >= limit:
                break


def _extract_taxonomy_codes(row: dict[str, str]) -> list[str]:
    codes: list[str] = []
    for idx in range(1, 16):
        key = f"Healthcare Provider Taxonomy Code_{idx}"
        val = (row.get(key) or "").strip()
        if val:
            codes.append(val)
    return codes


def _map_pos_hospital_type(category: str, subtype: str) -> str:
    """Map POS hospital category/subtype to canonical facility_type.

    Based on CMS POS hospital subtype codes (PRVDR_CTGRY_SBTYP_CD).
    """
    if category != "01":
        return ""
    # Hospital subtypes -> canonical facility_type
    if subtype in {"01", "06", "11", "20", "22", "23"}:
        return "acute"
    if subtype in {"02", "27"}:
        return "ltach"
    if subtype in {"04", "07", "24", "25"}:
        return "psych"
    if subtype in {"05", "26"}:
        return "rehab"
    return ""


def _make_row(
    *,
    canonical_id: str,
    canonical_name: str,
    npi: str,
    ccn: str,
    facility_type: str,
    facility_type_raw: str,
    aliases: set[str],
    source: str,
    address_line1: str,
    address_line2: str,
    city: str,
    state: str,
    zip_code: str,
    taxonomy_codes: list[str],
    pos_category_code: str,
    pos_subtype_code: str,
    pos_provider_type_id: str,
    pos_general_facility_type_code: str,
) -> dict[str, str]:
    return {
        "canonical_id": canonical_id,
        "canonical_name": canonical_name,
        "npi": npi,
        "ccn": ccn,
        "facility_type": facility_type,
        "facility_type_raw": facility_type_raw,
        "aliases": json.dumps(sorted(aliases)) if aliases else "",
        "source": source,
        "address_line1": address_line1,
        "address_line2": address_line2,
        "city": city,
        "state": state,
        "zip": zip_code,
        "taxonomy_codes": json.dumps(taxonomy_codes) if taxonomy_codes else "",
        "pos_category_code": pos_category_code,
        "pos_subtype_code": pos_subtype_code,
        "pos_provider_type_id": pos_provider_type_id,
        "pos_general_facility_type_code": pos_general_facility_type_code,
    }
