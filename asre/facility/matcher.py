"""Facility matching with exact alias, NPI, CCN, and fuzzy lookup.

Matches normalized input strings against known facility aliases
loaded from FacilityAliasConfig. Both input and aliases are
normalized via FacilityNormalizer for case-insensitive comparison.
NPI and CCN identifiers provide direct lookup when available.
Fuzzy matching via rapidfuzz token_sort_ratio as fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from asre.config.facility_alias_schema import FacilityAliasConfig
from asre.facility.normalizer import FacilityNormalizer


@dataclass
class MatchResult:
    """Result of a facility match attempt."""

    canonical_id: str
    match_type: str
    score: float


class FacilityMatcher:
    """Matches facility name strings against known aliases.

    Loads facility aliases from FacilityAliasConfig into an in-memory
    lookup indexed by normalized alias strings.
    """

    def __init__(
        self,
        alias_config: FacilityAliasConfig,
        normalizer: FacilityNormalizer,
        fuzzy_threshold: float = 0.85,
    ) -> None:
        self._normalizer = normalizer
        self._fuzzy_threshold = fuzzy_threshold
        # Build normalized alias -> canonical_id lookup
        self._alias_index: dict[str, str] = {}
        # Build NPI -> canonical_id lookup
        self._npi_index: dict[str, str] = {}
        # Build CCN -> canonical_id lookup
        self._ccn_index: dict[str, str] = {}
        # Build list of (normalized_name, canonical_id) for fuzzy comparison
        self._fuzzy_candidates: list[tuple[str, str]] = []
        for facility in alias_config.facilities:
            # Index the canonical_name itself (normalized)
            normalized_name = normalizer.normalize(facility.canonical_name)
            if normalized_name:
                self._alias_index[normalized_name] = facility.canonical_id
                self._fuzzy_candidates.append((normalized_name, facility.canonical_id))
            # Index each alias (normalized)
            for alias in facility.aliases:
                normalized_alias = normalizer.normalize(alias)
                if normalized_alias:
                    self._alias_index[normalized_alias] = facility.canonical_id
                    self._fuzzy_candidates.append(
                        (normalized_alias, facility.canonical_id)
                    )
            # Index NPI if present
            if facility.npi:
                self._npi_index[facility.npi.strip()] = facility.canonical_id
            # Index CCN if present
            if facility.ccn:
                self._ccn_index[facility.ccn.strip()] = facility.canonical_id

    def match_exact(self, facility_name: str | None) -> MatchResult | None:
        """Attempt exact match of normalized input against known aliases.

        Args:
            facility_name: Raw facility name string to match.

        Returns:
            MatchResult with canonical_id if matched, None otherwise.
        """
        if not facility_name:
            return None

        normalized = self._normalizer.normalize(facility_name)
        if not normalized:
            return None

        canonical_id = self._alias_index.get(normalized)
        if canonical_id is not None:
            return MatchResult(
                canonical_id=canonical_id,
                match_type="exact",
                score=1.0,
            )

        return None

    def match_npi(self, npi: str | None) -> MatchResult | None:
        """Attempt match by NPI identifier.

        Args:
            npi: NPI string from source record.

        Returns:
            MatchResult with canonical_id if matched, None otherwise.
        """
        if not npi or not npi.strip():
            return None

        canonical_id = self._npi_index.get(npi.strip())
        if canonical_id is not None:
            return MatchResult(
                canonical_id=canonical_id,
                match_type="npi",
                score=1.0,
            )

        return None

    def match_ccn(self, ccn: str | None) -> MatchResult | None:
        """Attempt match by CCN identifier.

        Args:
            ccn: CCN string from source record.

        Returns:
            MatchResult with canonical_id if matched, None otherwise.
        """
        if not ccn or not ccn.strip():
            return None

        canonical_id = self._ccn_index.get(ccn.strip())
        if canonical_id is not None:
            return MatchResult(
                canonical_id=canonical_id,
                match_type="ccn",
                score=1.0,
            )

        return None

    def match_fuzzy(self, facility_name: str | None) -> MatchResult | None:
        """Attempt fuzzy match using rapidfuzz token_sort_ratio.

        Compares normalized input against all known facility names and
        aliases. Accepts match if score >= fuzzy_threshold. If multiple
        facilities score above threshold, selects the highest score.

        Args:
            facility_name: Raw facility name string to match.

        Returns:
            MatchResult with canonical_id if matched, None otherwise.
        """
        if not facility_name:
            return None

        normalized = self._normalizer.normalize(facility_name)
        if not normalized:
            return None

        if not self._fuzzy_candidates:
            return None

        best_score = 0.0
        best_canonical_id: str | None = None

        for candidate_name, canonical_id in self._fuzzy_candidates:
            # rapidfuzz token_sort_ratio returns 0-100
            score = fuzz.token_sort_ratio(normalized, candidate_name) / 100.0
            if score > best_score:
                best_score = score
                best_canonical_id = canonical_id

        if best_canonical_id is not None and best_score >= self._fuzzy_threshold:
            return MatchResult(
                canonical_id=best_canonical_id,
                match_type="fuzzy",
                score=best_score,
            )

        return None
