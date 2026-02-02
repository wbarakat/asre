"""Tests for structured JSON logging."""

from __future__ import annotations

import json
import logging

from asre.observability.logger import get_logger


def test_get_logger_returns_logger() -> None:
    logger = get_logger(stage="ingest", run_id="run_001")
    assert isinstance(logger, logging.Logger)


def test_log_output_is_json(capfd: object) -> None:
    logger = get_logger(stage="ingest", run_id="run_001")
    handler = logger.handlers[0]
    assert handler is not None

    # Emit a log record and capture it
    import io

    stream = io.StringIO()
    handler.stream = stream  # type: ignore[attr-defined]
    logger.info("test message")
    output = stream.getvalue().strip()

    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["stage"] == "ingest"
    assert parsed["run_id"] == "run_001"
    assert parsed["message"] == "test message"
    assert "timestamp" in parsed


def test_log_output_includes_extra_kwargs(capfd: object) -> None:
    logger = get_logger(stage="stitch", run_id="run_002")
    handler = logger.handlers[0]

    import io

    stream = io.StringIO()
    handler.stream = stream  # type: ignore[attr-defined]
    logger.info("stage done", extra={"records_in": 100, "records_out": 95, "duration_seconds": 1.5})
    output = stream.getvalue().strip()

    parsed = json.loads(output)
    assert parsed["records_in"] == 100
    assert parsed["records_out"] == 95
    assert parsed["duration_seconds"] == 1.5


def test_log_output_has_required_fields() -> None:
    logger = get_logger(stage="dedup", run_id="run_003")
    handler = logger.handlers[0]

    import io

    stream = io.StringIO()
    handler.stream = stream  # type: ignore[attr-defined]
    logger.warning("something happened")
    output = stream.getvalue().strip()

    parsed = json.loads(output)
    required_fields = {"timestamp", "level", "stage", "run_id", "message"}
    assert required_fields.issubset(set(parsed.keys()))


def test_multiple_loggers_independent() -> None:
    logger1 = get_logger(stage="ingest", run_id="run_a")
    logger2 = get_logger(stage="stitch", run_id="run_b")

    import io

    stream1 = io.StringIO()
    stream2 = io.StringIO()
    logger1.handlers[0].stream = stream1  # type: ignore[attr-defined]
    logger2.handlers[0].stream = stream2  # type: ignore[attr-defined]

    logger1.info("msg1")
    logger2.info("msg2")

    parsed1 = json.loads(stream1.getvalue().strip())
    parsed2 = json.loads(stream2.getvalue().strip())

    assert parsed1["stage"] == "ingest"
    assert parsed1["run_id"] == "run_a"
    assert parsed2["stage"] == "stitch"
    assert parsed2["run_id"] == "run_b"
