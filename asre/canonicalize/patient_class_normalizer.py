"""Normalize patient_class values to canonical encounter types."""

from __future__ import annotations

from typing import Any

# Event types that imply a specific patient_class regardless of source value
_OBS_EVENT_TYPES = {"OBS_START", "OBS_END", "OBS_TO_IP"}
_ED_EVENT_TYPES = {"ED_ARRIVAL", "ED_DEPARTURE"}


def normalize_patient_class(
    patient_class: str | None,
    *,
    event_type: str | None = None,
) -> str | None:
    """Normalize patient_class to canonical values.

    Canonical values: inpatient, outpatient, ed, observation.
    HL7 v2 PV1-2 patient class codes are mapped when present.
    """
    if event_type is not None:
        if event_type in _OBS_EVENT_TYPES:
            return "observation"
        if event_type in _ED_EVENT_TYPES:
            return "ed"

    if patient_class is None:
        return None

    raw = str(patient_class).strip()
    if not raw:
        return None

    normalized = raw.lower()

    # HL7 v2 PV1-2 codes and common synonyms
    if normalized in {"i", "ip", "inpatient"}:
        return "inpatient"
    if normalized in {"o", "op", "outpatient"}:
        return "outpatient"
    if normalized in {"e", "ed", "emergency"}:
        return "ed"
    if normalized in {"obs", "observation"}:
        return "observation"

    # Unknown or unsupported class
    return None
