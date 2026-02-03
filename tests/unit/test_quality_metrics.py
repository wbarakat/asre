"""Tests for QualityMetricComputer (US-081).

Tests the quality metric computation class that computes all 11 metrics
from SPEC section 8.2 after each pipeline run. Metrics are computed from
scored encounters and stage metrics, then written to asre_quality_metrics table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from asre.models.canonical_event import CanonicalEvent
from asre.reconcile.stage import ReconciledEncounter
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    *,
    event_type: str = "ADMIT",
    source_system: str = "adt_vendor_x",
    patient_key: str = "PAT_001",
    facility_canonical_id: str | None = "FAC_001",
    event_ts: datetime | None = None,
    event_id: str = "evt_001",
    source_record_id: str = "src_001",
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts or datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw="Test Hospital",
        facility_canonical_id=facility_canonical_id,
        admit_flag=(event_type in ("ADMIT", "CLAIM_ADMIT")),
        discharge_flag=(event_type in ("DISCHARGE", "CLAIM_DISCHARGE")),
        auth_flag=False,
        patient_class=None,
        drg=None,
        principal_diagnosis=None,
        diagnosis_codes=None,
        auth_status=None,
        payer_id=None,
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        batch_id="batch_001",
        _raw_payload={},
    )


def _make_encounter(
    events: list[CanonicalEvent],
    *,
    patient_key: str = "PAT_001",
    facility_canonical_id: str | None = "FAC_001",
    has_discharge: bool = False,
    status: str = "open",
) -> StitchedEncounter:
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
        events=events,
        last_event_ts=events[-1].event_ts if events else None,
        encounter_type="inpatient",
    )
    enc.has_discharge = has_discharge
    enc.status = status
    return enc


def _make_reconciled(
    encounter: StitchedEncounter,
    flags: list[str] | None = None,
    confidence_score: float = 0.5,
) -> ReconciledEncounter:
    rec = ReconciledEncounter(encounter)
    rec.confidence_flags = flags or []
    rec.confidence_score = confidence_score  # type: ignore[attr-defined]
    return rec


class TestQualityMetricComputerImport:
    """Test that QualityMetricComputer is importable from asre.quality.metrics."""

    def test_import(self) -> None:
        from asre.quality.metrics import QualityMetricComputer

        assert QualityMetricComputer is not None


class TestQualityMetricComputerCompute:
    """Test that QualityMetricComputer.compute() returns correct metric values."""

    def test_all_11_metrics_returned(self) -> None:
        """All 11 metrics from SPEC 8.2 are computed and returned."""
        from asre.quality.metrics import QualityMetricComputer

        # 10 encounters, no issues
        encounters = []
        for i in range(10):
            admit = _make_event(
                event_id=f"evt_admit_{i}",
                source_system="adt_vendor_x",
                patient_key=f"PAT_{i:03d}",
            )
            discharge = _make_event(
                event_type="DISCHARGE",
                event_id=f"evt_disch_{i}",
                source_system="adt_vendor_x",
                patient_key=f"PAT_{i:03d}",
            )
            enc = _make_encounter(
                [admit, discharge],
                patient_key=f"PAT_{i:03d}",
                has_discharge=True,
                status="closed",
            )
            encounters.append(_make_reconciled(enc, confidence_score=0.9))

        stage_metrics: list[dict[str, Any]] = [
            {"stage_name": "ingest", "records_in": 20, "records_out": 20, "errors": 0},
        ]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=stage_metrics,
            events_ingested=20,
            encounters_created=10,
            encounters_updated=0,
        )

        expected_keys = {
            "duplicate_rate",
            "missing_discharge_rate",
            "reconciliation_mismatch_rate",
            "low_confidence_rate",
            "facility_unresolved_rate",
            "auth_without_admit_rate",
            "claims_only_rate",
            "avg_confidence_score",
            "events_ingested",
            "encounters_created",
            "encounters_updated",
            "failed_event_rate",
        }
        assert set(metrics.keys()) == expected_keys

    def test_duplicate_rate(self) -> None:
        """duplicate_rate = encounters with DUPLICATE_DETECTED / total encounters."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        # 8 normal encounters
        for i in range(8):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            encounters.append(_make_reconciled(enc, confidence_score=0.8))

        # 2 encounters with DUPLICATE_DETECTED flag
        for i in range(8, 10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            encounters.append(
                _make_reconciled(enc, flags=["DUPLICATE_DETECTED"], confidence_score=0.7)
            )

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["duplicate_rate"] == pytest.approx(0.2)

    def test_missing_discharge_rate(self) -> None:
        """missing_discharge_rate = encounters with MISSING_DISCHARGE / total."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        # 7 closed encounters
        for i in range(7):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
                has_discharge=True,
                status="closed",
            )
            encounters.append(_make_reconciled(enc, confidence_score=0.9))

        # 3 encounters with MISSING_DISCHARGE
        for i in range(7, 10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            encounters.append(
                _make_reconciled(
                    enc, flags=["MISSING_DISCHARGE"], confidence_score=0.5
                )
            )

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["missing_discharge_rate"] == pytest.approx(0.3)

    def test_reconciliation_mismatch_rate(self) -> None:
        """reconciliation_mismatch_rate = encounters with TIMESTAMP_MISMATCH / total."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        for i in range(10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            flags = ["TIMESTAMP_MISMATCH"] if i < 2 else []
            encounters.append(_make_reconciled(enc, flags=flags, confidence_score=0.8))

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["reconciliation_mismatch_rate"] == pytest.approx(0.2)

    def test_low_confidence_rate(self) -> None:
        """low_confidence_rate = encounters with score < 0.60 / total."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        # 6 high-confidence encounters
        for i in range(6):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            encounters.append(_make_reconciled(enc, confidence_score=0.85))

        # 4 low-confidence encounters (score < 0.60)
        for i in range(6, 10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            encounters.append(_make_reconciled(enc, confidence_score=0.40))

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["low_confidence_rate"] == pytest.approx(0.4)

    def test_facility_unresolved_rate(self) -> None:
        """facility_unresolved_rate = encounters with FACILITY_UNRESOLVED / total."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        for i in range(10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            flags = ["FACILITY_UNRESOLVED"] if i < 1 else []
            encounters.append(_make_reconciled(enc, flags=flags, confidence_score=0.7))

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["facility_unresolved_rate"] == pytest.approx(0.1)

    def test_auth_without_admit_rate(self) -> None:
        """auth_without_admit_rate = encounters with AUTH_WITHOUT_ADMIT / total."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        for i in range(10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            flags = ["AUTH_WITHOUT_ADMIT"] if i < 3 else []
            encounters.append(_make_reconciled(enc, flags=flags, confidence_score=0.7))

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["auth_without_admit_rate"] == pytest.approx(0.3)

    def test_claims_only_rate(self) -> None:
        """claims_only_rate = encounters with CLAIMS_ONLY_ENCOUNTER / total."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        for i in range(10):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            flags = ["CLAIMS_ONLY_ENCOUNTER"] if i < 5 else []
            encounters.append(_make_reconciled(enc, flags=flags, confidence_score=0.6))

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=10,
            encounters_updated=0,
        )

        assert metrics["claims_only_rate"] == pytest.approx(0.5)

    def test_avg_confidence_score(self) -> None:
        """avg_confidence_score = mean of all encounter confidence scores."""
        from asre.quality.metrics import QualityMetricComputer

        encounters = []
        scores = [0.9, 0.8, 0.7, 0.6]
        for i, score in enumerate(scores):
            enc = _make_encounter(
                [_make_event(event_id=f"e_{i}", patient_key=f"P_{i}")],
                patient_key=f"P_{i}",
            )
            encounters.append(_make_reconciled(enc, confidence_score=score))

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=4,
            encounters_created=4,
            encounters_updated=0,
        )

        # Mean of [0.9, 0.8, 0.7, 0.6] = 0.75
        assert metrics["avg_confidence_score"] == pytest.approx(0.75)

    def test_events_ingested_count(self) -> None:
        """events_ingested is passed through directly."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter([_make_event()])
        encounters = [_make_reconciled(enc, confidence_score=0.8)]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=500,
            encounters_created=1,
            encounters_updated=0,
        )

        assert metrics["events_ingested"] == 500

    def test_encounters_created_and_updated(self) -> None:
        """encounters_created and encounters_updated are passed through."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter([_make_event()])
        encounters = [_make_reconciled(enc, confidence_score=0.8)]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=10,
            encounters_created=7,
            encounters_updated=3,
        )

        assert metrics["encounters_created"] == 7
        assert metrics["encounters_updated"] == 3

    def test_failed_event_rate(self) -> None:
        """failed_event_rate = total errors / total records_in across stages."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter([_make_event()])
        encounters = [_make_reconciled(enc, confidence_score=0.8)]

        stage_metrics: list[dict[str, Any]] = [
            {"stage_name": "ingest", "records_in": 100, "records_out": 98, "errors": 2},
            {"stage_name": "canonicalize", "records_in": 98, "records_out": 95, "errors": 3},
        ]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=stage_metrics,
            events_ingested=100,
            encounters_created=1,
            encounters_updated=0,
        )

        # 5 errors / 198 total records_in = 0.02525...
        assert metrics["failed_event_rate"] == pytest.approx(5 / 198)

    def test_zero_encounters_returns_zero_rates(self) -> None:
        """With no encounters, all rates should be 0."""
        from asre.quality.metrics import QualityMetricComputer

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=[],
            stage_metrics=[],
            events_ingested=0,
            encounters_created=0,
            encounters_updated=0,
        )

        assert metrics["duplicate_rate"] == 0.0
        assert metrics["missing_discharge_rate"] == 0.0
        assert metrics["low_confidence_rate"] == 0.0
        assert metrics["avg_confidence_score"] == 0.0
        assert metrics["failed_event_rate"] == 0.0

    def test_multiple_flags_on_single_encounter(self) -> None:
        """An encounter can have multiple flags; each metric counts independently."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter(
            [_make_event()],
        )
        encounters = [
            _make_reconciled(
                enc,
                flags=["DUPLICATE_DETECTED", "MISSING_DISCHARGE", "TIMESTAMP_MISMATCH"],
                confidence_score=0.4,
            )
        ]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=1,
            encounters_created=1,
            encounters_updated=0,
        )

        assert metrics["duplicate_rate"] == pytest.approx(1.0)
        assert metrics["missing_discharge_rate"] == pytest.approx(1.0)
        assert metrics["reconciliation_mismatch_rate"] == pytest.approx(1.0)
        assert metrics["low_confidence_rate"] == pytest.approx(1.0)


