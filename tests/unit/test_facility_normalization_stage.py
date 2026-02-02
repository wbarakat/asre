"""Tests for FacilityNormalizationStage pipeline stage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.normalizer import FacilityNormalizer
from asre.facility.registry import FacilityRegistry
from asre.facility.stage import FacilityNormalizationStage
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext, PipelineStage


def _make_event(
    facility_raw: str = "St. Mary's Medical Center",
    patient_key: str = "PAT_001",
    event_id: str = "EVT_001",
    facility_canonical_id: str | None = None,
) -> CanonicalEvent:
    """Create a test CanonicalEvent with specified facility_raw."""
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type="ADMIT",
        event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="SRC_001",
        facility_raw=facility_raw,
        ingested_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        batch_id="BATCH_001",
        facility_canonical_id=facility_canonical_id,
    )


def _make_alias_config() -> FacilityAliasConfig:
    """Create a test FacilityAliasConfig with known facilities."""
    return FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="St. Mary's Medical Center",
                facility_type="acute",
                npi="1234567890",
                ccn="050001",
                aliases=["St Marys Med Ctr", "SAINT MARYS"],
            ),
            FacilityAlias(
                canonical_id="FAC_002",
                canonical_name="Memorial Regional Hospital",
                facility_type="acute",
                npi="0987654321",
                aliases=["Memorial Regional"],
            ),
            FacilityAlias(
                canonical_id="FAC_003",
                canonical_name="Good Samaritan Rehab Center",
                facility_type="rehab",
                aliases=[],
            ),
        ]
    )


def _make_context(run_id: str = "run_001") -> PipelineContext:
    """Create a test PipelineContext."""
    return PipelineContext(
        run_id=run_id,
        config={},
        mode="full",
    )


class TestFacilityNormalizationStageInterface:
    """Tests for PipelineStage interface compliance."""

    def test_implements_pipeline_stage(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        assert isinstance(stage, PipelineStage)

    def test_has_run_method(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        assert hasattr(stage, "run")
        assert callable(stage.run)

    def test_returns_event_batch(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        batch = EventBatch(batch_id="BATCH_001", events=[_make_event()])
        context = _make_context()
        result = stage.run(batch, context)
        assert isinstance(result, EventBatch)


class TestExactAliasMatching:
    """Tests for events matched via exact alias lookup."""

    def test_exact_alias_match_sets_canonical_id(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event = _make_event(facility_raw="St Marys Med Ctr")
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        result = stage.run(batch, _make_context())
        assert result.events[0].facility_canonical_id == "FAC_001"

    def test_canonical_name_match(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event = _make_event(facility_raw="Memorial Regional Hospital")
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        result = stage.run(batch, _make_context())
        assert result.events[0].facility_canonical_id == "FAC_002"


class TestFuzzyMatching:
    """Tests for events matched via fuzzy matching."""

    def test_fuzzy_match_sets_canonical_id(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        # Close but not exact match
        event = _make_event(facility_raw="SAINT MARYS EAST")
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        result = stage.run(batch, _make_context())
        # Should either fuzzy match to FAC_001 or create new
        assert result.events[0].facility_canonical_id is not None


class TestNewFacilityCreation:
    """Tests for events with unrecognized facility names."""

    def test_unknown_facility_creates_new_record(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event = _make_event(facility_raw="Totally Unknown Hospital XYZ123")
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        result = stage.run(batch, _make_context())
        assert result.events[0].facility_canonical_id is not None
        assert result.events[0].facility_canonical_id.startswith("FAC_")

    def test_unknown_facility_added_to_registry(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event = _make_event(facility_raw="Brand New Hospital 999")
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        result = stage.run(batch, _make_context())
        new_id = result.events[0].facility_canonical_id
        assert new_id is not None
        # Registry should have the new facility
        record = registry.get_facility(new_id)
        assert record is not None
        assert "FACILITY_NEW_UNREVIEWED" in record.flags

    def test_second_event_same_unknown_facility_reuses_id(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event1 = _make_event(facility_raw="New Place ABC", event_id="EVT_001")
        event2 = _make_event(facility_raw="New Place ABC", event_id="EVT_002")
        batch = EventBatch(batch_id="BATCH_001", events=[event1, event2])
        result = stage.run(batch, _make_context())
        assert result.events[0].facility_canonical_id == result.events[1].facility_canonical_id


class TestEmptyAndNullFacility:
    """Tests for events with empty or missing facility_raw."""

    def test_empty_facility_raw_leaves_canonical_id_none(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event = _make_event(facility_raw="")
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        result = stage.run(batch, _make_context())
        assert result.events[0].facility_canonical_id is None


class TestMixedBatch:
    """Tests for batch with various facility names."""

    def test_mixed_batch_assigns_correct_ids(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        events = [
            _make_event(facility_raw="St Marys Med Ctr", event_id="EVT_001"),
            _make_event(facility_raw="Memorial Regional Hospital", event_id="EVT_002"),
            _make_event(facility_raw="Unknown Place 42", event_id="EVT_003"),
            _make_event(facility_raw="", event_id="EVT_004"),
        ]
        batch = EventBatch(batch_id="BATCH_001", events=events)
        result = stage.run(batch, _make_context())
        assert result.events[0].facility_canonical_id == "FAC_001"
        assert result.events[1].facility_canonical_id == "FAC_002"
        assert result.events[2].facility_canonical_id is not None  # new facility
        assert result.events[3].facility_canonical_id is None  # empty


class TestStageMetrics:
    """Tests for stage metrics tracking."""

    def test_metrics_track_match_types(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        events = [
            _make_event(facility_raw="St Marys Med Ctr", event_id="EVT_001"),  # exact
            _make_event(facility_raw="Unknown Place XYZ", event_id="EVT_002"),  # new
        ]
        batch = EventBatch(batch_id="BATCH_001", events=events)
        stage.run(batch, _make_context())
        metrics_dict = stage.metrics.to_dict()
        assert metrics_dict["records_in"] == 2
        assert metrics_dict["records_out"] == 2

    def test_metrics_errors_for_unresolvable(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        events = [
            _make_event(facility_raw="", event_id="EVT_001"),  # empty - unresolvable
        ]
        batch = EventBatch(batch_id="BATCH_001", events=events)
        stage.run(batch, _make_context())
        # Empty facility_raw is not an error, just unresolvable
        assert stage.metrics.errors == 0

    def test_metrics_stage_name(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        events = [_make_event()]
        batch = EventBatch(batch_id="BATCH_001", events=events)
        stage.run(batch, _make_context())
        assert stage.metrics.to_dict()["stage_name"] == "facility_normalize"


class TestRegistryUpdates:
    """Tests for facility registry updates after stage run."""

    def test_registry_updated_with_new_facilities(self) -> None:
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        initial_count = len(registry.get_all_facilities())

        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        events = [
            _make_event(facility_raw="Oceanview Psychiatric Institute", event_id="EVT_001"),
            _make_event(facility_raw="Riverbend Orthopedic Specialists", event_id="EVT_002"),
        ]
        batch = EventBatch(batch_id="BATCH_001", events=events)
        stage.run(batch, _make_context())

        # Registry should have 2 more facilities (distinct names, no fuzzy overlap)
        assert len(registry.get_all_facilities()) == initial_count + 2

    def test_original_events_not_mutated_beyond_canonical_id(self) -> None:
        """Verify stage only sets facility_canonical_id on events."""
        normalizer = FacilityNormalizer()
        alias_config = _make_alias_config()
        registry = FacilityRegistry(alias_config, normalizer)
        stage = FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
        )
        event = _make_event(facility_raw="St Marys Med Ctr")
        original_raw = event.facility_raw
        batch = EventBatch(batch_id="BATCH_001", events=[event])
        stage.run(batch, _make_context())
        # facility_raw should remain unchanged
        assert event.facility_raw == original_raw
