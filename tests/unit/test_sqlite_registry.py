"""Tests for SQLite facility registry lookup and build."""

from __future__ import annotations

import csv
import sqlite3
import tempfile
from pathlib import Path

import pytest

from asre.facility.sqlite_registry import (
    SQLiteRegistryLookup,
    build_sqlite_from_csv,
)


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """Create a small test CSV matching registry_builder output format."""
    csv_path = tmp_path / "registry.csv"
    rows = [
        {
            "canonical_id": "NPI:1234567890",
            "canonical_name": "Test Hospital",
            "npi": "1234567890",
            "ccn": "",
            "facility_type": "acute",
            "aliases": '["TEST HOSP"]',
            "source": "nppes",
            "address_line1": "123 Main St",
            "address_line2": "",
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
        },
        {
            "canonical_id": "CCN:050001",
            "canonical_name": "Memorial Regional Hospital",
            "npi": "",
            "ccn": "050001",
            "facility_type": "acute",
            "aliases": '["MEMORIAL REGIONAL"]',
            "source": "pos_hospital",
            "address_line1": "456 Oak Ave",
            "address_line2": "Suite 200",
            "city": "Los Angeles",
            "state": "CA",
            "zip": "90001",
        },
        {
            "canonical_id": "NPI:9876543210",
            "canonical_name": "Both IDs Facility",
            "npi": "9876543210",
            "ccn": "060002",
            "facility_type": "snf",
            "aliases": "",
            "source": "nppes",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "state": "",
            "zip": "",
        },
    ]
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


@pytest.fixture()
def sample_db(tmp_path: Path, sample_csv: Path) -> Path:
    """Build a SQLite DB from the sample CSV."""
    db_path = tmp_path / "registry.db"
    build_sqlite_from_csv(sample_csv, db_path)
    return db_path


