"""ConfidenceScorer - weighted confidence scoring for encounters (US-064).

Computes: base_score = sum(signal_i * weight_i) / sum(weight_i)

7 signals with default weights:
  HAS_CLAIMS (30), HAS_ADT_ADMIT (20), HAS_ADT_DISCHARGE (10),
  HAS_AUTH (10), FACILITY_RESOLVED (5), TIMESTAMPS_CONSISTENT (15),
  PATIENT_CLASS_CONSISTENT (10)

Maximum raw score = 100, normalized to 1.0.
"""

from __future__ import annotations

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

_ADMIT_EVENT_TYPES: set[str] = {
    "ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START",
}
_DISCHARGE_EVENT_TYPES: set[str] = {
    "DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END",
}


class ConfidenceScorer:
    """Computes a weighted confidence score for encounters."""

    def __init__(
        self,
        signal_weights: dict[str, int] | None = None,
    ) -> None:
        self.signal_weights = signal_weights or dict(_DEFAULT_SIGNAL_WEIGHTS)
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
        """Compute the base confidence score normalized to [0, 1]."""
        if self.max_score == 0:
            return 0.0

        signals = self.evaluate_signals(encounter)
        raw_score = sum(
            self.signal_weights[signal]
            for signal, active in signals.items()
            if active
        )
        return raw_score / self.max_score

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
