"""Tests for episode pipeline stages (US-095).

Tests for EpisodeStitchStage, EpisodeMaterializeStage, and EpisodeQualityStage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from asre.models.batch import EventBatch
from asre.models.encounter import Encounter
from asre.models.episode import Episode
from asre.pipeline.runner import PipelineContext, PipelineStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_encounter(
    *,
    encounter_id: str = "ENC_001",
    patient_key: str = "PAT_001",
    encounter_type: str = "inpatient",
    status: str = "closed",
    facility_canonical_id: str = "FAC_001",
    is_acute: bool = True,
    admit_ts: datetime | None = None,
    discharge_ts: datetime | None = None,
    los_hours: float | None = 48.0,
    confidence_score: float = 0.8,
    drg: str | None = None,
    principal_diagnosis: str | None = None,
    diagnosis_codes: list[dict[str, Any]] | None = None,
    episode_id: str | None = None,
) -> Encounter:
    now = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    return Encounter(
        encounter_id=encounter_id,
        patient_key=patient_key,
        encounter_type=encounter_type,
        status=status,
        admit_ts=admit_ts or datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        discharge_ts=discharge_ts or datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc),
        los_hours=los_hours,
        facility_canonical_id=facility_canonical_id,
        facility_name="Test Hospital",
        is_acute=is_acute,
        source_event_ids=["evt_001"],
        source_systems=["adt_vendor_x"],
        has_adt=True,
        has_claims=False,
        has_auth=False,
        confidence_score=confidence_score,
        confidence_flags=["HAS_ADT_ADMIT"],
        created_at=now,
        updated_at=now,
        asre_version="0.1.0",
        drg=drg,
        principal_diagnosis=principal_diagnosis,
        diagnosis_codes=diagnosis_codes,
        episode_id=episode_id,
    )


def _make_context(config: dict[str, Any] | None = None) -> PipelineContext:
    return PipelineContext(
        run_id="run_test_001",
        config=config or {},
        mode="full",
    )


# ===========================================================================
# EpisodeStitchStage tests
# ===========================================================================

class TestEpisodeStitchStage:
    """Tests for EpisodeStitchStage pipeline stage."""

    def test_is_pipeline_stage_subclass(self) -> None:
        from asre.episode.stage import EpisodeStitchStage
        assert issubclass(EpisodeStitchStage, PipelineStage)

    def test_has_run_method(self) -> None:
        from asre.episode.stage import EpisodeStitchStage
        stage = EpisodeStitchStage()
        assert hasattr(stage, "run") and callable(stage.run)

    def test_run_returns_event_batch(self) -> None:
        from asre.episode.stage import EpisodeStitchStage
        stage = EpisodeStitchStage()
        stage.encounters_in = [_make_encounter()]
        batch = EventBatch(batch_id="b1", events=[])
        result = stage.run(batch, _make_context())
        assert isinstance(result, EventBatch)

    def test_stitches_encounters_into_episodes(self) -> None:
        """Single patient with one encounter produces one episode."""
        from asre.episode.stage import EpisodeStitchStage
        enc = _make_encounter()
        stage = EpisodeStitchStage()
        stage.encounters_in = [enc]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert len(stage.episodes) == 1
        assert stage.episodes[0].patient_key == "PAT_001"

    def test_multiple_patients_produce_separate_episodes(self) -> None:
        """Different patients produce separate episodes."""
        from asre.episode.stage import EpisodeStitchStage
        enc1 = _make_encounter(patient_key="PAT_001", encounter_id="ENC_001")
        enc2 = _make_encounter(patient_key="PAT_002", encounter_id="ENC_002")
        stage = EpisodeStitchStage()
        stage.encounters_in = [enc1, enc2]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert len(stage.episodes) == 2

    def test_readmission_linked_into_same_episode(self) -> None:
        """Acute readmission within 30 days produces one episode with readmission flag."""
        from asre.episode.stage import EpisodeStitchStage
        enc1 = _make_encounter(
            encounter_id="ENC_001",
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
        )
        enc2 = _make_encounter(
            encounter_id="ENC_002",
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 18, 10, 0, tzinfo=timezone.utc),
        )
        stage = EpisodeStitchStage()
        stage.encounters_in = [enc1, enc2]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert len(stage.episodes) == 1
        assert stage.episodes[0].includes_readmission is True

    def test_records_stage_metrics(self) -> None:
        """Stage records metrics: records_in and records_out."""
        from asre.episode.stage import EpisodeStitchStage
        enc = _make_encounter()
        stage = EpisodeStitchStage()
        stage.encounters_in = [enc]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.metrics.records_in == 1
        assert stage.metrics.records_out == 1
        assert stage.metrics.status == "success"

    def test_empty_encounters_list(self) -> None:
        """Empty encounter list produces zero episodes."""
        from asre.episode.stage import EpisodeStitchStage
        stage = EpisodeStitchStage()
        stage.encounters_in = []
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.episodes == []
        assert stage.metrics.records_in == 0
        assert stage.metrics.records_out == 0

    def test_uses_episode_stitching_config(self) -> None:
        """Stage uses episode_stitching config for window parameters."""
        from asre.episode.stage import EpisodeStitchStage
        # Two acute encounters 45 days apart — default 30d window would NOT link
        enc1 = _make_encounter(
            encounter_id="ENC_001",
            admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
        )
        enc2 = _make_encounter(
            encounter_id="ENC_002",
            admit_ts=datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 2, 18, 10, 0, tzinfo=timezone.utc),
        )

        # With custom 60-day readmission window, should link
        config: dict[str, Any] = {
            "episode_stitching": {
                "readmission_window_days": 60,
            }
        }
        stage = EpisodeStitchStage()
        stage.encounters_in = [enc1, enc2]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context(config))

        assert len(stage.episodes) == 1


# ===========================================================================
# EpisodeMaterializeStage tests
# ===========================================================================

class TestEpisodeMaterializeStage:
    """Tests for EpisodeMaterializeStage pipeline stage."""

    def test_is_pipeline_stage_subclass(self) -> None:
        from asre.episode.stage import EpisodeMaterializeStage
        assert issubclass(EpisodeMaterializeStage, PipelineStage)

    def test_run_returns_event_batch(self) -> None:
        from asre.episode.stage import EpisodeMaterializeStage
        stage = EpisodeMaterializeStage()
        stage.episodes_in = []
        batch = EventBatch(batch_id="b1", events=[])
        result = stage.run(batch, _make_context())
        assert isinstance(result, EventBatch)

    def test_writes_episodes_to_table(self) -> None:
        """Stage writes episode records to asre_episodes table."""
        from asre.episode.stage import EpisodeMaterializeStage
        episode = Episode(
            episode_id="EP_001",
            patient_key="PAT_001",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            episode_end_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
            total_los_days=4.0,
            encounter_ids=["ENC_001"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.8,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        adapter = MagicMock()
        adapter.read_source.return_value = []  # no existing episodes
        adapter.write_records.return_value = 1

        stage = EpisodeMaterializeStage()
        stage.episodes_in = [episode]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context({"adapter": adapter}))

        # Should have called execute_ddl for table creation and write_records
        adapter.execute_ddl.assert_called()
        adapter.write_records.assert_called()
        # Verify table name
        write_call = adapter.write_records.call_args
        assert write_call[0][0] == "asre_episodes"

    def test_updates_episode_id_on_encounters(self) -> None:
        """Stage updates episode_id FK on encounters in admission_events_unified."""
        from asre.episode.stage import EpisodeMaterializeStage
        episode = Episode(
            episode_id="EP_001",
            patient_key="PAT_001",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            encounter_ids=["ENC_001", "ENC_002"],
            encounter_count=2,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.8,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        stage = EpisodeMaterializeStage()
        stage.episodes_in = [episode]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context({"adapter": adapter}))

        # Should have called execute_dml to update episode_id on encounters
        assert adapter.execute_dml.call_count == 2
        for call in adapter.execute_dml.call_args_list:
            statement = call[0][0]
            params = call[0][1]
            assert "UPDATE admission_events_unified" in statement
            assert "SET episode_id = :episode_id" in statement
            assert "WHERE encounter_id = :encounter_id" in statement
            assert params["episode_id"] == "EP_001"

    def test_no_adapter_skips_materialization(self) -> None:
        """Without adapter, stage skips writes gracefully."""
        from asre.episode.stage import EpisodeMaterializeStage
        stage = EpisodeMaterializeStage()
        stage.episodes_in = []
        batch = EventBatch(batch_id="b1", events=[])
        result = stage.run(batch, _make_context())
        assert isinstance(result, EventBatch)

    def test_records_stage_metrics(self) -> None:
        """Stage records metrics."""
        from asre.episode.stage import EpisodeMaterializeStage
        episode = Episode(
            episode_id="EP_001",
            patient_key="PAT_001",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            encounter_ids=["ENC_001"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.8,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        stage = EpisodeMaterializeStage()
        stage.episodes_in = [episode]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context({"adapter": adapter}))

        assert stage.metrics.records_in == 1
        assert stage.metrics.records_out == 1
        assert stage.metrics.status == "success"


# ===========================================================================
# EpisodeQualityStage tests
# ===========================================================================

class TestEpisodeQualityStage:
    """Tests for EpisodeQualityStage pipeline stage."""

    def test_is_pipeline_stage_subclass(self) -> None:
        from asre.episode.stage import EpisodeQualityStage
        assert issubclass(EpisodeQualityStage, PipelineStage)

    def test_run_returns_event_batch(self) -> None:
        from asre.episode.stage import EpisodeQualityStage
        stage = EpisodeQualityStage()
        stage.episodes_in = []
        batch = EventBatch(batch_id="b1", events=[])
        result = stage.run(batch, _make_context())
        assert isinstance(result, EventBatch)

    def test_computes_episode_count(self) -> None:
        """Stage tracks episode count."""
        from asre.episode.stage import EpisodeQualityStage
        episodes = [
            Episode(
                episode_id=f"EP_{i}",
                patient_key=f"PAT_{i}",
                episode_type="medical",
                episode_status="closed",
                episode_start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
                encounter_ids=[f"ENC_{i}"],
                encounter_count=1,
                facility_count=1,
                facility_sequence=["FAC_001"],
                is_acute=True,
                confidence_score=0.8,
                created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
                updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
                includes_readmission=False,
            )
            for i in range(3)
        ]

        stage = EpisodeQualityStage()
        stage.episodes_in = episodes
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.episode_count == 3

    def test_computes_readmission_rate(self) -> None:
        """Stage computes readmission rate as fraction of episodes with readmission."""
        from asre.episode.stage import EpisodeQualityStage
        ep1 = Episode(
            episode_id="EP_001",
            patient_key="PAT_001",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            encounter_ids=["ENC_001"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.8,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            includes_readmission=True,
        )
        ep2 = Episode(
            episode_id="EP_002",
            patient_key="PAT_002",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            encounter_ids=["ENC_002"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.8,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            includes_readmission=False,
        )

        stage = EpisodeQualityStage()
        stage.episodes_in = [ep1, ep2]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.readmission_rate == 0.5

    def test_computes_mean_confidence(self) -> None:
        """Stage computes mean episode confidence score."""
        from asre.episode.stage import EpisodeQualityStage
        ep1 = Episode(
            episode_id="EP_001",
            patient_key="PAT_001",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            encounter_ids=["ENC_001"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.8,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        ep2 = Episode(
            episode_id="EP_002",
            patient_key="PAT_002",
            episode_type="surgical",
            episode_status="closed",
            episode_start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            encounter_ids=["ENC_002"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.6,
            created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

        stage = EpisodeQualityStage()
        stage.episodes_in = [ep1, ep2]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.mean_confidence == 0.7

    def test_records_stage_metrics(self) -> None:
        """Stage records metrics."""
        from asre.episode.stage import EpisodeQualityStage
        stage = EpisodeQualityStage()
        stage.episodes_in = []
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.metrics.status == "success"
        assert stage.metrics.records_in == 0
        assert stage.metrics.records_out == 0

    def test_empty_episodes_produces_zero_metrics(self) -> None:
        """Empty episode list produces zero counts and rates."""
        from asre.episode.stage import EpisodeQualityStage
        stage = EpisodeQualityStage()
        stage.episodes_in = []
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.episode_count == 0
        assert stage.readmission_rate == 0.0
        assert stage.mean_confidence == 0.0
