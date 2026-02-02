"""Reconciler — cross-source timestamp and classification reconciliation.

US-058: Timestamp selection by source priority. Encounter timestamps
(admit_ts, discharge_ts) are selected from the most trusted source
based on configurable timestamp_priority.

US-059: Classification resolution by source priority. Encounter type,
DRG, payer, and diagnoses are selected from the most trusted
classification source.

US-060: Auth reconciliation rules. Auth events validate encounters
without anchoring them. Auth has lowest priority for timestamps and
classification. Orphan auth signals (no ADT/claims) produce
AUTH_WITHOUT_ADMIT flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import StitchedEncounter


# Event types that indicate an admission
_ADMIT_EVENT_TYPES = {"ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START"}

# Event types that indicate a discharge
_DISCHARGE_EVENT_TYPES = {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"}

# Default timestamp priority (higher = more trusted)
_DEFAULT_TIMESTAMP_PRIORITY: dict[str, int] = {
    "adt": 100,
    "claims": 80,
    "auth": 40,
}

# Default classification priority (higher = more trusted)
_DEFAULT_CLASSIFICATION_PRIORITY: dict[str, int] = {
    "claims": 100,
    "adt": 80,
    "auth": 40,
}


@dataclass
class ReconciledTimestamps:
    """Result of timestamp reconciliation for an encounter."""

    admit_ts: datetime
    admit_source_priority: str
    discharge_ts: datetime | None
    discharge_source_priority: str | None


@dataclass
class ReconciledClassification:
    """Result of classification reconciliation for an encounter."""

    encounter_type: str
    drg: str | None = None
    payer_id: str | None = None
    principal_diagnosis: str | None = None
    admitting_diagnosis: str | None = None
    diagnosis_codes: list[dict[str, Any]] = field(default_factory=list)


def _extract_source_type(source_system: str) -> str:
    """Extract source type prefix from source_system name."""
    lower = source_system.lower()
    for prefix in ("claims", "auth", "adt"):
        if lower.startswith(prefix):
            return prefix
    return lower


class Reconciler:
    """Reconciles cross-source conflicts for encounter timestamps and classification.

    Selects timestamps from the most trusted source based on configurable
    priority. ADT has highest default priority (100), followed by claims (80),
    then auth (40).
    """

    def __init__(
        self,
        timestamp_priority: dict[str, int] | None = None,
        classification_priority: dict[str, int] | None = None,
    ) -> None:
        self.timestamp_priority = timestamp_priority or dict(_DEFAULT_TIMESTAMP_PRIORITY)
        self.classification_priority = classification_priority or dict(_DEFAULT_CLASSIFICATION_PRIORITY)

    def reconcile_timestamps(
        self, encounter: StitchedEncounter
    ) -> ReconciledTimestamps:
        """Select admit_ts and discharge_ts from the highest-priority source.

        For admit: finds all admit-type events, selects the one from the
        source with the highest timestamp_priority.
        For discharge: same logic with discharge-type events.

        Args:
            encounter: A stitched encounter with events.

        Returns:
            ReconciledTimestamps with selected timestamps and source info.
        """
        admit_ts, admit_source = self._select_timestamp(
            encounter.events, _ADMIT_EVENT_TYPES
        )
        discharge_ts, discharge_source = self._select_timestamp(
            encounter.events, _DISCHARGE_EVENT_TYPES
        )

        # Fallback: if no admit-type event, use earliest event
        if admit_ts is None or admit_source is None:
            earliest = min(encounter.events, key=lambda e: e.event_ts)
            admit_ts = earliest.event_ts
            admit_source = _extract_source_type(earliest.source_system)

        return ReconciledTimestamps(
            admit_ts=admit_ts,
            admit_source_priority=admit_source,
            discharge_ts=discharge_ts,
            discharge_source_priority=discharge_source,
        )

    def reconcile_classification(
        self, encounter: StitchedEncounter
    ) -> ReconciledClassification:
        """Select encounter_type, DRG, payer, and diagnoses from the highest-priority source.

        Classification priority defaults: claims=100, ADT=80, auth=40.
        DRG and principal_diagnosis are set from claims when available.
        Admitting diagnosis is set from ADT when available.
        Diagnosis codes are aggregated from all sources with claims taking precedence.

        Args:
            encounter: A stitched encounter with events.

        Returns:
            ReconciledClassification with resolved fields.
        """
        # Group events by source type with their priority
        source_events: dict[str, list[CanonicalEvent]] = {}
        for event in encounter.events:
            source_type = _extract_source_type(event.source_system)
            source_events.setdefault(source_type, []).append(event)

        # Sort source types by classification priority descending
        sorted_sources = sorted(
            source_events.keys(),
            key=lambda s: self.classification_priority.get(s, 0),
            reverse=True,
        )

        # Encounter type: from highest classification priority source with patient_class
        encounter_type = self._resolve_encounter_type(sorted_sources, source_events)

        # DRG: from claims when available, fallback to other sources by priority
        drg = self._resolve_field(sorted_sources, source_events, "drg")

        # Payer: from highest classification priority source
        payer_id = self._resolve_field(sorted_sources, source_events, "payer_id")

        # Principal diagnosis: from highest classification priority source
        principal_diagnosis = self._resolve_field(
            sorted_sources, source_events, "principal_diagnosis"
        )

        # Admitting diagnosis: specifically from ADT
        admitting_diagnosis = self._resolve_admitting_diagnosis(source_events)

        # Diagnosis codes: aggregated from all sources, claims first
        diagnosis_codes = self._aggregate_diagnosis_codes(sorted_sources, source_events)

        return ReconciledClassification(
            encounter_type=encounter_type,
            drg=drg,
            payer_id=payer_id,
            principal_diagnosis=principal_diagnosis,
            admitting_diagnosis=admitting_diagnosis,
            diagnosis_codes=diagnosis_codes,
        )

    def _resolve_encounter_type(
        self,
        sorted_sources: list[str],
        source_events: dict[str, list[CanonicalEvent]],
    ) -> str:
        """Resolve encounter_type from highest-priority source with patient_class."""
        for source_type in sorted_sources:
            for event in source_events[source_type]:
                if event.patient_class:
                    return event.patient_class
        return "outpatient"

    def _resolve_field(
        self,
        sorted_sources: list[str],
        source_events: dict[str, list[CanonicalEvent]],
        field_name: str,
    ) -> str | None:
        """Resolve a field from the highest-priority source that has it set."""
        for source_type in sorted_sources:
            for event in source_events[source_type]:
                value: str | None = getattr(event, field_name, None)
                if value is not None:
                    return value
        return None

    def _resolve_admitting_diagnosis(
        self,
        source_events: dict[str, list[CanonicalEvent]],
    ) -> str | None:
        """Resolve admitting diagnosis specifically from ADT source."""
        adt_events = source_events.get("adt", [])
        for event in adt_events:
            if event.principal_diagnosis is not None:
                return event.principal_diagnosis
        return None

    def _aggregate_diagnosis_codes(
        self,
        sorted_sources: list[str],
        source_events: dict[str, list[CanonicalEvent]],
    ) -> list[dict[str, Any]]:
        """Aggregate diagnosis codes from all sources, highest priority first.

        Codes from higher-priority sources appear first. Duplicate codes
        (by code value) from lower-priority sources are excluded.
        """
        result: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        for source_type in sorted_sources:
            for event in source_events[source_type]:
                if event.diagnosis_codes:
                    for dx in event.diagnosis_codes:
                        code = dx.get("code", "")
                        if code and code not in seen_codes:
                            seen_codes.add(code)
                            result.append(dx)
        return result

    def reconcile_auth(
        self, encounter: StitchedEncounter
    ) -> list[str]:
        """Check auth reconciliation rules and return flags.

        Auth events are never used as anchors for encounter creation.
        Auth has lowest priority for both timestamps and classification
        (enforced by default priority configs).

        If auth events exist with NO matching ADT or claims events in the
        encounter, flag AUTH_WITHOUT_ADMIT.

        Args:
            encounter: A stitched encounter with events.

        Returns:
            List of flag strings (e.g., ["AUTH_WITHOUT_ADMIT"]).
        """
        flags: list[str] = []

        has_auth = False
        has_adt_or_claims = False

        for event in encounter.events:
            source_type = _extract_source_type(event.source_system)
            if source_type == "auth":
                has_auth = True
            elif source_type in ("adt", "claims"):
                has_adt_or_claims = True

        if has_auth and not has_adt_or_claims:
            flags.append("AUTH_WITHOUT_ADMIT")

        return flags

    def _select_timestamp(
        self,
        events: list[CanonicalEvent],
        event_types: set[str],
    ) -> tuple[datetime | None, str | None]:
        """Select a timestamp from the highest-priority source among matching events.

        Groups matching events by source type, picks the source with highest
        priority, then returns the earliest timestamp from that source.

        Args:
            events: All events in the encounter.
            event_types: Set of event types to consider (admit or discharge types).

        Returns:
            Tuple of (timestamp, source_type) or (None, None) if no matching events.
        """
        matching = [e for e in events if e.event_type in event_types]
        if not matching:
            return None, None

        # Group by source type and find highest priority source
        best_event: CanonicalEvent | None = None
        best_priority: int = -1
        best_source_type: str = ""

        for event in matching:
            source_type = _extract_source_type(event.source_system)
            priority = self.timestamp_priority.get(source_type, 0)

            if priority > best_priority:
                best_priority = priority
                best_event = event
                best_source_type = source_type
            elif priority == best_priority and best_event is not None:
                # Same priority: use earliest timestamp
                if event.event_ts < best_event.event_ts:
                    best_event = event
                    best_source_type = source_type

        if best_event is None:
            return None, None

        return best_event.event_ts, best_source_type
