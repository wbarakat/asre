"""Record validation for error tolerance in the canonicalize stage.

Validates required fields (patient_key, event_ts) before mapping.
Invalid records are skipped with logged error details and counted in metrics.
"""

from __future__ import annotations

import logging
from typing import Any

from asre.config.source_schema import FieldMappings

logger = logging.getLogger(__name__)


class RecordValidationError(Exception):
    """Raised when a record fails required field validation."""

    def __init__(self, source_record_id: str, reason: str) -> None:
        self.source_record_id = source_record_id
        self.reason = reason
        super().__init__(f"Record {source_record_id}: {reason}")


def validate_record(record: dict[str, Any], field_mappings: FieldMappings) -> None:
    """Validate that required fields are present and non-null.

    Args:
        record: Raw record dict from ingest stage.
        field_mappings: Field mapping config defining source column names.

    Raises:
        RecordValidationError: If patient_key or event_ts is missing, null, or empty.
    """
    # Extract source_record_id for error reporting (best effort)
    src_id_col = field_mappings.source_record_id
    source_record_id = str(record.get(src_id_col, "unknown"))

    # Check patient_key
    pk_col = field_mappings.patient_key
    pk_val = record.get(pk_col)
    if pk_val is None or (isinstance(pk_val, str) and pk_val.strip() == ""):
        raise RecordValidationError(
            source_record_id=source_record_id,
            reason=f"Required field patient_key (column '{pk_col}') is missing or null",
        )

    # Check event_ts
    ts_col = field_mappings.event_ts
    ts_val = record.get(ts_col)
    if ts_val is None or (isinstance(ts_val, str) and ts_val.strip() == ""):
        raise RecordValidationError(
            source_record_id=source_record_id,
            reason=f"Required field event_ts (column '{ts_col}') is missing or null",
        )


def process_records_with_tolerance(
    records: list[dict[str, Any]],
    field_mappings: FieldMappings,
) -> tuple[list[dict[str, Any]], list[RecordValidationError]]:
    """Filter records, skipping invalid ones and collecting errors.

    Args:
        records: Raw record dicts from ingest stage.
        field_mappings: Field mapping config.

    Returns:
        Tuple of (valid_records, errors).
    """
    valid: list[dict[str, Any]] = []
    errors: list[RecordValidationError] = []

    for record in records:
        try:
            validate_record(record, field_mappings)
            valid.append(record)
        except RecordValidationError as e:
            logger.warning(
                "Skipping unparseable record %s: %s",
                e.source_record_id,
                e.reason,
            )
            errors.append(e)

    return valid, errors