class TestBuildSqliteFromCsv:
    def test_builds_correct_row_count(
        self, tmp_path: Path, sample_csv: Path
    ) -> None:
        db_path = tmp_path / "test.db"
        count = build_sqlite_from_csv(sample_csv, db_path)
        assert count == 3
        assert db_path.exists()

    def test_creates_npi_index(self, sample_db: Path) -> None:
        conn = sqlite3.connect(str(sample_db))
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_npi'"
        ).fetchall()
        conn.close()
        assert len(indexes) == 1

    def test_creates_ccn_index(self, sample_db: Path) -> None:
        conn = sqlite3.connect(str(sample_db))
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ccn'"
        ).fetchall()
        conn.close()
        assert len(indexes) == 1

    def test_composes_address(self, sample_db: Path) -> None:
        conn = sqlite3.connect(str(sample_db))
        row = conn.execute(
            "SELECT address FROM facilities WHERE canonical_id = 'NPI:1234567890'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert "123 Main St" in row[0]
        assert "Springfield" in row[0]

    def test_address_with_line2(self, sample_db: Path) -> None:
        conn = sqlite3.connect(str(sample_db))
        row = conn.execute(
            "SELECT address FROM facilities WHERE canonical_id = 'CCN:050001'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert "Suite 200" in row[0]

    def test_null_address_when_empty(self, sample_db: Path) -> None:
        conn = sqlite3.connect(str(sample_db))
        row = conn.execute(
            "SELECT address FROM facilities WHERE canonical_id = 'NPI:9876543210'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None

    def test_replaces_existing_db(
        self, tmp_path: Path, sample_csv: Path
    ) -> None:
        db_path = tmp_path / "test.db"
        build_sqlite_from_csv(sample_csv, db_path)
        count = build_sqlite_from_csv(sample_csv, db_path)
        assert count == 3

    def test_csv_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_sqlite_from_csv(tmp_path / "nonexistent.csv", tmp_path / "out.db")


class TestSQLiteRegistryLookup:
    def test_lookup_npi_found(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_npi("1234567890")
            assert result is not None
            assert result.canonical_id == "NPI:1234567890"
            assert result.canonical_name == "Test Hospital"
            assert result.npi == "1234567890"
        finally:
            lookup.close()

    def test_lookup_npi_not_found(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_npi("0000000000")
            assert result is None
        finally:
            lookup.close()

    def test_lookup_ccn_found(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_ccn("050001")
            assert result is not None
            assert result.canonical_id == "CCN:050001"
            assert result.canonical_name == "Memorial Regional Hospital"
            assert result.ccn == "050001"
        finally:
            lookup.close()

    def test_lookup_ccn_not_found(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_ccn("999999")
            assert result is None
        finally:
            lookup.close()

    def test_lookup_strips_whitespace(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_npi("  1234567890  ")
            assert result is not None
            assert result.canonical_id == "NPI:1234567890"
        finally:
            lookup.close()

    def test_lookup_npi_none_input(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            assert lookup.lookup_npi(None) is None  # type: ignore[arg-type]
            assert lookup.lookup_npi("") is None
            assert lookup.lookup_npi("   ") is None
        finally:
            lookup.close()

    def test_lookup_ccn_none_input(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            assert lookup.lookup_ccn(None) is None  # type: ignore[arg-type]
            assert lookup.lookup_ccn("") is None
        finally:
            lookup.close()

    def test_close_connection(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        lookup.close()
        # Should not raise

    def test_aliases_parsed(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_npi("1234567890")
            assert result is not None
            assert "TEST HOSP" in result.aliases
        finally:
            lookup.close()

    def test_facility_type_preserved(self, sample_db: Path) -> None:
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            result = lookup.lookup_ccn("050001")
            assert result is not None
            assert result.facility_type == "acute"
        finally:
            lookup.close()


class TestSQLiteMatcherIntegration:
    """Test SQLite lookup integrated with FacilityMatcher."""

    def test_resolve_npi_falls_through_to_sqlite(
        self, sample_db: Path
    ) -> None:
        from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
        from asre.facility.matcher import FacilityMatcher
        from asre.facility.normalizer import FacilityNormalizer

        # Config has no NPI entries
        config = FacilityAliasConfig(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_001",
                    canonical_name="Some Other Hospital",
                )
            ]
        )
        normalizer = FacilityNormalizer()
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            matcher = FacilityMatcher(
                config, normalizer, sqlite_lookup=lookup
            )
            result = matcher.resolve_or_create(
                "Unknown Facility", npi="1234567890"
            )
            assert result is not None
            assert result.canonical_id == "NPI:1234567890"
            assert result.match_type == "npi_registry"
            assert result.score == 1.0
        finally:
            lookup.close()

    def test_resolve_ccn_falls_through_to_sqlite(
        self, sample_db: Path
    ) -> None:
        from asre.config.facility_alias_schema import FacilityAliasConfig
        from asre.facility.matcher import FacilityMatcher
        from asre.facility.normalizer import FacilityNormalizer

        config = FacilityAliasConfig(facilities=[])
        normalizer = FacilityNormalizer()
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            matcher = FacilityMatcher(
                config, normalizer, sqlite_lookup=lookup
            )
            result = matcher.resolve_or_create(
                "Unknown Facility", ccn="050001"
            )
            assert result is not None
            assert result.canonical_id == "CCN:050001"
            assert result.match_type == "ccn_registry"
            assert result.score == 1.0
        finally:
            lookup.close()

    def test_sqlite_hit_caches_in_memory(self, sample_db: Path) -> None:
        from asre.config.facility_alias_schema import FacilityAliasConfig
        from asre.facility.matcher import FacilityMatcher
        from asre.facility.normalizer import FacilityNormalizer
        from unittest.mock import patch

        config = FacilityAliasConfig(facilities=[])
        normalizer = FacilityNormalizer()
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            matcher = FacilityMatcher(
                config, normalizer, sqlite_lookup=lookup
            )
            # First call: goes to SQLite
            result1 = matcher.resolve_or_create(
                "Unknown", npi="1234567890"
            )
            assert result1 is not None
            assert result1.match_type == "npi_registry"

            # Second call: should hit in-memory NPI index (match_type="npi")
            result2 = matcher.resolve_or_create(
                "Unknown", npi="1234567890"
            )
            assert result2 is not None
            assert result2.match_type == "npi"  # cached in-memory
        finally:
            lookup.close()

    def test_sqlite_none_when_no_lookup(self) -> None:
        from asre.config.facility_alias_schema import FacilityAliasConfig
        from asre.facility.matcher import FacilityMatcher
        from asre.facility.normalizer import FacilityNormalizer

        config = FacilityAliasConfig(facilities=[])
        normalizer = FacilityNormalizer()
        # No sqlite_lookup passed
        matcher = FacilityMatcher(config, normalizer)
        result = matcher.resolve_or_create(
            "Unknown Facility", npi="1234567890"
        )
        assert result is not None
        assert result.match_type == "new"  # Falls through to create new

    def test_config_npi_takes_priority_over_sqlite(
        self, sample_db: Path
    ) -> None:
        from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
        from asre.facility.matcher import FacilityMatcher
        from asre.facility.normalizer import FacilityNormalizer

        # Config has the same NPI mapped to a different facility
        config = FacilityAliasConfig(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_CONFIG",
                    canonical_name="Config Hospital",
                    npi="1234567890",
                )
            ]
        )
        normalizer = FacilityNormalizer()
        lookup = SQLiteRegistryLookup(sample_db)
        try:
            matcher = FacilityMatcher(
                config, normalizer, sqlite_lookup=lookup
            )
            result = matcher.resolve_or_create(
                "Unknown", npi="1234567890"
            )
            assert result is not None
            # Config NPI (tier 2) should win over SQLite (tier 2b)
            assert result.canonical_id == "FAC_CONFIG"
            assert result.match_type == "npi"
        finally:
            lookup.close()
