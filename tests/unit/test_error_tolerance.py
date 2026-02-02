"""Tests for error tolerance in the canonicalize stage.

US-033: If a required field (patient_key, event_ts) is missing or null,
the record is skipped. Skipped records are logged with error details
and counted in stage metrics. Pipeline continues processing remaining records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from asre.canonicalize.record_validator import RecordValidationError, validate_record
from asre.config.source_schema import FieldMappings


def _make_field_mappings() -> FieldMappings:
    return FieldMappings(
        patient_key="mrn",
        event_ts="event_datetime",
        source_record_id="record_id",
        facility_raw="facility_name",
    )


def _valid_record() -> dict[str, Any]:
    return {
        "mrn": "PAT001",
        "event_datetime": "2024-01-15T10:00:00",
        "record_id": "REC001",
        "facility_name": "General Hospital",
        "_source_name": "adt_vendor_x",
        "_source_type": "adt",
    }


class TestValidateRecord:
    """Tests for validate_record function."""

    def test_valid_record_passes(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        # Should not raise
        validate_record(record, fm)

    def test_missing_patient_key_raises(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        del record["mrn"]

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "patient_key" in str(e)

    def test_null_patient_key_raises(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        record["mrn"] = None

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "patient_key" in str(e)

    def test_missing_event_ts_raises(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        del record["event_datetime"]

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "event_ts" in str(e)

    def test_null_event_ts_raises(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        record["event_datetime"] = None

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "event_ts" in str(e)

    def test_empty_string_patient_key_raises(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        record["mrn"] = ""

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "patient_key" in str(e)

    def test_empty_string_event_ts_raises(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        record["event_datetime"] = ""

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "event_ts" in str(e)

    def test_error_includes_source_record_id(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        record["mrn"] = None

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert e.source_record_id == "REC001"

    def test_error_includes_reason(self) -> None:
        fm = _make_field_mappings()
        record = _valid_record()
        record["mrn"] = None

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert e.reason is not None
            assert "patient_key" in e.reason

    def test_error_when_source_record_id_also_missing(self) -> None:
        """Even when source_record_id is missing, validation reports it."""
        fm = _make_field_mappings()
        record = {"event_datetime": "2024-01-15T10:00:00"}
        # Both patient_key and source_record_id missing

        try:
            validate_record(record, fm)
            assert False, "Expected RecordValidationError"
        except RecordValidationError as e:
            assert "patient_key" in str(e)
            # source_record_id should be "unknown" when not extractable
            assert e.source_record_id is not None


class TestBatchErrorTolerance:
    """Tests for processing a batch with mix of valid and invalid records.

    The key acceptance criterion: batch with 10 records, 2 with missing
    patient_key, produces 8 canonical events + 2 errors.
    """

    def test_batch_skips_invalid_records(self) -> None:
        """10 records, 2 with missing patient_key -> 8 events + 2 errors."""
        from asre.canonicalize.record_validator import process_records_with_tolerance

        fm = _make_field_mappings()
        records: list[dict[str, Any]] = []
        for i in range(10):
            rec = {
                "mrn": f"PAT{i:03d}",
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": f"REC{i:03d}",
                "facility_name": "General Hospital",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
                "_raw_payload": {"original": True},
            }
            records.append(rec)

        # Make records 3 and 7 invalid (missing patient_key)
        records[3]["mrn"] = None
        records[7]["mrn"] = None

        valid, errors = process_records_with_tolerance(records, fm)
        assert len(valid) == 8
        assert len(errors) == 2

    def test_batch_error_details_include_source_record_id(self) -> None:
        from asre.canonicalize.record_validator import process_records_with_tolerance

        fm = _make_field_mappings()
        records: list[dict[str, Any]] = [
            {
                "mrn": None,
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": "BAD_REC_001",
                "facility_name": "General Hospital",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
        ]

        valid, errors = process_records_with_tolerance(records, fm)
        assert len(valid) == 0
        assert len(errors) == 1
        assert errors[0].source_record_id == "BAD_REC_001"
        assert "patient_key" in errors[0].reason

    def test_batch_continues_after_errors(self) -> None:
        """Pipeline continues with remaining valid records."""
        from asre.canonicalize.record_validator import process_records_with_tolerance

        fm = _make_field_mappings()
        records: list[dict[str, Any]] = [
            {
                "mrn": None,
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": "BAD1",
                "facility_name": "General Hospital",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
            {
                "mrn": "PAT001",
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": "GOOD1",
                "facility_name": "General Hospital",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
            {
                "mrn": "PAT002",
                "event_datetime": None,
                "record_id": "BAD2",
                "facility_name": "General Hospital",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
        ]

        valid, errors = process_records_with_tolerance(records, fm)
        assert len(valid) == 1
        assert len(errors) == 2
        assert valid[0]["record_id"] == "GOOD1"

    def test_all_records_valid_returns_no_errors(self) -> None:
        from asre.canonicalize.record_validator import process_records_with_tolerance

        fm = _make_field_mappings()
        records: list[dict[str, Any]] = [
            {
                "mrn": "PAT001",
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": "REC001",
                "facility_name": "General Hospital",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
        ]

        valid, errors = process_records_with_tolerance(records, fm)
        assert len(valid) == 1
        assert len(errors) == 0

    def test_all_records_invalid_returns_empty_valid(self) -> None:
        from asre.canonicalize.record_validator import process_records_with_tolerance

        fm = _make_field_mappings()
        records: list[dict[str, Any]] = [
            {
                "mrn": None,
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": "BAD1",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
            {
                "mrn": "PAT001",
                "event_datetime": None,
                "record_id": "BAD2",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
        ]

        valid, errors = process_records_with_tolerance(records, fm)
        assert len(valid) == 0
        assert len(errors) == 2

    def test_errors_are_logged(self, caplog: Any) -> None:
        """Skipped records are logged with error details."""
        from asre.canonicalize.record_validator import process_records_with_tolerance

        fm = _make_field_mappings()
        records: list[dict[str, Any]] = [
            {
                "mrn": None,
                "event_datetime": "2024-01-15T10:00:00",
                "record_id": "BAD_REC_X",
                "_source_name": "adt_vendor_x",
                "_source_type": "adt",
            },
        ]

        with caplog.at_level(logging.WARNING):
            process_records_with_tolerance(records, fm)

        assert any("BAD_REC_X" in msg for msg in caplog.messages)
        assert any("patient_key" in msg for msg in caplog.messages)
