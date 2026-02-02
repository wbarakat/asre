"""Tests for NPI/CCN facility matching (US-037)."""

from __future__ import annotations

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.matcher import FacilityMatcher, MatchResult
from asre.facility.normalizer import FacilityNormalizer


def _make_alias_config() -> FacilityAliasConfig:
    """Create a test FacilityAliasConfig with NPI and CCN values."""
    return FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="St. Mary's Medical Center",
                npi="1234567890",
                ccn="010001",
                facility_type="acute",
                aliases=["ST MARYS MEDICAL CTR"],
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
                canonical_name="Good Samaritan Hospital",
                npi="3456789012",
                facility_type="acute",
                aliases=["GOOD SAMARITAN HOSP"],
            ),
            FacilityAlias(
                canonical_id="FAC_004",
                canonical_name="Valley View SNF",
                ccn="020001",
                facility_type="snf",
                aliases=[],
            ),
        ]
    )


class TestNPIMatching:
    """Test matching facilities by NPI identifier."""

    def test_npi_match_returns_canonical_id(self) -> None:
        """Record with NPI '1234567890' matches FAC_001."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("1234567890")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_npi_match_second_facility(self) -> None:
        """NPI '2345678901' matches FAC_002."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("2345678901")
        assert result is not None
        assert result.canonical_id == "FAC_002"

    def test_npi_match_third_facility(self) -> None:
        """NPI '3456789012' matches FAC_003."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("3456789012")
        assert result is not None
        assert result.canonical_id == "FAC_003"

    def test_npi_no_match_returns_none(self) -> None:
        """Unknown NPI returns None."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("9999999999")
        assert result is None

    def test_npi_none_returns_none(self) -> None:
        """None NPI returns None."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi(None)
        assert result is None

    def test_npi_empty_string_returns_none(self) -> None:
        """Empty string NPI returns None."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("")
        assert result is None

    def test_npi_match_type_is_npi(self) -> None:
        """NPI match result should have match_type='npi'."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("1234567890")
        assert result is not None
        assert result.match_type == "npi"

    def test_npi_match_score_is_one(self) -> None:
        """NPI match is a direct identifier match, score should be 1.0."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("1234567890")
        assert result is not None
        assert result.score == 1.0

    def test_npi_whitespace_stripped(self) -> None:
        """NPI with leading/trailing whitespace should still match."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_npi("  1234567890  ")
        assert result is not None
        assert result.canonical_id == "FAC_001"


class TestCCNMatching:
    """Test matching facilities by CCN identifier."""

    def test_ccn_match_returns_canonical_id(self) -> None:
        """CCN '010001' matches FAC_001."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("010001")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_ccn_match_second_facility(self) -> None:
        """CCN '010002' matches FAC_002."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("010002")
        assert result is not None
        assert result.canonical_id == "FAC_002"

    def test_ccn_match_facility_without_npi(self) -> None:
        """FAC_004 has CCN but no NPI — CCN match should still work."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("020001")
        assert result is not None
        assert result.canonical_id == "FAC_004"

    def test_ccn_no_match_returns_none(self) -> None:
        """Unknown CCN returns None."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("999999")
        assert result is None

    def test_ccn_none_returns_none(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn(None)
        assert result is None

    def test_ccn_empty_string_returns_none(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("")
        assert result is None

    def test_ccn_match_type_is_ccn(self) -> None:
        """CCN match result should have match_type='ccn'."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("010001")
        assert result is not None
        assert result.match_type == "ccn"

    def test_ccn_match_score_is_one(self) -> None:
        """CCN match is direct identifier, score=1.0."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("010001")
        assert result is not None
        assert result.score == 1.0

    def test_ccn_whitespace_stripped(self) -> None:
        """CCN with whitespace should still match."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_ccn("  010001  ")
        assert result is not None
        assert result.canonical_id == "FAC_001"


class TestMatchPrecedence:
    """Test that NPI/CCN does not override exact alias match but takes precedence over fuzzy."""

    def test_exact_alias_takes_precedence_over_npi(self) -> None:
        """Exact alias match should be tried first; NPI/CCN is secondary."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        # "ST MARYS MEDICAL CTR" is exact alias for FAC_001
        # Try exact first — should get match_type='exact'
        exact_result = matcher.match_exact("ST MARYS MEDICAL CTR")
        assert exact_result is not None
        assert exact_result.match_type == "exact"

        # NPI for same facility gives match_type='npi'
        npi_result = matcher.match_npi("1234567890")
        assert npi_result is not None
        assert npi_result.match_type == "npi"

    def test_npi_index_only_includes_facilities_with_npi(self) -> None:
        """FAC_004 has no NPI — should not appear in NPI index."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        # FAC_004 (Valley View SNF) has ccn but no npi
        # NPI match should not find it
        # (No NPI to try — this just confirms no false positives)
        result = matcher.match_npi("020001")  # This is a CCN, not NPI
        assert result is None

    def test_ccn_index_only_includes_facilities_with_ccn(self) -> None:
        """FAC_003 has NPI but no CCN — should not appear in CCN index."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        # FAC_003 has npi=3456789012 but no ccn
        result = matcher.match_ccn("3456789012")  # This is an NPI, not CCN
        assert result is None
