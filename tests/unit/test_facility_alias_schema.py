"""Tests for facility alias config Pydantic schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig


class TestFacilityAlias:
    """Tests for the FacilityAlias model."""

    def test_valid_facility_alias_all_fields(self) -> None:
        alias = FacilityAlias(
            canonical_id="FAC_001",
            canonical_name="St. Mary's Medical Center",
            npi="1234567890",
            ccn="050001",
            aliases=["ST MARYS MED CTR", "SAINT MARYS HOSPITAL"],
        )
        assert alias.canonical_id == "FAC_001"
        assert alias.canonical_name == "St. Mary's Medical Center"
        assert alias.npi == "1234567890"
        assert alias.ccn == "050001"
        assert alias.aliases == ["ST MARYS MED CTR", "SAINT MARYS HOSPITAL"]

    def test_valid_facility_alias_required_only(self) -> None:
        alias = FacilityAlias(
            canonical_id="FAC_002",
            canonical_name="Memorial Regional Hospital",
        )
        assert alias.canonical_id == "FAC_002"
        assert alias.canonical_name == "Memorial Regional Hospital"
        assert alias.npi is None
        assert alias.ccn is None
        assert alias.aliases == []

    def test_missing_canonical_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            FacilityAlias(canonical_name="Test Hospital")  # type: ignore[call-arg]

    def test_missing_canonical_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            FacilityAlias(canonical_id="FAC_001")  # type: ignore[call-arg]

    def test_aliases_defaults_to_empty_list(self) -> None:
        alias = FacilityAlias(
            canonical_id="FAC_003",
            canonical_name="Test Clinic",
        )
        assert alias.aliases == []

    def test_facility_type_field(self) -> None:
        alias = FacilityAlias(
            canonical_id="FAC_004",
            canonical_name="Long Term Care",
            facility_type="ltach",
        )
        assert alias.facility_type == "ltach"

    def test_facility_type_defaults_to_none(self) -> None:
        alias = FacilityAlias(
            canonical_id="FAC_005",
            canonical_name="Unknown Type Facility",
        )
        assert alias.facility_type is None


class TestFacilityAliasConfig:
    """Tests for the FacilityAliasConfig model."""

    def test_valid_config_with_facilities(self) -> None:
        config = FacilityAliasConfig(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_001",
                    canonical_name="St. Mary's Medical Center",
                    npi="1234567890",
                    aliases=["ST MARYS MED CTR"],
                ),
                FacilityAlias(
                    canonical_id="FAC_002",
                    canonical_name="Memorial Regional Hospital",
                    ccn="050002",
                    aliases=["MEMORIAL REGIONAL", "MRH"],
                ),
            ]
        )
        assert len(config.facilities) == 2
        assert config.facilities[0].canonical_id == "FAC_001"
        assert config.facilities[1].canonical_id == "FAC_002"

    def test_empty_facilities_list(self) -> None:
        config = FacilityAliasConfig(facilities=[])
        assert config.facilities == []

    def test_facilities_defaults_to_empty_list(self) -> None:
        config = FacilityAliasConfig()
        assert config.facilities == []

    def test_invalid_facility_in_list_raises(self) -> None:
        with pytest.raises(ValidationError):
            FacilityAliasConfig(
                facilities=[
                    {"canonical_id": "FAC_001"}  # type: ignore[list-item]  # missing canonical_name
                ]
            )

    def test_config_with_all_facility_fields(self) -> None:
        config = FacilityAliasConfig(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_001",
                    canonical_name="Good Samaritan Hospital",
                    npi="9876543210",
                    ccn="060001",
                    facility_type="acute",
                    aliases=[
                        "GOOD SAM",
                        "GOOD SAMARITAN HOSP",
                        "GOOD SAMARITAN HOSPITAL WEST",
                    ],
                ),
            ]
        )
        fac = config.facilities[0]
        assert fac.npi == "9876543210"
        assert fac.ccn == "060001"
        assert fac.facility_type == "acute"
        assert len(fac.aliases) == 3
