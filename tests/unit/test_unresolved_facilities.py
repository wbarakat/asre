"""Tests for unresolved facility handling (US-039).

When no match is found at any tier (exact, NPI, CCN, fuzzy),
the matcher should create a new facility record, flag it as
FACILITY_NEW_UNREVIEWED, and reuse it for subsequent events
with the same normalized name.
"""

from __future__ import annotations

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.matcher import FacilityMatcher, MatchResult
from asre.facility.normalizer import FacilityNormalizer


def _make_matcher(
    facilities: list[FacilityAlias] | None = None,
    fuzzy_threshold: float = 0.85,
) -> FacilityMatcher:
    """Helper to build a matcher with optional pre-loaded facilities."""
    config = FacilityAliasConfig(facilities=facilities or [])
    normalizer = FacilityNormalizer()
    return FacilityMatcher(
        alias_config=config,
        normalizer=normalizer,
        fuzzy_threshold=fuzzy_threshold,
    )


class TestUnresolvedFacilityCreation:
    """When no match found at any tier, create new facility record."""

    def test_resolve_unknown_returns_match_result(self) -> None:
        """Calling resolve_or_create for unknown name returns a MatchResult."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("Totally Unknown Hospital")
        assert result is not None
        assert isinstance(result, MatchResult)

    def test_resolve_unknown_generates_canonical_id(self) -> None:
        """New facility gets auto-generated facility_canonical_id."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("Totally Unknown Hospital")
        assert result is not None
        assert result.canonical_id  # non-empty
        assert isinstance(result.canonical_id, str)

    def test_resolve_unknown_match_type_is_new(self) -> None:
        """New facility has match_type = 'new'."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("Totally Unknown Hospital")
        assert result is not None
        assert result.match_type == "new"

    def test_resolve_unknown_score_is_zero(self) -> None:
        """New facility has score = 0.0 (no match confidence)."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("Totally Unknown Hospital")
        assert result is not None
        assert result.score == 0.0

    def test_resolve_unknown_flagged_new_unreviewed(self) -> None:
        """New facility is flagged FACILITY_NEW_UNREVIEWED."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("Totally Unknown Hospital")
        assert result is not None
        assert result.flags is not None
        assert "FACILITY_NEW_UNREVIEWED" in result.flags


class TestUnresolvedFacilityReuse:
    """Subsequent events with same normalized name reuse the new facility."""

    def test_same_name_reuses_facility(self) -> None:
        """Second event with same normalized name returns same canonical_id."""
        matcher = _make_matcher()
        result1 = matcher.resolve_or_create("Brand New Place Hospital")
        result2 = matcher.resolve_or_create("Brand New Place Hospital")
        assert result1 is not None
        assert result2 is not None
        assert result1.canonical_id == result2.canonical_id

    def test_same_normalized_name_reuses_facility(self) -> None:
        """Variant spelling normalizing to same string reuses same facility."""
        matcher = _make_matcher()
        result1 = matcher.resolve_or_create("Brand New Place Hospital")
        # Different raw string, but normalizes the same
        result2 = matcher.resolve_or_create("brand new place hosp")
        assert result1 is not None
        assert result2 is not None
        assert result1.canonical_id == result2.canonical_id

    def test_reused_facility_match_type_is_exact(self) -> None:
        """Second match against a runtime-created facility uses match_type='exact'."""
        matcher = _make_matcher()
        matcher.resolve_or_create("Brand New Place Hospital")
        result2 = matcher.resolve_or_create("Brand New Place Hospital")
        assert result2 is not None
        # Second time it hits the alias index — that's an exact match
        assert result2.match_type == "exact"

    def test_different_names_create_different_facilities(self) -> None:
        """Two distinct unknown names create two distinct facilities."""
        matcher = _make_matcher()
        result1 = matcher.resolve_or_create("Alpha General Hospital")
        result2 = matcher.resolve_or_create("Beta Regional Hospital")
        assert result1 is not None
        assert result2 is not None
        assert result1.canonical_id != result2.canonical_id


class TestUnresolvedFacilityAlias:
    """New facility's normalized name becomes its first alias."""

    def test_new_facility_added_to_alias_index(self) -> None:
        """After creation, exact match on same name finds the new facility."""
        matcher = _make_matcher()
        created = matcher.resolve_or_create("Totally Unknown Hospital")
        assert created is not None

        # Now exact match should find it
        exact = matcher.match_exact("Totally Unknown Hospital")
        assert exact is not None
        assert exact.canonical_id == created.canonical_id

    def test_new_facility_added_to_fuzzy_candidates(self) -> None:
        """After creation, fuzzy match on similar name can find the new facility."""
        matcher = _make_matcher(fuzzy_threshold=0.70)
        created = matcher.resolve_or_create("Springfield General Hospital")
        assert created is not None

        # Fuzzy should match a similar input
        fuzzy = matcher.match_fuzzy("Springfield General Hosp")
        assert fuzzy is not None
        assert fuzzy.canonical_id == created.canonical_id


