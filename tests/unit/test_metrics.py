"""Tests for per-stage metrics tracking."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from asre.observability.metrics import StageMetrics


def test_stage_metrics_construction() -> None:
    m = StageMetrics(stage_name="ingest", run_id="run_001")
    assert m.stage_name == "ingest"
    assert m.run_id == "run_001"
    assert m.records_in == 0
    assert m.records_out == 0
    assert m.errors == 0
    assert m.status == "pending"
    assert m.started_at is None
    assert m.completed_at is None


def test_context_manager_captures_timing() -> None:
    with StageMetrics("stitch", "run_002") as m:
        assert m.started_at is not None
        assert isinstance(m.started_at, datetime)
        assert m.status == "running"
        time.sleep(0.05)

    assert m.completed_at is not None
    assert isinstance(m.completed_at, datetime)
    assert m.completed_at > m.started_at
    assert m.status == "success"


def test_context_manager_records_failure_on_exception() -> None:
    try:
        with StageMetrics("dedup", "run_003") as m:
            raise ValueError("something broke")
    except ValueError:
        pass

    assert m.status == "failed"
    assert m.completed_at is not None


def test_records_in_out_tracking() -> None:
    with StageMetrics("canonicalize", "run_004") as m:
        m.records_in = 100
        m.records_out = 95
        m.errors = 5

    assert m.records_in == 100
    assert m.records_out == 95
    assert m.errors == 5


def test_to_dict_returns_all_fields() -> None:
    with StageMetrics("score", "run_005") as m:
        m.records_in = 50
        m.records_out = 50

    result = m.to_dict()
    assert result["stage_name"] == "score"
    assert result["run_id"] == "run_005"
    assert result["records_in"] == 50
    assert result["records_out"] == 50
    assert result["errors"] == 0
    assert result["status"] == "success"
    assert "started_at" in result
    assert "completed_at" in result
    # Timestamps should be ISO format strings
    assert isinstance(result["started_at"], str)
    assert isinstance(result["completed_at"], str)


def test_to_dict_with_none_timestamps() -> None:
    m = StageMetrics("ingest", "run_006")
    result = m.to_dict()
    assert result["started_at"] is None
    assert result["completed_at"] is None


def test_timing_values_are_utc() -> None:
    with StageMetrics("reconcile", "run_007") as m:
        pass

    assert m.started_at is not None
    assert m.started_at.tzinfo == timezone.utc
    assert m.completed_at is not None
    assert m.completed_at.tzinfo == timezone.utc
