"""Tests for ReadmissionDetector (US-074).

Verifies:
- Acute discharge Jan 1, acute admit Jan 15 -> is_readmission=true, readmission_days=14
- Acute discharge Jan 1, SNF admit Jan 5 -> is_readmission=false (SNF not acute)
- Acute discharge Jan 1, acute admit Feb 15 -> is_readmission=false (>30 days)
- First admission is never a readmission
- readmission_days only populated when is_readmission=true
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from asre.models.canonical_event import CanonicalEvent
from asre.readmission.detector import ReadmissionDetector
from asre.reconcile.reconciler import (
    ReconciledClassification,
    ReconciledTimestamps,
)
from asre.reconcile.stage import ReconciledEncounter
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    event_id: str = "evt-001",
    patient_key: str = "PAT-001",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "SRC-001",
    facility_raw: str = "St Marys",
    facility_canonical_id: str | None = "FAC-001",
) -> CanonicalEvent:
    now = datetime.now(tz=timezone.utc)
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw=facility_raw,
        ingested_at=now,
        batch_id="batch-001",
        facility_canonical_id=facility_canonical_id,
    )


def _make_reconciled_encounter(
    patient_key: str = "PAT-001",
    facility_canonical_id: str = "FAC-001",
    encounter_id: str = "enc-001",
    encounter_type: str = "inpatient",
    status: str = "closed",
    has_discharge: bool = True,
    admit_ts: datetime | None = None,
    discharge_ts: datetime | None = None,
    events: list[CanonicalEvent] | None = None,
) -> ReconciledEncounter:
    """Create a ReconciledEncounter with reconciled timestamps for testing."""
    if admit_ts is None:
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    if events is None:
        events = [
            _make_event(
                event_id=f"{encounter_id}-admit",
                patient_key=patient_key,
                event_type="ADMIT",
                event_ts=admit_ts,
                facility_canonical_id=facility_canonical_id,
            ),
        ]
        if has_discharge and discharge_ts is not None:
            events.append(
                _make_event(
                    event_id=f"{encounter_id}-discharge",
                    patient_key=patient_key,
                    event_type="DISCHARGE",
                    event_ts=discharge_ts,
                    facility_canonical_id=facility_canonical_id,
                )
            )

    stitched = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
        events=events,
        encounter_type=encounter_type,
        status=status,
        has_discharge=has_discharge,
        encounter_id=encounter_id,
    )
    rec = ReconciledEncounter(stitched)
    rec.reconciled_timestamps = ReconciledTimestamps(
        admit_ts=admit_ts,
        admit_source_priority="adt",
        discharge_ts=discharge_ts,
        discharge_source_priority="adt" if discharge_ts else None,
    )
    rec.reconciled_classification = ReconciledClassification(
        encounter_type=encounter_type,
    )
    rec.confidence_flags = []
    rec.confidence_score = 0.8  # type: ignore[attr-defined]
    return rec


class TestReadmissionDetector:
    """Tests for ReadmissionDetector."""

    def test_acute_readmission_within_30_days(self) -> None:
        """Acute discharge Jan 1, acute admit Jan 15 -> is_readmission=true, readmission_days=14."""
        # First encounter: acute, discharged Jan 1
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-001",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2023, 12, 25, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        )

        # Second encounter: acute, admitted Jan 15
        enc2 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-002",
            encounter_id="enc-002",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc),
        )

        # Both facilities are acute
        facility_type_map = {"FAC-001": "acute", "FAC-002": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1, enc2])

        assert enc1.is_readmission is False
        assert enc1.readmission_days is None
        assert enc2.is_readmission is True
        assert enc2.readmission_days == 14

    def test_snf_admit_not_readmission(self) -> None:
        """Acute discharge Jan 1, SNF admit Jan 5 -> is_readmission=false (SNF not acute)."""
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-001",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2023, 12, 25, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        )

        enc2 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-SNF",
            encounter_id="enc-002",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc),
        )

        # FAC-001 is acute, FAC-SNF is snf (not acute)
        facility_type_map = {"FAC-001": "acute", "FAC-SNF": "snf"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1, enc2])

        assert enc2.is_readmission is False
        assert enc2.readmission_days is None

    def test_readmission_beyond_30_days(self) -> None:
        """Acute discharge Jan 1, acute admit Feb 15 -> is_readmission=false (>30 days)."""
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-001",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2023, 12, 25, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        )

        enc2 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-002",
            encounter_id="enc-002",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 2, 20, 10, 0, tzinfo=timezone.utc),
        )

        facility_type_map = {"FAC-001": "acute", "FAC-002": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1, enc2])

        assert enc2.is_readmission is False
        assert enc2.readmission_days is None

    def test_first_admission_never_readmission(self) -> None:
        """First admission for a patient is never a readmission."""
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-001",
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
        )

        facility_type_map = {"FAC-001": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1])

        assert enc1.is_readmission is False
        assert enc1.readmission_days is None

    def test_readmission_days_only_when_readmission(self) -> None:
        """readmission_days is only populated when is_readmission=true."""
        # Three encounters: first not readmission, second is, third is not (>30 days gap)
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-001",
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
        )
        enc2 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-002",
            admit_ts=datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 25, 10, 0, tzinfo=timezone.utc),
        )
        enc3 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-003",
            admit_ts=datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 3, 20, 10, 0, tzinfo=timezone.utc),
        )

        facility_type_map = {"FAC-001": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1, enc2, enc3])

        assert enc1.is_readmission is False
        assert enc1.readmission_days is None
        assert enc2.is_readmission is True
        assert enc2.readmission_days == 15
        assert enc3.is_readmission is False
        assert enc3.readmission_days is None

    def test_different_patients_independent(self) -> None:
        """Readmission detection is per-patient; different patients don't affect each other."""
        enc_a = _make_reconciled_encounter(
            patient_key="PAT-A",
            facility_canonical_id="FAC-001",
            encounter_id="enc-a1",
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
        )
        enc_b = _make_reconciled_encounter(
            patient_key="PAT-B",
            facility_canonical_id="FAC-001",
            encounter_id="enc-b1",
            admit_ts=datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        )

        facility_type_map = {"FAC-001": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc_a, enc_b])

        assert enc_a.is_readmission is False
        assert enc_b.is_readmission is False

    def test_prior_discharge_from_non_acute_doesnt_trigger_readmission(self) -> None:
        """Only acute-to-acute counts. SNF discharge -> acute admit is not readmission."""
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-SNF",
            encounter_id="enc-001",
            encounter_type="inpatient",
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc),
        )
        enc2 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-002",
            encounter_type="inpatient",
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc),
        )

        facility_type_map = {"FAC-SNF": "snf", "FAC-001": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1, enc2])

        assert enc2.is_readmission is False

    def test_open_encounter_no_discharge_not_prior(self) -> None:
        """An open encounter (no discharge) cannot serve as a prior discharge for readmission."""
        enc1 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-001",
            encounter_type="inpatient",
            status="open",
            has_discharge=False,
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=None,
        )
        enc2 = _make_reconciled_encounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            encounter_id="enc-002",
            encounter_type="inpatient",
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc),
        )

        facility_type_map = {"FAC-001": "acute"}
        detector = ReadmissionDetector(facility_type_map=facility_type_map)
        detector.detect([enc1, enc2])

        assert enc2.is_readmission is False
