"""Tests for BYOFID (Bring Your Own Facility ID) feature.

When a source config maps facility_canonical_id, customer-provided facility IDs
bypass ASRE's facility normalization cascade and flow through the pipeline untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from asre.canonicalize.mapper import FieldMapper
from asre.canonicalize.paired_event_emitter import PairedEventEmitter
from asre.config.source_schema import (
    FieldMappings,
    PairedEventConfig,
    PairedEvents,
)
from asre.facility.stage import FacilityNormalizationStage
from asre.materialize.stage import encounter_to_record
from asre.models.canonical_event import CanonicalEvent
from asre.reconcile.stage import ReconciledEncounter
from asre.stitch.encounter_stitcher import StitchedEncounter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(**overrides: Any) -> CanonicalEvent:
    """Build a minimal CanonicalEvent with sensible defaults."""
    defaults: dict[str, Any] = {
        "event_id": "evt-001",
        "patient_key": "PAT-001",
        "event_type": "ADMIT",
        "event_ts": datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        "source_system": "adt_vendor_x",
        "source_record_id": "REC-001",
        "facility_raw": "General Hospital",
        "ingested_at": datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        "batch_id": "batch_001",
    }
    defaults.update(overrides)
    return CanonicalEvent(**defaults)


def _make_reconciled_encounter(
    events: list[CanonicalEvent],
    facility_canonical_id: str = "FAC-001",
) -> ReconciledEncounter:
    """Build a minimal ReconciledEncounter for materialization tests."""
    stitched = StitchedEncounter(
        patient_key="PAT-001",
        facility_canonical_id=facility_canonical_id,
        events=events,
        encounter_type="inpatient",
        status="closed",
        encounter_id="ENC-001",
    )
    enc = ReconciledEncounter(stitched)
    enc.confidence_score = 0.85
    enc.confidence_flags = []
    return enc


# ===========================================================================
# 1. FieldMappings schema
# ===========================================================================

class TestFieldMappingsByofid:
    def test_field_mappings_accepts_facility_canonical_id(self) -> None:
        fm = FieldMappings(
            patient_key="mrn",
            event_ts="ts",
            source_record_id="rid",
            facility_canonical_id="site_id",
        )
        assert fm.facility_canonical_id == "site_id"

    def test_field_mappings_defaults_none(self) -> None:
        fm = FieldMappings(
            patient_key="mrn",
            event_ts="ts",
            source_record_id="rid",
        )
        assert fm.facility_canonical_id is None
        assert fm.facility_name is None


# ===========================================================================
# 2. FieldMapper
# ===========================================================================

class TestFieldMapperByofid:
    def test_mapper_sets_canonical_id_and_match_type(self) -> None:
        fm = FieldMappings(
            patient_key="mrn",
            event_ts="ts",
            source_record_id="rid",
            facility_canonical_id="site_id",
        )
        mapper = FieldMapper(fm)
        record = {
            "mrn": "PAT-001",
            "ts": "2024-01-15T10:00:00",
            "rid": "REC-001",
            "site_id": "FAC-CUSTOMER-001",
        }

        event = mapper.map_record(record, "adt_x", "batch_001")

        assert event.facility_canonical_id == "FAC-CUSTOMER-001"
        assert event.facility_match_type == "customer_provided"

    def test_mapper_sets_facility_name(self) -> None:
        fm = FieldMappings(
            patient_key="mrn",
            event_ts="ts",
            source_record_id="rid",
            facility_canonical_id="site_id",
            facility_name="site_name",
        )
        mapper = FieldMapper(fm)
        record = {
            "mrn": "PAT-001",
            "ts": "2024-01-15T10:00:00",
            "rid": "REC-001",
            "site_id": "FAC-CUSTOMER-001",
            "site_name": "Downtown Medical Center",
        }

        event = mapper.map_record(record, "adt_x", "batch_001")

        assert event.facility_name == "Downtown Medical Center"

    def test_mapper_without_byofid_leaves_none(self) -> None:
        fm = FieldMappings(
            patient_key="mrn",
            event_ts="ts",
            source_record_id="rid",
        )
        mapper = FieldMapper(fm)
        record = {
            "mrn": "PAT-001",
            "ts": "2024-01-15T10:00:00",
            "rid": "REC-001",
        }

        event = mapper.map_record(record, "adt_x", "batch_001")

        assert event.facility_canonical_id is None
        assert event.facility_match_type is None
        assert event.facility_name is None


# ===========================================================================
# 3. PairedEventEmitter
# ===========================================================================

class TestPairedEmitterByofid:
    def _make_emitter(self, **fm_overrides: Any) -> PairedEventEmitter:
        fm_defaults: dict[str, Any] = {
            "patient_key": "member_id",
            "event_ts": "admit_date",
            "source_record_id": "claim_id",
            "facility_raw": "fac_name",
        }
        fm_defaults.update(fm_overrides)
        fm = FieldMappings(**fm_defaults)
        pe = PairedEvents(
            admit=PairedEventConfig(event_ts="admit_date", event_type="CLAIM_ADMIT"),
            discharge=PairedEventConfig(event_ts="discharge_date", event_type="CLAIM_DISCHARGE"),
        )
        return PairedEventEmitter(field_mappings=fm, paired_events=pe)

    def test_paired_emitter_sets_byofid_on_both_events(self) -> None:
        emitter = self._make_emitter(
            facility_canonical_id="site_id",
            facility_name="site_name",
        )
        record = {
            "member_id": "PAT-001",
            "admit_date": "2024-01-15T10:00:00",
            "discharge_date": "2024-01-18T14:00:00",
            "claim_id": "CLM-001",
            "fac_name": "General Hospital",
            "site_id": "FAC-CUST-001",
            "site_name": "General Hospital Downtown",
        }

        events = emitter.emit(record, "claims_x", "batch_001")

        assert len(events) == 2
        for event in events:
            assert event.facility_canonical_id == "FAC-CUST-001"
            assert event.facility_match_type == "customer_provided"
            assert event.facility_name == "General Hospital Downtown"

    def test_paired_emitter_without_byofid(self) -> None:
        emitter = self._make_emitter()
        record = {
            "member_id": "PAT-001",
            "admit_date": "2024-01-15T10:00:00",
            "discharge_date": "2024-01-18T14:00:00",
            "claim_id": "CLM-001",
            "fac_name": "General Hospital",
        }

        events = emitter.emit(record, "claims_x", "batch_001")

        for event in events:
            assert event.facility_canonical_id is None
            assert event.facility_match_type is None
            assert event.facility_name is None


# ===========================================================================
# 4. FacilityNormalizationStage bypass
# ===========================================================================

class TestFacilityStageByofid:
    def _make_stage(self) -> FacilityNormalizationStage:
        normalizer = MagicMock()
        alias_config = MagicMock()
        registry = MagicMock()
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        # Replace the real matcher with a mock for assertions
        stage._matcher = MagicMock()
        return stage

    def test_customer_provided_skips_normalization(self) -> None:
        stage = self._make_stage()
        event = _make_event(
            facility_canonical_id="FAC-CUST-001",
            facility_match_type="customer_provided",
        )

        stage._resolve_facility(event)

        # Should not have been overwritten by the normalization cascade
        assert event.facility_canonical_id == "FAC-CUST-001"
        assert event.facility_match_type == "customer_provided"
        # Matcher should never have been called
        stage._matcher.resolve_or_create.assert_not_called()

    def test_customer_provided_preserves_original_values(self) -> None:
        stage = self._make_stage()
        event = _make_event(
            facility_canonical_id="MY-SITE-42",
            facility_match_type="customer_provided",
            facility_name="My Custom Facility",
        )

        stage._resolve_facility(event)

        assert event.facility_canonical_id == "MY-SITE-42"
        assert event.facility_match_type == "customer_provided"
        assert event.facility_name == "My Custom Facility"

    def test_mixed_batch_normalizes_only_unmapped(self) -> None:
        stage = self._make_stage()
        # Mock matcher to return a result for non-BYOFID events
        stage._matcher.resolve_or_create.return_value = MagicMock(
            canonical_id="FAC-RESOLVED",
            match_type="exact",
            score=1.0,
            flags=[],
        )

        byofid_event = _make_event(
            event_id="evt-byofid",
            facility_canonical_id="FAC-CUST-001",
            facility_match_type="customer_provided",
        )
        raw_event = _make_event(
            event_id="evt-raw",
            facility_raw="Some Hospital",
            facility_canonical_id=None,
            facility_match_type=None,
        )

        stage._resolve_facility(byofid_event)
        stage._resolve_facility(raw_event)

        # BYOFID event untouched
        assert byofid_event.facility_canonical_id == "FAC-CUST-001"
        assert byofid_event.facility_match_type == "customer_provided"
        # Raw event went through normalization
        assert raw_event.facility_canonical_id == "FAC-RESOLVED"
        assert raw_event.facility_match_type == "exact"
        # Matcher called only once (for the raw event)
        assert stage._matcher.resolve_or_create.call_count == 1


# ===========================================================================
# 5. Materialization
# ===========================================================================

class TestMaterializeByofid:
    def test_materialize_uses_customer_facility_name(self) -> None:
        event = _make_event(
            facility_canonical_id="FAC-CUST-001",
            facility_match_type="customer_provided",
            facility_name="Downtown Medical Center",
        )
        enc = _make_reconciled_encounter([event], facility_canonical_id="FAC-CUST-001")
        now = datetime(2024, 1, 20, 12, 0, tzinfo=timezone.utc)

        record = encounter_to_record(enc, now, "run-001")

        assert record["facility_name"] == "Downtown Medical Center"

    def test_materialize_falls_back_to_canonical_id(self) -> None:
        event = _make_event(
            facility_canonical_id="FAC-CUST-001",
            facility_match_type="customer_provided",
            # No facility_name set
        )
        enc = _make_reconciled_encounter([event], facility_canonical_id="FAC-CUST-001")
        now = datetime(2024, 1, 20, 12, 0, tzinfo=timezone.utc)

        record = encounter_to_record(enc, now, "run-001")

        assert record["facility_name"] == "FAC-CUST-001"
