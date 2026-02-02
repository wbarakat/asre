"""Tests that verify shared conftest fixtures are available and correctly typed."""

from __future__ import annotations

from datetime import datetime

import pytest

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.models.encounter import Encounter


class TestSampleCanonicalEventFixture:
    """Verify the sample_canonical_event fixture."""

    def test_fixture_exists(self, sample_canonical_event: CanonicalEvent) -> None:
        assert isinstance(sample_canonical_event, CanonicalEvent)

    def test_required_fields_populated(self, sample_canonical_event: CanonicalEvent) -> None:
        assert sample_canonical_event.event_id
        assert sample_canonical_event.patient_key
        assert sample_canonical_event.event_type
        assert isinstance(sample_canonical_event.event_ts, datetime)
        assert sample_canonical_event.source_system
        assert sample_canonical_event.source_record_id
        assert sample_canonical_event.facility_raw
        assert isinstance(sample_canonical_event.ingested_at, datetime)
        assert sample_canonical_event.batch_id


class TestSampleEncounterFixture:
    """Verify the sample_encounter fixture."""

    def test_fixture_exists(self, sample_encounter: Encounter) -> None:
        assert isinstance(sample_encounter, Encounter)

    def test_required_fields_populated(self, sample_encounter: Encounter) -> None:
        assert sample_encounter.encounter_id
        assert sample_encounter.patient_key
        assert sample_encounter.encounter_type
        assert sample_encounter.status
        assert isinstance(sample_encounter.admit_ts, datetime)
        assert sample_encounter.facility_canonical_id
        assert sample_encounter.facility_name
        assert isinstance(sample_encounter.is_acute, bool)
        assert isinstance(sample_encounter.source_event_ids, list)
        assert isinstance(sample_encounter.source_systems, list)
        assert isinstance(sample_encounter.confidence_score, float)
        assert isinstance(sample_encounter.confidence_flags, list)
        assert isinstance(sample_encounter.created_at, datetime)
        assert isinstance(sample_encounter.updated_at, datetime)
        assert sample_encounter.asre_version


class TestSampleEventBatchFixture:
    """Verify the sample_event_batch fixture."""

    def test_fixture_exists(self, sample_event_batch: EventBatch) -> None:
        assert isinstance(sample_event_batch, EventBatch)

    def test_has_events(self, sample_event_batch: EventBatch) -> None:
        assert len(sample_event_batch.events) > 0

    def test_events_are_canonical(self, sample_event_batch: EventBatch) -> None:
        for event in sample_event_batch.events:
            assert isinstance(event, CanonicalEvent)

    def test_batch_id_populated(self, sample_event_batch: EventBatch) -> None:
        assert sample_event_batch.batch_id


class TestSyrupyConfigured:
    """Verify pytest-syrupy snapshot testing is configured."""

    def test_snapshot_extension_available(self, snapshot: object) -> None:
        # syrupy provides the 'snapshot' fixture automatically
        assert snapshot is not None
