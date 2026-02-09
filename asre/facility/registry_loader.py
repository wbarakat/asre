"""Load facility registry CSV into FacilityAliasConfig."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig


def load_facility_registry_csv(
    path: Path,
    *,
    use_npi_registry: bool = True,
    use_ccn_registry: bool = True,
) -> FacilityAliasConfig:
    """Load facility registry CSV into FacilityAliasConfig.

    Args:
        path: Path to facility registry CSV.
        use_npi_registry: Whether to include NPI-based rows.
        use_ccn_registry: Whether to include CCN-based rows.

    Returns:
        FacilityAliasConfig containing facilities from the registry.
    """
    if not path.exists():
        raise FileNotFoundError(f"Facility registry not found: {path}")

    facilities: list[FacilityAlias] = []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            canonical_id = (row.get("canonical_id") or "").strip()
            canonical_name = (row.get("canonical_name") or "").strip()
            if not canonical_id or not canonical_name:
                continue

            if canonical_id.startswith("NPI:") and not use_npi_registry:
                continue
            if canonical_id.startswith("CCN:") and not use_ccn_registry:
                continue

            npi = (row.get("npi") or "").strip() or None
            ccn = (row.get("ccn") or "").strip() or None
            facility_type = (row.get("facility_type") or "").strip() or None

            # Compose address from CSV columns
            address_parts = []
            addr1 = (row.get("address_line1") or "").strip()
            addr2 = (row.get("address_line2") or "").strip()
            city = (row.get("city") or "").strip()
            state = (row.get("state") or "").strip()
            zip_code = (row.get("zip") or "").strip()
            if addr1:
                address_parts.append(addr1)
            if addr2:
                address_parts.append(addr2)
            city_state_zip = ", ".join(filter(None, [city, state]))
            if zip_code:
                city_state_zip = f"{city_state_zip} {zip_code}".strip()
            if city_state_zip:
                address_parts.append(city_state_zip)
            address = ", ".join(address_parts) if address_parts else None

            aliases = _parse_aliases(row.get("aliases"))

            facilities.append(
                FacilityAlias(
                    canonical_id=canonical_id,
                    canonical_name=canonical_name,
                    npi=npi,
                    ccn=ccn,
                    facility_type=facility_type,
                    aliases=aliases,
                    address=address,
                )
            )

    return FacilityAliasConfig(facilities=facilities)


def _parse_aliases(raw: Any) -> list[str]:
    """Parse aliases field into a list of strings."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if _valid_alias(item)]

    text = str(raw).strip()
    if not text:
        return []

    # Try JSON list first
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item).strip() for item in data if _valid_alias(item)]
        except json.JSONDecodeError:
            pass

    return [text] if _valid_alias(text) else []


def _valid_alias(value: Any) -> bool:
    text = str(value).strip()
    if not text:
        return False
    return text != "<UNAVAIL>"
