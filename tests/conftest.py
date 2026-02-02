"""Shared test fixtures for ASRE test suite."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.models.encounter import Encounter


@pytest.fixture
def sample_canonical_event() -> CanonicalEvent:
    """A minimal valid CanonicalEvent for unit testing."""
    now = datetime.now(tz=timezone.utc)
    return CanonicalEvent(
        event_id="evt-001",
        patient_key="PAT-123",
        event_type="ADMIT",
        event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="SRC-001",
        facility_raw="St. Mary's Medical Center",
        ingested_at=now,
        batch_id="batch-001",
    )


@pytest.fixture
def sample_encounter() -> Encounter:
    """A minimal valid Encounter for unit testing."""
    now = datetime.now(tz=timezone.utc)
    return Encounter(
        encounter_id="enc-001",
        patient_key="PAT-123",
        encounter_type="inpatient",
        status="closed",
        admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        facility_canonical_id="FAC-001",
        facility_name="ST MARYS MEDICAL CENTER",
        is_acute=True,
        source_event_ids=["evt-001", "evt-002"],
        source_systems=["adt_vendor_x"],
        has_adt=True,
        has_claims=False,
        has_auth=False,
        confidence_score=0.50,
        confidence_flags=["HAS_ADT_ADMIT"],
        created_at=now,
        updated_at=now,
        asre_version="0.1.0",
        discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        los_hours=76.0,
    )


@pytest.fixture
def sample_event_batch(sample_canonical_event: CanonicalEvent) -> EventBatch:
    """An EventBatch with a few sample events for unit testing."""
    now = datetime.now(tz=timezone.utc)
    events = [
        sample_canonical_event,
        CanonicalEvent(
            event_id="evt-002",
            patient_key="PAT-123",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            source_record_id="SRC-002",
            facility_raw="St. Mary's Medical Center",
            ingested_at=now,
            batch_id="batch-001",
        ),
    ]
    return EventBatch(batch_id="batch-001", events=events)
