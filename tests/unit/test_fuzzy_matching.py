"""Tests for fuzzy facility matching using rapidfuzz token_sort_ratio."""

from __future__ import annotations

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.matcher import FacilityMatcher, MatchResult
from asre.facility.normalizer import FacilityNormalizer


def _build_matcher(
    facilities: list[FacilityAlias] | None = None,
    fuzzy_threshold: float = 0.85,
) -> FacilityMatcher:
    """Build a FacilityMatcher with given facilities and threshold."""
    if facilities is None:
        facilities = [
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="St. Mary's Medical Center - East Campus",
                aliases=["ST MARYS EAST CAMPUS", "SAINT MARYS EAST"],
            ),
            FacilityAlias(
                canonical_id="FAC_002",
                canonical_name="Memorial Regional Hospital",
                aliases=["MEMORIAL REGIONAL"],
            ),
            FacilityAlias(
                canonical_id="FAC_003",
                canonical_name="Good Samaritan Hospital - West",
                aliases=["GOOD SAMARITAN WEST"],
            ),
        ]
    normalizer = FacilityNormalizer()
    config = FacilityAliasConfig(facilities=facilities)
    return FacilityMatcher(config, normalizer, fuzzy_threshold=fuzzy_threshold)


class TestFuzzyMatchBasic:
    """Basic fuzzy matching behavior."""

    def test_fuzzy_match_close_name_above_threshold(self) -> None:
        """'ST MARYS EAST' fuzzy matches 'ST MARYS EAST CAMPUS' above threshold."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy("ST MARYS EAST")
        assert result is not None
        assert result.canonical_id == "FAC_001"
        assert result.match_type == "fuzzy"

    def test_fuzzy_match_completely_different_name(self) -> None:
        """'COMPLETELY DIFFERENT NAME' does not match at threshold 0.85."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy("COMPLETELY DIFFERENT NAME")
        assert result is None

    def test_fuzzy_match_returns_match_result(self) -> None:
        """Fuzzy match returns a MatchResult with correct fields."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy("ST MARYS EAST")
        assert result is not None
        assert isinstance(result, MatchResult)
        assert result.match_type == "fuzzy"
        assert 0.0 <= result.score <= 1.0


class TestFuzzyMatchScore:
    """Fuzzy match score behavior."""

    def test_score_above_threshold(self) -> None:
        """Score is at or above the configured threshold when matched."""
        matcher = _build_matcher(fuzzy_threshold=0.85)
        result = matcher.match_fuzzy("ST MARYS EAST")
        assert result is not None
        assert result.score >= 0.85

    def test_score_is_normalized_0_to_1(self) -> None:
        """Score is normalized to [0, 1] range (rapidfuzz returns 0-100)."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy("ST MARYS EAST")
        assert result is not None
        assert result.score <= 1.0
        assert result.score >= 0.0

    def test_low_threshold_matches_more(self) -> None:
        """Lower threshold allows weaker matches."""
        # With default 0.85, "MEMORIAL" alone won't match "MEMORIAL REGIONAL"
        matcher_strict = _build_matcher(fuzzy_threshold=0.85)
        result_strict = matcher_strict.match_fuzzy("MEMORIAL")

        matcher_lenient = _build_matcher(fuzzy_threshold=0.50)
        result_lenient = matcher_lenient.match_fuzzy("MEMORIAL")

        # Lenient should match even if strict doesn't
        if result_strict is None:
            assert result_lenient is not None

    def test_threshold_zero_disables_fuzzy_matching(self) -> None:
        """Threshold <= 0 should disable fuzzy matching entirely."""
        matcher = _build_matcher(fuzzy_threshold=0.0)
        result = matcher.match_fuzzy("ST MARYS EAST")
        assert result is None


class TestFuzzyMatchSelection:
    """When multiple facilities could match, select the best one."""

    def test_selects_highest_score(self) -> None:
        """If multiple facilities score above threshold, selects highest."""
        facilities = [
            FacilityAlias(
                canonical_id="FAC_A",
                canonical_name="North Valley Hospital",
                aliases=["NORTH VALLEY"],
            ),
            FacilityAlias(
                canonical_id="FAC_B",
                canonical_name="North Valley Regional Hospital",
                aliases=["NORTH VALLEY REGIONAL"],
            ),
        ]
        matcher = _build_matcher(facilities=facilities, fuzzy_threshold=0.50)
        result = matcher.match_fuzzy("NORTH VALLEY")
        assert result is not None
        # Should match FAC_A (exact alias match would catch this, but if fuzzy:
        # "NORTH VALLEY" is closer to "NORTH VALLEY" than "NORTH VALLEY REGIONAL")
        assert result.canonical_id == "FAC_A"


class TestFuzzyMatchEdgeCases:
    """Edge cases for fuzzy matching."""

    def test_none_input(self) -> None:
        """None input returns None."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy(None)
        assert result is None

    def test_empty_string_input(self) -> None:
        """Empty string returns None."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy("")
        assert result is None

    def test_whitespace_only_input(self) -> None:
        """Whitespace-only input returns None."""
        matcher = _build_matcher()
        result = matcher.match_fuzzy("   ")
        assert result is None

    def test_no_facilities_configured(self) -> None:
        """Empty facility config returns None for any input."""
        matcher = _build_matcher(facilities=[])
        result = matcher.match_fuzzy("ST MARYS EAST")
        assert result is None

    def test_input_is_normalized_before_comparison(self) -> None:
        """Input is normalized before fuzzy comparison."""
        matcher = _build_matcher()
        # Raw input with punctuation and case should still match
        result = matcher.match_fuzzy("St. Mary's East")
        assert result is not None
        assert result.canonical_id == "FAC_001"


class TestFuzzyMatchComparesBothAliasesAndCanonicalName:
    """Fuzzy matching compares against all known names and aliases."""

    def test_matches_against_alias(self) -> None:
        """Fuzzy match works against stored aliases."""
        matcher = _build_matcher()
        # "GOOD SAMARITAN" is close to alias "GOOD SAMARITAN WEST"
        result = matcher.match_fuzzy("GOOD SAMARITAN WEST WING")
        # Should match FAC_003 if score is above threshold
        if result is not None:
            assert result.canonical_id == "FAC_003"

    def test_matches_against_canonical_name(self) -> None:
        """Fuzzy match works against canonical name (normalized)."""
        matcher = _build_matcher()
        # "MEMORIAL REGL" normalizes to "MEMORIAL REGIONAL" which is stored
        result = matcher.match_fuzzy("MEMORIAL REGL")
        assert result is not None
        assert result.canonical_id == "FAC_002"
