"""ConfidenceScorer - weighted confidence scoring for encounters (US-064, US-067).

Computes: base_score = sum(signal_i * weight_i) / sum(weight_i)

7 signals with default weights:
  HAS_CLAIMS (30), HAS_ADT_ADMIT (20), HAS_ADT_DISCHARGE (10),
  HAS_AUTH (10), FACILITY_RESOLVED (5), TIMESTAMPS_CONSISTENT (15),
  PATIENT_CLASS_CONSISTENT (10)

Maximum raw score = 100, normalized to 1.0.

US-067: Stale encounter detection with facility-type-aware thresholds.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from asre.reconcile.stage import ReconciledEncounter

_DEFAULT_SIGNAL_WEIGHTS: dict[str, int] = {
    "HAS_CLAIMS": 30,
    "HAS_ADT_ADMIT": 20,
    "HAS_ADT_DISCHARGE": 10,
    "HAS_AUTH": 10,
    "FACILITY_RESOLVED": 5,
    "TIMESTAMPS_CONSISTENT": 15,
    "PATIENT_CLASS_CONSISTENT": 10,
}

_DEFAULT_PENALTY_WEIGHTS: dict[str, float] = {
    "MISSING_DISCHARGE": -0.15,
    "ORPHAN_DISCHARGE": -0.20,
    "TIMESTAMP_MISMATCH": -0.10,
    "CLAIMS_ONLY_ENCOUNTER": -0.10,
    "STALE_OPEN_ENCOUNTER": -0.20,
    "DUPLICATE_DETECTED": -0.05,
    "FACILITY_UNRESOLVED": -0.10,
    "AUTH_WITHOUT_ADMIT": -0.05,
    "CANCELLED_AND_REOPENED": -0.05,
}

_ADMIT_EVENT_TYPES: set[str] = {
    "ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START",
}
_DISCHARGE_EVENT_TYPES: set[str] = {
    "DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END",
}

_DEFAULT_STALE_THRESHOLDS: dict[str, int] = {
    "acute": 30,
    "ed_standalone": 3,
    "ltach": 90,
    "snf": 120,
    "rehab": 60,
    "psych": 90,
    "default": 30,
}


class ConfidenceScorer:
    """Computes a weighted confidence score for encounters."""

    def __init__(
        self,
        signal_weights: dict[str, int] | None = None,
        penalty_weights: dict[str, float] | None = None,
        stale_thresholds: dict[str, int] | None = None,
    ) -> None:
        self.signal_weights = signal_weights or dict(_DEFAULT_SIGNAL_WEIGHTS)
        self.penalty_weights = penalty_weights or dict(_DEFAULT_PENALTY_WEIGHTS)
        self.stale_thresholds = stale_thresholds or dict(_DEFAULT_STALE_THRESHOLDS)
        self.max_score = sum(self.signal_weights.values())

    def evaluate_signals(self, encounter: ReconciledEncounter) -> dict[str, bool]:
        """Evaluate which binary signals are active for an encounter."""
        events = encounter.events
        source_types: set[str] = set()
        has_adt_admit = False
        has_adt_discharge = False
        patient_classes: set[str] = set()

        for evt in events:
            src_type = self._extract_source_type(evt.source_system)
            source_types.add(src_type)

            if src_type == "adt":
                if evt.event_type in _ADMIT_EVENT_TYPES:
                    has_adt_admit = True
                if evt.event_type in _DISCHARGE_EVENT_TYPES:
                    has_adt_discharge = True

            if evt.patient_class:
                patient_classes.add(evt.patient_class)

        has_claims = "claims" in source_types
        has_auth = "auth" in source_types

        facility_resolved = encounter.facility_canonical_id is not None

        # TIMESTAMPS_CONSISTENT: no TIMESTAMP_MISMATCH flag
        flags = encounter.confidence_flags
        timestamps_consistent = "TIMESTAMP_MISMATCH" not in flags

        # PATIENT_CLASS_CONSISTENT: all non-null patient_class values are the same
        patient_class_consistent = len(patient_classes) <= 1

        return {
            "HAS_CLAIMS": has_claims,
            "HAS_ADT_ADMIT": has_adt_admit,
            "HAS_ADT_DISCHARGE": has_adt_discharge,
            "HAS_AUTH": has_auth,
            "FACILITY_RESOLVED": facility_resolved,
            "TIMESTAMPS_CONSISTENT": timestamps_consistent,
            "PATIENT_CLASS_CONSISTENT": patient_class_consistent,
        }

    def compute_score(self, encounter: ReconciledEncounter) -> float:
        """Compute the confidence score: base score minus penalties, floored at 0.0."""
        if self.max_score == 0:
            return 0.0

        signals = self.evaluate_signals(encounter)
        raw_score = sum(
            self.signal_weights[signal]
            for signal, active in signals.items()
            if active
        )
        base_score = raw_score / self.max_score

        # Apply penalties from confidence_flags
        penalty = self._compute_penalty(encounter)
        return max(0.0, base_score + penalty)

    def build_confidence_flags(self, encounter: ReconciledEncounter) -> list[str]:
        """Build the confidence_flags list with active signals and applied penalties.

        Includes:
        - Signal names where signal is active (True)
        - Penalty flag names that are present on the encounter
        """
        signals = self.evaluate_signals(encounter)
        flags: list[str] = [name for name, active in signals.items() if active]

        # Add penalty flags from encounter (already set by reconcile stage)
        for flag in encounter.confidence_flags:
            if flag not in flags:
                flags.append(flag)

        return flags

    def detect_stale_encounter(
        self,
        encounter: ReconciledEncounter,
        *,
        now: datetime,
        facility_type: str | None = None,
    ) -> list[str]:
        """Detect if an encounter is stale based on facility-type-aware thresholds.

        Args:
            encounter: The reconciled encounter to check.
            now: Current reference time for computing open duration.
            facility_type: The facility type (acute, snf, ltach, etc.).
                If None or not in thresholds, uses "default" threshold.

        Returns:
            List of flags (["STALE_OPEN_ENCOUNTER"] or []).
        """
        # Only open encounters can be stale
        if encounter.has_discharge:
            return []

        # Find earliest admit-type event timestamp
        earliest_admit_ts: datetime | None = None
        for evt in encounter.events:
            if evt.event_type in _ADMIT_EVENT_TYPES:
                if earliest_admit_ts is None or evt.event_ts < earliest_admit_ts:
                    earliest_admit_ts = evt.event_ts

        if earliest_admit_ts is None:
            return []

        # Determine threshold in days
        threshold_days = self.stale_thresholds.get(
            facility_type or "default",
            self.stale_thresholds.get("default", 30),
        )

        open_duration = now - earliest_admit_ts
        if open_duration > timedelta(days=threshold_days):
            return ["STALE_OPEN_ENCOUNTER"]

        return []

    def _compute_penalty(self, encounter: ReconciledEncounter) -> float:
        """Compute total penalty from encounter's confidence_flags."""
        flags = encounter.confidence_flags
        total = 0.0
        for flag in flags:
            if flag in self.penalty_weights:
                total += self.penalty_weights[flag]
        return total

    @staticmethod
    def _extract_source_type(source_system: str) -> str:
        """Extract source type prefix from source_system name."""
        lower = source_system.lower()
        if lower.startswith("claims"):
            return "claims"
        if lower.startswith("auth"):
            return "auth"
        if lower.startswith("adt"):
            return "adt"
        return "unknown"
