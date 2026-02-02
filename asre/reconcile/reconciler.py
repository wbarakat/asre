"""Reconciler — cross-source timestamp and classification reconciliation.

US-058: Timestamp selection by source priority. Encounter timestamps
(admit_ts, discharge_ts) are selected from the most trusted source
based on configurable timestamp_priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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


@dataclass
class ReconciledTimestamps:
    """Result of timestamp reconciliation for an encounter."""

    admit_ts: datetime
    admit_source_priority: str
    discharge_ts: datetime | None
    discharge_source_priority: str | None


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
    ) -> None:
        self.timestamp_priority = timestamp_priority or dict(_DEFAULT_TIMESTAMP_PRIORITY)

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
