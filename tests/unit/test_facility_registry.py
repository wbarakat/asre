"""Unit tests for FacilityRegistry (US-040)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.normalizer import FacilityNormalizer
from asre.facility.registry import FacilityRecord, FacilityRegistry


def _make_alias_config() -> FacilityAliasConfig:
    """Create a sample FacilityAliasConfig for testing."""
    return FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="St. Mary's Medical Center",
                npi="1234567890",
                ccn="010001",
                facility_type="acute",
                aliases=["ST MARYS MEDICAL CTR", "ST MARY MED CTR"],
            ),
            FacilityAlias(
                canonical_id="FAC_002",
                canonical_name="Memorial Regional Hospital",
                npi="2345678901",
                ccn="010002",
                facility_type="acute",
                aliases=["MEMORIAL REGIONAL HOSP"],
            ),
            FacilityAlias(
                canonical_id="FAC_003",
                canonical_name="Sunrise Skilled Nursing Facility",
                facility_type="snf",
                aliases=["SUNRISE SNF"],
            ),
        ]
    )


def _make_registry() -> FacilityRegistry:
    """Create a FacilityRegistry loaded from sample config."""
    normalizer = FacilityNormalizer()
    alias_config = _make_alias_config()
    return FacilityRegistry(alias_config=alias_config, normalizer=normalizer)


class TestFacilityRegistryConstruction:
    """Tests for registry construction and loading."""

    def test_loads_facilities_from_alias_config(self) -> None:
        registry = _make_registry()
        # Should have 3 facilities loaded
        assert len(registry.get_all_facilities()) == 3

    def test_empty_alias_config_creates_empty_registry(self) -> None:
        normalizer = FacilityNormalizer()
        config = FacilityAliasConfig(facilities=[])
        registry = FacilityRegistry(alias_config=config, normalizer=normalizer)
        assert len(registry.get_all_facilities()) == 0

    def test_facility_record_has_all_fields(self) -> None:
        registry = _make_registry()
        record = registry.get_facility("FAC_001")
        assert record is not None
        assert record.canonical_id == "FAC_001"
        assert record.canonical_name == "St. Mary's Medical Center"
        assert record.npi == "1234567890"
        assert record.ccn == "010001"
        assert record.facility_type == "acute"
        assert len(record.aliases) >= 2  # At least the configured aliases

    def test_facility_record_tracks_facility_type(self) -> None:
        registry = _make_registry()
        fac_001 = registry.get_facility("FAC_001")
        fac_003 = registry.get_facility("FAC_003")
        assert fac_001 is not None
        assert fac_001.facility_type == "acute"
        assert fac_003 is not None
        assert fac_003.facility_type == "snf"


class TestLookupByAlias:
    """Tests for looking up facilities by alias string."""

    def test_lookup_by_normalized_alias(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_alias("ST MARYS MEDICAL CTR")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_lookup_by_canonical_name(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_alias("St. Mary's Medical Center")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_lookup_normalizes_input(self) -> None:
        registry = _make_registry()
        # Input with different casing/punctuation should still match
        result = registry.lookup_by_alias("st marys medical ctr")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_lookup_no_match_returns_none(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_alias("COMPLETELY UNKNOWN FACILITY")
        assert result is None

    def test_lookup_empty_input_returns_none(self) -> None:
        registry = _make_registry()
        assert registry.lookup_by_alias("") is None
        assert registry.lookup_by_alias(None) is None


class TestLookupByNPI:
    """Tests for looking up facilities by NPI."""

    def test_lookup_by_npi(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_npi("1234567890")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_lookup_by_npi_different_facility(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_npi("2345678901")
        assert result is not None
        assert result.canonical_id == "FAC_002"

    def test_lookup_npi_no_match(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_npi("9999999999")
        assert result is None

    def test_lookup_npi_none(self) -> None:
        registry = _make_registry()
        assert registry.lookup_by_npi(None) is None

    def test_lookup_npi_whitespace_stripped(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_npi("  1234567890  ")
        assert result is not None
        assert result.canonical_id == "FAC_001"


class TestLookupByCCN:
    """Tests for looking up facilities by CCN."""

    def test_lookup_by_ccn(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_ccn("010001")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_lookup_ccn_no_match(self) -> None:
        registry = _make_registry()
        result = registry.lookup_by_ccn("999999")
        assert result is None

    def test_lookup_ccn_none(self) -> None:
        registry = _make_registry()
        assert registry.lookup_by_ccn(None) is None


class TestAddNewFacility:
    """Tests for adding new facilities at runtime."""

    def test_add_new_facility(self) -> None:
        registry = _make_registry()
        initial_count = len(registry.get_all_facilities())
        registry.add_facility(
            canonical_id="FAC_NEW",
            canonical_name="New Test Hospital",
            facility_type="acute",
        )
        assert len(registry.get_all_facilities()) == initial_count + 1

    def test_added_facility_retrievable_by_id(self) -> None:
        registry = _make_registry()
        registry.add_facility(
            canonical_id="FAC_NEW",
            canonical_name="New Test Hospital",
            facility_type="acute",
            npi="9876543210",
            ccn="099999",
        )
        record = registry.get_facility("FAC_NEW")
        assert record is not None
        assert record.canonical_name == "New Test Hospital"
        assert record.facility_type == "acute"
        assert record.npi == "9876543210"
        assert record.ccn == "099999"

    def test_added_facility_searchable_by_alias(self) -> None:
        registry = _make_registry()
        registry.add_facility(
            canonical_id="FAC_NEW",
            canonical_name="New Test Hospital",
        )
        result = registry.lookup_by_alias("New Test Hospital")
        assert result is not None
        assert result.canonical_id == "FAC_NEW"

    def test_added_facility_searchable_by_npi(self) -> None:
        registry = _make_registry()
        registry.add_facility(
            canonical_id="FAC_NEW",
            canonical_name="New Test Hospital",
            npi="9876543210",
        )
        result = registry.lookup_by_npi("9876543210")
        assert result is not None
        assert result.canonical_id == "FAC_NEW"

    def test_add_alias_to_existing_facility(self) -> None:
        registry = _make_registry()
        registry.add_alias("FAC_001", "SAINT MARY EAST")
        result = registry.lookup_by_alias("SAINT MARY EAST")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_add_alias_to_nonexistent_facility_raises(self) -> None:
        registry = _make_registry()
        try:
            registry.add_alias("FAC_NONEXISTENT", "SOME ALIAS")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_added_facility_with_flags(self) -> None:
        registry = _make_registry()
        registry.add_facility(
            canonical_id="FAC_NEW",
            canonical_name="Unknown Place",
            flags=["FACILITY_NEW_UNREVIEWED"],
        )
        record = registry.get_facility("FAC_NEW")
        assert record is not None
        assert "FACILITY_NEW_UNREVIEWED" in record.flags


class TestPersistence:
    """Tests for persisting registry to database."""

    def test_to_records_returns_list_of_dicts(self) -> None:
        registry = _make_registry()
        records = registry.to_records()
        assert isinstance(records, list)
        assert len(records) == 3
        for rec in records:
            assert "canonical_id" in rec
            assert "canonical_name" in rec
            assert "facility_type" in rec
            assert "aliases" in rec

    def test_to_records_includes_all_fields(self) -> None:
        registry = _make_registry()
        records = registry.to_records()
        fac_001 = next(r for r in records if r["canonical_id"] == "FAC_001")
        assert fac_001["canonical_name"] == "St. Mary's Medical Center"
        assert fac_001["npi"] == "1234567890"
        assert fac_001["ccn"] == "010001"
        assert fac_001["facility_type"] == "acute"
        assert isinstance(fac_001["aliases"], list)
        assert isinstance(fac_001["flags"], list)

    def test_persist_calls_adapter_write_records(self) -> None:
        registry = _make_registry()
        mock_adapter = MagicMock()
        mock_adapter.write_records.return_value = 3
        count = registry.persist(mock_adapter)
        mock_adapter.write_records.assert_called_once()
        call_args = mock_adapter.write_records.call_args
        assert call_args[0][0] == "asre_facility_registry"
        assert len(call_args[0][1]) == 3
        assert count == 3

    def test_persist_with_empty_registry(self) -> None:
        normalizer = FacilityNormalizer()
        config = FacilityAliasConfig(facilities=[])
        registry = FacilityRegistry(alias_config=config, normalizer=normalizer)
        mock_adapter = MagicMock()
        mock_adapter.write_records.return_value = 0
        count = registry.persist(mock_adapter)
        assert count == 0


class TestFacilityRecord:
    """Tests for the FacilityRecord dataclass."""

    def test_facility_record_construction(self) -> None:
        record = FacilityRecord(
            canonical_id="FAC_TEST",
            canonical_name="Test Hospital",
            facility_type="acute",
        )
        assert record.canonical_id == "FAC_TEST"
        assert record.canonical_name == "Test Hospital"
        assert record.facility_type == "acute"
        assert record.npi is None
        assert record.ccn is None
        assert record.aliases == []
        assert record.flags == []

    def test_facility_record_to_dict(self) -> None:
        record = FacilityRecord(
            canonical_id="FAC_TEST",
            canonical_name="Test Hospital",
            facility_type="acute",
            npi="1111111111",
            ccn="020002",
            aliases=["TEST HOSP"],
            flags=["FACILITY_NEW_UNREVIEWED"],
        )
        d = record.to_dict()
        assert d["canonical_id"] == "FAC_TEST"
        assert d["canonical_name"] == "Test Hospital"
        assert d["npi"] == "1111111111"
        assert d["ccn"] == "020002"
        assert d["facility_type"] == "acute"
        assert d["aliases"] == ["TEST HOSP"]
        assert d["flags"] == ["FACILITY_NEW_UNREVIEWED"]