class TestQualityMetricComputerToRecords:
    """Test that metrics can be converted to records for asre_quality_metrics table."""

    def test_to_records_returns_list_of_dicts(self) -> None:
        """to_records() converts metrics dict into list of row dicts for DB."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter([_make_event()])
        encounters = [_make_reconciled(enc, confidence_score=0.8)]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=1,
            encounters_created=1,
            encounters_updated=0,
        )

        records = computer.to_records(
            metrics=metrics,
            run_id="run_20240101_120000",
        )

        assert isinstance(records, list)
        # 12 metrics = 12 records
        assert len(records) == 12

        # Each record has expected fields
        for record in records:
            assert "run_id" in record
            assert "metric_name" in record
            assert "metric_value" in record
            assert record["run_id"] == "run_20240101_120000"

    def test_to_records_metric_names_match(self) -> None:
        """All metric names in records match the compute output keys."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter([_make_event()])
        encounters = [_make_reconciled(enc, confidence_score=0.8)]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=1,
            encounters_created=1,
            encounters_updated=0,
        )

        records = computer.to_records(
            metrics=metrics,
            run_id="run_20240101_120000",
        )

        record_names = {r["metric_name"] for r in records}
        assert record_names == set(metrics.keys())

    def test_to_records_values_match(self) -> None:
        """Record values match the computed metric values."""
        from asre.quality.metrics import QualityMetricComputer

        enc = _make_encounter([_make_event()])
        encounters = [_make_reconciled(enc, confidence_score=0.8)]

        computer = QualityMetricComputer()
        metrics = computer.compute(
            encounters=encounters,
            stage_metrics=[],
            events_ingested=100,
            encounters_created=1,
            encounters_updated=0,
        )

        records = computer.to_records(
            metrics=metrics,
            run_id="run_test",
        )

        record_map = {r["metric_name"]: r["metric_value"] for r in records}
        for key, value in metrics.items():
            assert record_map[key] == pytest.approx(value)