class TestResolveOrCreateCascade:
    """resolve_or_create should try existing match tiers before creating new."""

    def test_exact_match_returns_existing(self) -> None:
        """If exact match exists, resolve_or_create returns it (no new facility)."""
        matcher = _make_matcher(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_001",
                    canonical_name="St. Mary's Medical Center",
                    aliases=["St Marys Med Ctr"],
                )
            ]
        )
        result = matcher.resolve_or_create("St Marys Med Ctr")
        assert result is not None
        assert result.canonical_id == "FAC_001"
        assert result.match_type == "exact"

    def test_npi_match_returns_existing(self) -> None:
        """If NPI match exists, resolve_or_create returns it."""
        matcher = _make_matcher(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_002",
                    canonical_name="City Hospital",
                    npi="1234567890",
                )
            ]
        )
        result = matcher.resolve_or_create(
            "Some Random Name", npi="1234567890"
        )
        assert result is not None
        assert result.canonical_id == "FAC_002"
        assert result.match_type == "npi"

    def test_ccn_match_returns_existing(self) -> None:
        """If CCN match exists, resolve_or_create returns it."""
        matcher = _make_matcher(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_003",
                    canonical_name="County Medical",
                    ccn="050001",
                )
            ]
        )
        result = matcher.resolve_or_create(
            "Some Random Name", ccn="050001"
        )
        assert result is not None
        assert result.canonical_id == "FAC_003"
        assert result.match_type == "ccn"

    def test_fuzzy_match_returns_existing(self) -> None:
        """If fuzzy match exists above threshold, resolve_or_create returns it."""
        matcher = _make_matcher(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_004",
                    canonical_name="Memorial Regional Hospital",
                    aliases=["Memorial Regional"],
                )
            ],
            fuzzy_threshold=0.70,
        )
        # "MEMORIA REGIONL" won't exact-match but fuzzy should catch it
        result = matcher.resolve_or_create("Memoria Regionl")
        assert result is not None
        assert result.canonical_id == "FAC_004"
        assert result.match_type == "fuzzy"

    def test_creates_new_when_no_tier_matches(self) -> None:
        """Only creates new facility when all tiers fail."""
        matcher = _make_matcher(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_001",
                    canonical_name="St. Mary's Medical Center",
                )
            ]
        )
        result = matcher.resolve_or_create("Completely Different Place")
        assert result is not None
        assert result.match_type == "new"
        assert result.canonical_id != "FAC_001"


class TestEdgeCases:
    """Edge cases for resolve_or_create."""

    def test_empty_string_returns_none(self) -> None:
        """Empty string input returns None."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("")
        assert result is None

    def test_none_input_returns_none(self) -> None:
        """None input returns None."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create(None)
        assert result is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only input returns None."""
        matcher = _make_matcher()
        result = matcher.resolve_or_create("   ")
        assert result is None
