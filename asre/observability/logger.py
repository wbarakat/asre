"""Structured JSON logging for ASRE pipeline stages."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Formats log records as JSON with stage context."""

    def __init__(self, stage: str, run_id: str) -> None:
        super().__init__()
        self._stage = stage
        self._run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "stage": self._stage,
            "run_id": self._run_id,
            "message": record.getMessage(),
        }
        # Include extra kwargs passed via extra={}
        for key in ("records_in", "records_out", "duration_seconds"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value
        return json.dumps(log_entry)


def get_logger(stage: str, run_id: str) -> logging.Logger:
    """Return a logger that emits structured JSON with stage context.

    Args:
        stage: Pipeline stage name (e.g. 'ingest', 'stitch').
        run_id: Unique identifier for the pipeline run.

    Returns:
        A configured logging.Logger instance.
    """
    name = f"asre.{stage}.{run_id}"
    logger = logging.getLogger(name)
    level_name = os.environ.get("ASRE_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    # Avoid adding duplicate handlers if get_logger called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter(stage, run_id))
        logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger
