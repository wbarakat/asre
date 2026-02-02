"""Facility registry storing canonical facilities with aliases, NPI, CCN, and type.

Loads initial data from facility_aliases.yaml. Provides in-memory indexes
keyed by normalized alias strings, NPI, and CCN. Supports adding new
facilities and aliases at runtime, and persisting to database table
(asre_facility_registry).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from asre.config.facility_alias_schema import FacilityAliasConfig
from asre.facility.normalizer import FacilityNormalizer


@dataclass
class FacilityRecord:
    """A canonical facility record in the registry."""

    canonical_id: str
    canonical_name: str
    facility_type: str | None = None
    npi: str | None = None
    ccn: str | None = None
    aliases: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for persistence."""
        return {
            "canonical_id": self.canonical_id,
            "canonical_name": self.canonical_name,
            "npi": self.npi,
            "ccn": self.ccn,
            "facility_type": self.facility_type,
            "aliases": self.aliases,
            "flags": self.flags,
        }


class FacilityRegistry:
    """In-memory registry of canonical facilities.

    Loads initial data from FacilityAliasConfig. Maintains indexes
    for lookup by normalized alias, NPI, and CCN. Supports runtime
    additions and database persistence.
    """

    def __init__(
        self,
        alias_config: FacilityAliasConfig,
        normalizer: FacilityNormalizer,
    ) -> None:
        self._normalizer = normalizer
        # Primary store: canonical_id -> FacilityRecord
        self._facilities: dict[str, FacilityRecord] = {}
        # Lookup indexes
        self._alias_index: dict[str, str] = {}
        self._npi_index: dict[str, str] = {}
        self._ccn_index: dict[str, str] = {}

        for facility in alias_config.facilities:
            record = FacilityRecord(
                canonical_id=facility.canonical_id,
                canonical_name=facility.canonical_name,
                facility_type=facility.facility_type,
                npi=facility.npi,
                ccn=facility.ccn,
                aliases=list(facility.aliases),
            )
            self._register(record)

    def _register(self, record: FacilityRecord) -> None:
        """Add a facility record to all indexes."""
        self._facilities[record.canonical_id] = record

        # Index canonical_name (normalized)
        normalized_name = self._normalizer.normalize(record.canonical_name)
        if normalized_name:
            self._alias_index[normalized_name] = record.canonical_id

        # Index each alias (normalized)
        for alias in record.aliases:
            normalized_alias = self._normalizer.normalize(alias)
            if normalized_alias:
                self._alias_index[normalized_alias] = record.canonical_id

        # Index NPI
        if record.npi:
            self._npi_index[record.npi.strip()] = record.canonical_id

        # Index CCN
        if record.ccn:
            self._ccn_index[record.ccn.strip()] = record.canonical_id

    def get_facility(self, canonical_id: str) -> FacilityRecord | None:
        """Get a facility record by canonical_id."""
        return self._facilities.get(canonical_id)

    def get_all_facilities(self) -> list[FacilityRecord]:
        """Get all facility records."""
        return list(self._facilities.values())

    def lookup_by_alias(self, name: str | None) -> FacilityRecord | None:
        """Look up a facility by normalized alias string.

        Args:
            name: Raw facility name to look up.

        Returns:
            FacilityRecord if found, None otherwise.
        """
        if not name:
            return None
        normalized = self._normalizer.normalize(name)
        if not normalized:
            return None
        canonical_id = self._alias_index.get(normalized)
        if canonical_id is not None:
            return self._facilities.get(canonical_id)
        return None

    def lookup_by_npi(self, npi: str | None) -> FacilityRecord | None:
        """Look up a facility by NPI.

        Args:
            npi: NPI string.

        Returns:
            FacilityRecord if found, None otherwise.
        """
        if not npi or not npi.strip():
            return None
        canonical_id = self._npi_index.get(npi.strip())
        if canonical_id is not None:
            return self._facilities.get(canonical_id)
        return None

    def lookup_by_ccn(self, ccn: str | None) -> FacilityRecord | None:
        """Look up a facility by CCN.

        Args:
            ccn: CCN string.

        Returns:
            FacilityRecord if found, None otherwise.
        """
        if not ccn or not ccn.strip():
            return None
        canonical_id = self._ccn_index.get(ccn.strip())
        if canonical_id is not None:
            return self._facilities.get(canonical_id)
        return None

    def add_facility(
        self,
        canonical_id: str,
        canonical_name: str,
        facility_type: str | None = None,
        npi: str | None = None,
        ccn: str | None = None,
        aliases: list[str] | None = None,
        flags: list[str] | None = None,
    ) -> FacilityRecord:
        """Add a new facility to the registry at runtime.

        Args:
            canonical_id: Unique facility identifier.
            canonical_name: Human-readable facility name.
            facility_type: Facility type (acute, snf, rehab, etc.).
            npi: Optional NPI identifier.
            ccn: Optional CCN identifier.
            aliases: Optional list of alias strings.
            flags: Optional list of flags (e.g., FACILITY_NEW_UNREVIEWED).

        Returns:
            The created FacilityRecord.
        """
        record = FacilityRecord(
            canonical_id=canonical_id,
            canonical_name=canonical_name,
            facility_type=facility_type,
            npi=npi,
            ccn=ccn,
            aliases=aliases or [],
            flags=flags or [],
        )
        self._register(record)
        return record

    def add_alias(self, canonical_id: str, alias: str) -> None:
        """Add an alias to an existing facility.

        Args:
            canonical_id: The facility to add the alias to.
            alias: The alias string to add.

        Raises:
            ValueError: If canonical_id not found in registry.
        """
        record = self._facilities.get(canonical_id)
        if record is None:
            raise ValueError(f"Facility {canonical_id} not found in registry")
        record.aliases.append(alias)
        normalized = self._normalizer.normalize(alias)
        if normalized:
            self._alias_index[normalized] = canonical_id

    def to_records(self) -> list[dict[str, Any]]:
        """Serialize all facilities to list of dicts for persistence.

        Returns:
            List of facility dicts suitable for write_records().
        """
        return [record.to_dict() for record in self._facilities.values()]

    def persist(self, adapter: Any) -> int:
        """Persist registry to database via adapter.

        Args:
            adapter: IngestAdapter instance for database access.

        Returns:
            Number of records written.
        """
        records = self.to_records()
        if not records:
            return 0
        # Serialize list fields to JSON strings for database storage
        db_records: list[dict[str, Any]] = []
        for rec in records:
            db_rec = dict(rec)
            db_rec["aliases"] = json.dumps(rec["aliases"])
            db_rec["flags"] = json.dumps(rec["flags"])
            db_records.append(db_rec)
        count: int = adapter.write_records("asre_facility_registry", db_records)
        return count
