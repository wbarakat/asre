"""Tests for FacilityMatcher exact alias matching (US-036)."""

from __future__ import annotations

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.matcher import FacilityMatcher, MatchResult
from asre.facility.normalizer import FacilityNormalizer


def _make_alias_config() -> FacilityAliasConfig:
    """Create a test FacilityAliasConfig with sample facilities."""
    return FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="St. Mary's Medical Center",
                npi="1234567890",
                ccn="010001",
                facility_type="acute",
                aliases=[
                    "ST MARYS MEDICAL CTR",
                    "ST MARY MED CTR",
                    "SAINT MARYS MEDICAL CENTER",
                    "ST MARYS EAST CAMPUS",
                ],
            ),
            FacilityAlias(
                canonical_id="FAC_002",
                canonical_name="Memorial Regional Hospital",
                npi="2345678901",
                ccn="010002",
                facility_type="acute",
                aliases=[
                    "MEMORIAL REGIONAL HOSP",
                    "MEMORIAL REGIONAL",
                    "MRH",
                ],
            ),
            FacilityAlias(
                canonical_id="FAC_003",
                canonical_name="Good Samaritan Hospital",
                npi="3456789012",
                facility_type="acute",
                aliases=[
                    "GOOD SAMARITAN HOSP",
                    "GOOD SAM HOSPITAL",
                ],
            ),
        ]
    )


class TestFacilityMatcherConstruction:
    """Test FacilityMatcher construction and setup."""

    def test_construction_with_alias_config(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)
        assert matcher is not None

    def test_construction_with_empty_config(self) -> None:
        config = FacilityAliasConfig(facilities=[])
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)
        assert matcher is not None


class TestExactAliasMatch:
    """Test exact alias matching against known facility aliases."""

    def test_exact_match_returns_canonical_id(self) -> None:
        """ST MARYS MEDICAL CTR is a known alias for FAC_001."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("ST MARYS MEDICAL CTR")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_exact_match_case_insensitive(self) -> None:
        """Both sides normalized: 'st marys medical ctr' should match."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("st marys medical ctr")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_exact_match_different_alias_same_facility(self) -> None:
        """SAINT MARYS MEDICAL CENTER is another alias for FAC_001."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("SAINT MARYS MEDICAL CENTER")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_exact_match_second_facility(self) -> None:
        """MEMORIAL REGIONAL is an alias for FAC_002."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("MEMORIAL REGIONAL")
        assert result is not None
        assert result.canonical_id == "FAC_002"

    def test_exact_match_third_facility(self) -> None:
        """GOOD SAMARITAN HOSP is an alias for FAC_003."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("GOOD SAMARITAN HOSP")
        assert result is not None
        assert result.canonical_id == "FAC_003"

    def test_no_match_returns_none(self) -> None:
        """Unknown facility name returns None."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("COMPLETELY UNKNOWN HOSPITAL")
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("")
        assert result is None

    def test_none_input_returns_none(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact(None)
        assert result is None

    def test_canonical_name_also_indexed(self) -> None:
        """The canonical_name itself should also be matchable via normalization."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        # "St. Mary's Medical Center" normalizes via FacilityNormalizer
        result = matcher.match_exact("St. Mary's Medical Center")
        assert result is not None
        assert result.canonical_id == "FAC_001"


class TestMatchResult:
    """Test MatchResult contains expected fields."""

    def test_match_result_has_canonical_id(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("MEMORIAL REGIONAL")
        assert result is not None
        assert result.canonical_id == "FAC_002"

    def test_match_result_has_match_type(self) -> None:
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("MEMORIAL REGIONAL")
        assert result is not None
        assert result.match_type == "exact"

    def test_match_result_has_score(self) -> None:
        """Exact match should have score 1.0."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("MEMORIAL REGIONAL")
        assert result is not None
        assert result.score == 1.0


class TestNormalizationBeforeMatch:
    """Test that input strings are normalized before exact matching."""

    def test_input_with_punctuation_matches(self) -> None:
        """'St. Mary's Med Ctr' should normalize and match alias."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        # Normalizer will: uppercase, strip punctuation, expand abbreviations
        result = matcher.match_exact("St. Mary's Med Ctr")
        assert result is not None
        assert result.canonical_id == "FAC_001"

    def test_input_with_extra_whitespace_matches(self) -> None:
        """Extra whitespace should be normalized away."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        result = matcher.match_exact("  MEMORIAL   REGIONAL  ")
        assert result is not None
        assert result.canonical_id == "FAC_002"

    def test_aliases_are_normalized_at_load_time(self) -> None:
        """Aliases from config are normalized so raw input can match."""
        config = _make_alias_config()
        normalizer = FacilityNormalizer()
        matcher = FacilityMatcher(config, normalizer)

        # "MRH" is a short alias for FAC_002 - should match exactly
        result = matcher.match_exact("MRH")
        assert result is not None
        assert result.canonical_id == "FAC_002"
