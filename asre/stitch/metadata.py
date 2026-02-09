"""Encounter metadata derivation from StitchedEncounter (US-051).

Derives encounter-level metadata fields from the events in a StitchedEncounter:
- encounter_type: inpatient > observation > ed_only > outpatient
- status: open, closed, cancelled
- admit_ts, discharge_ts, los_hours
- source_event_ids, source_systems, has_adt, has_claims, has_auth
- obs_to_ip_conversion
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from asre.stitch.encounter_stitcher import StitchedEncounter


# Event types considered as admit/arrival events for timestamp derivation
_ADMIT_EVENT_TYPES = {"ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START"}

# Event types considered as discharge events for timestamp derivation
_DISCHARGE_EVENT_TYPES = {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"}


@dataclass
class EncounterMetadata:
    """Derived metadata for an encounter."""

    encounter_type: str
    status: str
    admit_ts: datetime
    discharge_ts: datetime | None
    los_hours: float | None
    source_event_ids: list[str]
    source_systems: list[str]
    has_adt: bool
    has_claims: bool
    has_auth: bool
    obs_to_ip_conversion: bool


def build_encounter_metadata(encounter: StitchedEncounter) -> EncounterMetadata:
    """Build derived metadata from a StitchedEncounter's events.

    Args:
        encounter: A stitched encounter with events already added.

    Returns:
        EncounterMetadata with all derived fields populated.
    """
    encounter_type = _derive_encounter_type(encounter)
    status = encounter.status
    admit_ts = _derive_admit_ts(encounter)
    discharge_ts = _derive_discharge_ts(encounter)

    los_hours: float | None = None
    if discharge_ts is not None and admit_ts is not None:
        delta = discharge_ts - admit_ts
        los_hours = delta.total_seconds() / 3600.0

    source_event_ids = [e.event_id for e in encounter.events]
    source_systems = sorted(set(e.source_system for e in encounter.events))

    has_adt = any(s.startswith("adt") for s in source_systems)
    has_claims = any(s.startswith("claims") for s in source_systems)
    has_auth = any(s.startswith("auth") for s in source_systems)

    return EncounterMetadata(
        encounter_type=encounter_type,
        status=status,
        admit_ts=admit_ts,
        discharge_ts=discharge_ts,
        los_hours=los_hours,
        source_event_ids=source_event_ids,
        source_systems=source_systems,
        has_adt=has_adt,
        has_claims=has_claims,
        has_auth=has_auth,
        obs_to_ip_conversion=encounter.obs_to_ip_conversion,
    )


def _derive_encounter_type(encounter: StitchedEncounter) -> str:
    """Derive encounter type from the encounter's patient classes.

    Rules:
    - If any IP event -> inpatient
    - If OBS events but no IP -> observation
    - If only ED events -> ed_only
    - Otherwise -> outpatient
    """
    # The stitcher already tracks encounter_type as highest-priority patient_class
    enc_type = encounter.encounter_type
    if enc_type is None:
        return "outpatient"
    if enc_type == "ed":
        return "ed_only"
    return enc_type


def _derive_admit_ts(encounter: StitchedEncounter) -> datetime:
    """Get the earliest admit/arrival event timestamp."""
    admit_ts: datetime | None = None
    for event in encounter.events:
        if event.event_type in _ADMIT_EVENT_TYPES:
            if admit_ts is None or event.event_ts < admit_ts:
                admit_ts = event.event_ts
    # Fallback to earliest event timestamp if no admit-type events
    if admit_ts is None and encounter.events:
        admit_ts = min(e.event_ts for e in encounter.events)
    # Should never be None if encounter has events
    if admit_ts is None:
        raise RuntimeError("Encounter has no events")
    return admit_ts


def _derive_discharge_ts(encounter: StitchedEncounter) -> datetime | None:
    """Get the latest discharge event timestamp, or None if encounter is open."""
    if not encounter.has_discharge:
        return None
    discharge_ts: datetime | None = None
    for event in encounter.events:
        if event.event_type in _DISCHARGE_EVENT_TYPES:
            if discharge_ts is None or event.event_ts > discharge_ts:
                discharge_ts = event.event_ts
    return discharge_ts
