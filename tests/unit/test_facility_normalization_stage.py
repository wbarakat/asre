"""Tests for FacilityNormalizationStage."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.facility.normalizer import FacilityNormalizer
from asre.facility.registry import FacilityRegistry
from asre.facility.stage import FacilityNormalizationStage
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext


def test_resolves_by_npi_from_event_fields() -> None:
    alias_config = FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="Test Hospital",
                npi="1234567890",
            )
        ]
    )
    normalizer = FacilityNormalizer()
    registry = FacilityRegistry(alias_config, normalizer)
    stage = FacilityNormalizationStage(
        normalizer=normalizer,
        alias_config=alias_config,
        registry=registry,
    )

    event = CanonicalEvent(
        event_id="evt_001",
        patient_key="P001",
        event_type="ADMIT",
        event_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="MSG-1",
        facility_raw="Unknown Facility",
        ingested_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        batch_id="batch_001",
        npi="1234567890",
    )

    stage._resolve_facility(event)

    assert event.facility_canonical_id == "FAC_001"
    assert event.facility_match_type == "npi"


def _make_event() -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt_001",
        patient_key="P001",
        event_type="ADMIT",
        event_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="MSG-1",
        facility_raw="Test Hospital",
        ingested_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        batch_id="batch_001",
    )


def test_persists_registry_when_adapter_present() -> None:
    alias_config = FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="Test Hospital",
            )
        ]
    )
    normalizer = FacilityNormalizer()
    registry = FacilityRegistry(alias_config, normalizer)
    stage = FacilityNormalizationStage(
        normalizer=normalizer,
        alias_config=alias_config,
        registry=registry,
    )

    adapter = MagicMock()
    adapter.write_records.return_value = 1
    context = PipelineContext(
        run_id="run_001",
        config={
            "adapter": adapter,
            "encounter_stitching": {"use_canonical_history": False},
        },
        mode="incremental",
    )

    batch = EventBatch(batch_id="batch_001", events=[_make_event()])

    with patch("asre.facility.stage.CanonicalEventStore"):
        stage.run(batch, context)

    adapter.write_records.assert_called()
    assert any(
        "asre_facility_registry" in str(call_args[0][0])
        for call_args in adapter.write_records.call_args_list
    )


def test_dry_run_skips_registry_persist() -> None:
    alias_config = FacilityAliasConfig(
        facilities=[
            FacilityAlias(
                canonical_id="FAC_001",
                canonical_name="Test Hospital",
            )
        ]
    )
    normalizer = FacilityNormalizer()
    registry = FacilityRegistry(alias_config, normalizer)
    stage = FacilityNormalizationStage(
        normalizer=normalizer,
        alias_config=alias_config,
        registry=registry,
    )

    adapter = MagicMock()
    adapter.write_records.return_value = 1
    context = PipelineContext(
        run_id="run_001",
        config={
            "adapter": adapter,
            "dry_run": True,
            "encounter_stitching": {"use_canonical_history": False},
        },
        mode="incremental",
    )

    batch = EventBatch(batch_id="batch_001", events=[_make_event()])

    with patch("asre.facility.stage.CanonicalEventStore"):
        stage.run(batch, context)

    adapter.write_records.assert_not_called()
