"""Encounter stitcher — groups canonical events into encounters.

US-043: Basic encounter stitching. Events are partitioned by patient_key,
sorted by event_ts, and grouped into encounters using time window + facility matching.

US-045: ED to IP merge. ED_ARRIVAL + ADMIT at same facility within time window
merges into a single encounter with encounter_type = inpatient.

US-046: OBS to IP conversion. OBS_START + OBS_TO_IP at same facility within time
window merges into a single encounter with obs_to_ip_conversion = true.

US-047: IP to IP as new encounter. DISCHARGE + new ADMIT (both IP) at same facility
within time window produces two separate encounters based on patient_class_transitions
with action=new_encounter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from asre.models.canonical_event import CanonicalEvent


@dataclass
class StitchedEncounter:
    """An intermediate encounter grouping produced by the stitcher.

    Contains the grouped events and basic metadata. Downstream stages
    (dedup, reconcile, score) enrich this into the final Encounter dataclass.
    """

    patient_key: str
    facility_canonical_id: str | None
    events: list[CanonicalEvent] = field(default_factory=list)
    last_event_ts: datetime | None = None
    encounter_type: str | None = None
    obs_to_ip_conversion: bool = False
    has_discharge: bool = False

    # Event types that indicate a discharge has occurred
    _DISCHARGE_EVENT_TYPES: set[str] = field(
        default_factory=lambda: {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"},
        repr=False,
    )

    # Event types that indicate an admission
    _ADMIT_EVENT_TYPES: set[str] = field(
        default_factory=lambda: {"ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START"},
        repr=False,
    )

    def add_event(self, event: CanonicalEvent) -> None:
        """Add an event to this encounter and update last_event_ts and encounter_type."""
        self.events.append(event)
        if self.last_event_ts is None or event.event_ts > self.last_event_ts:
            self.last_event_ts = event.event_ts
        self._update_encounter_type(event)
        self._check_obs_to_ip(event)
        if event.event_type in self._DISCHARGE_EVENT_TYPES:
            self.has_discharge = True

    def _check_obs_to_ip(self, event: CanonicalEvent) -> None:
        """Detect OBS_TO_IP event and set conversion flag."""
        if event.event_type == "OBS_TO_IP":
            self.obs_to_ip_conversion = True

    def _update_encounter_type(self, event: CanonicalEvent) -> None:
        """Derive encounter_type from the highest-priority patient_class seen.

        Priority: inpatient > observation > ed > outpatient.
        """
        priority = {"inpatient": 0, "observation": 1, "ed": 2, "outpatient": 3}
        event_class = event.patient_class
        if event_class is None:
            return
        new_priority = priority.get(event_class.lower(), 4)
        if self.encounter_type is None:
            self.encounter_type = event_class.lower()
        else:
            current_priority = priority.get(self.encounter_type, 4)
            if new_priority < current_priority:
                self.encounter_type = event_class.lower()


class EncounterStitcher:
    """Groups canonical events into encounters by patient, facility, and time window.

    Algorithm:
    1. Partition events by patient_key
    2. Sort by event_ts ascending (tiebreaker: source type priority)
    3. Iterate: events within time_window_hours of current encounter's last event
       AND same facility -> stitch into same encounter
    4. Otherwise -> close current encounter, start new one
    """

    # Default patient class transition rules per SPEC §4.2
    DEFAULT_TRANSITIONS: list[dict[str, str]] = [
        {"from": "ed", "to": "inpatient", "action": "merge"},
        {"from": "observation", "to": "inpatient", "action": "merge"},
        {"from": "inpatient", "to": "inpatient", "action": "new_encounter"},
    ]

    def __init__(
        self,
        time_window_hours: int = 48,
        facility_must_match: bool = True,
        same_timestamp_tiebreaker: list[str] | None = None,
        patient_class_transitions: list[dict[str, str]] | None = None,
    ) -> None:
        self.time_window_hours = time_window_hours
        self.facility_must_match = facility_must_match
        self.same_timestamp_tiebreaker = same_timestamp_tiebreaker or [
            "claims",
            "adt",
            "auth",
        ]
        self.patient_class_transitions = (
            patient_class_transitions
            if patient_class_transitions is not None
            else self.DEFAULT_TRANSITIONS
        )

    def stitch(self, events: list[CanonicalEvent]) -> list[StitchedEncounter]:
        """Stitch canonical events into encounter groupings.

        Args:
            events: List of canonical events (from any number of patients).

        Returns:
            List of StitchedEncounter groupings.
        """
        if not events:
            return []

        # Partition by patient_key
        patient_events: dict[str, list[CanonicalEvent]] = {}
        for event in events:
            patient_events.setdefault(event.patient_key, []).append(event)

        encounters: list[StitchedEncounter] = []
        for patient_key, pat_events in patient_events.items():
            sorted_events = self._sort_events(pat_events)
            patient_encounters = self._stitch_patient_events(
                patient_key, sorted_events
            )
            encounters.extend(patient_encounters)

        return encounters

    def _sort_events(self, events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        """Sort events by event_ts ascending, with tiebreaker by source type priority."""
        tiebreaker_map = self._build_tiebreaker_map()

        def sort_key(event: CanonicalEvent) -> tuple[datetime, int]:
            source_type = self._extract_source_type(event.source_system)
            priority = tiebreaker_map.get(source_type, len(self.same_timestamp_tiebreaker))
            return (event.event_ts, priority)

        return sorted(events, key=sort_key)

    def _build_tiebreaker_map(self) -> dict[str, int]:
        """Build source_type -> priority index from tiebreaker config.

        Lower index = higher priority (appears first in sort).
        """
        return {
            source_type: idx
            for idx, source_type in enumerate(self.same_timestamp_tiebreaker)
        }

    def _extract_source_type(self, source_system: str) -> str:
        """Extract source type category from source_system name.

        Maps source_system names like 'adt_vendor_x' -> 'adt',
        'claims_clearinghouse' -> 'claims', 'auth_portal' -> 'auth'.
        """
        lower = source_system.lower()
        if lower.startswith("claims"):
            return "claims"
        if lower.startswith("auth"):
            return "auth"
        if lower.startswith("adt"):
            return "adt"
        return lower

    def _stitch_patient_events(
        self, patient_key: str, sorted_events: list[CanonicalEvent]
    ) -> list[StitchedEncounter]:
        """Stitch sorted events for a single patient into encounters."""
        encounters: list[StitchedEncounter] = []
        current: StitchedEncounter | None = None

        for event in sorted_events:
            if current is None:
                current = StitchedEncounter(
                    patient_key=patient_key,
                    facility_canonical_id=event.facility_canonical_id,
                )
                current.add_event(event)
                continue

            if self._should_stitch(current, event):
                current.add_event(event)
            else:
                encounters.append(current)
                current = StitchedEncounter(
                    patient_key=patient_key,
                    facility_canonical_id=event.facility_canonical_id,
                )
                current.add_event(event)

        if current is not None:
            encounters.append(current)

        return encounters

    def _should_stitch(
        self, current: StitchedEncounter, event: CanonicalEvent
    ) -> bool:
        """Determine if event should be stitched into the current encounter.

        Checks:
        1. Patient class transition rules (new_encounter action forces split)
        2. Facility must match (if configured)
        3. Event is within time_window_hours of current encounter's last event
        """
        # Check patient_class_transitions for new_encounter action
        if self._should_force_new_encounter(current, event):
            return False

        # Check facility match
        if self.facility_must_match:
            if current.facility_canonical_id != event.facility_canonical_id:
                return False
            # Null facilities don't match (unresolved facilities shouldn't auto-stitch)
            if current.facility_canonical_id is None:
                return False

        # Check time window
        if current.last_event_ts is not None:
            time_diff = event.event_ts - current.last_event_ts
            if time_diff > timedelta(hours=self.time_window_hours):
                return False

        return True

    def _should_force_new_encounter(
        self, current: StitchedEncounter, event: CanonicalEvent
    ) -> bool:
        """Check if patient_class transition rules require a new encounter.

        A new encounter is forced when:
        1. The current encounter has had a discharge event
        2. The incoming event is an admit-type event
        3. A transition rule with action=new_encounter matches the
           from (current encounter_type) -> to (incoming patient_class)
        """
        if not current.has_discharge:
            return False

        if event.event_type not in current._ADMIT_EVENT_TYPES:
            return False

        from_class = current.encounter_type
        to_class = event.patient_class
        if from_class is None or to_class is None:
            return False

        to_class_lower = to_class.lower()
        for transition in self.patient_class_transitions:
            if (
                transition.get("from") == from_class
                and transition.get("to") == to_class_lower
                and transition.get("action") == "new_encounter"
            ):
                return True

        return False
