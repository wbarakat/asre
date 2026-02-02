"""Tests for source_record_id dedup on ingest."""

from __future__ import annotations

from typing import Any

from asre.ingest.dedup import dedup_by_source_record_id


class TestDedupBySourceRecordId:
    """Tests for dedup_by_source_record_id function."""

    def test_no_duplicates_returns_all(self) -> None:
        """Records with unique source_record_ids are all kept."""
        records = [
            {"source_record_id": "A", "name": "first"},
            {"source_record_id": "B", "name": "second"},
            {"source_record_id": "C", "name": "third"},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        assert len(result) == 3
        assert dedup_count == 0

    def test_duplicates_collapsed_to_first(self) -> None:
        """Duplicate source_record_ids keep only the first occurrence."""
        records = [
            {"source_record_id": "A", "name": "first"},
            {"source_record_id": "A", "name": "second"},
            {"source_record_id": "B", "name": "third"},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        assert len(result) == 2
        assert result[0]["name"] == "first"
        assert result[1]["name"] == "third"
        assert dedup_count == 1

    def test_multiple_duplicates_of_same_id(self) -> None:
        """Three records with same source_record_id collapse to one."""
        records = [
            {"source_record_id": "A", "val": 1},
            {"source_record_id": "A", "val": 2},
            {"source_record_id": "A", "val": 3},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        assert len(result) == 1
        assert result[0]["val"] == 1
        assert dedup_count == 2

    def test_preserves_order(self) -> None:
        """Output order matches input order of first occurrences."""
        records = [
            {"source_record_id": "C", "val": 1},
            {"source_record_id": "A", "val": 2},
            {"source_record_id": "B", "val": 3},
            {"source_record_id": "A", "val": 4},
            {"source_record_id": "C", "val": 5},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        assert len(result) == 3
        assert [r["source_record_id"] for r in result] == ["C", "A", "B"]
        assert dedup_count == 2

    def test_empty_input(self) -> None:
        """Empty record list returns empty with zero dedup count."""
        result, dedup_count = dedup_by_source_record_id([], "source_record_id")
        assert result == []
        assert dedup_count == 0

    def test_single_record(self) -> None:
        """Single record returns as-is."""
        records = [{"source_record_id": "A", "val": 1}]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        assert len(result) == 1
        assert dedup_count == 0

    def test_custom_key_field(self) -> None:
        """Dedup works with a different key field name."""
        records = [
            {"record_id": "X", "val": 1},
            {"record_id": "X", "val": 2},
            {"record_id": "Y", "val": 3},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "record_id")
        assert len(result) == 2
        assert result[0]["val"] == 1
        assert result[1]["val"] == 3
        assert dedup_count == 1

    def test_missing_key_field_skipped(self) -> None:
        """Records missing the key field are kept (not deduped)."""
        records: list[dict[str, Any]] = [
            {"source_record_id": "A", "val": 1},
            {"val": 2},  # no source_record_id
            {"source_record_id": "A", "val": 3},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        # First A kept, missing-key record kept, second A removed
        assert len(result) == 2
        assert result[0]["val"] == 1
        assert result[1]["val"] == 2
        assert dedup_count == 1

    def test_none_key_value_treated_as_unique(self) -> None:
        """Records with None as key value are each treated as unique."""
        records: list[dict[str, Any]] = [
            {"source_record_id": None, "val": 1},
            {"source_record_id": None, "val": 2},
            {"source_record_id": "A", "val": 3},
        ]
        result, dedup_count = dedup_by_source_record_id(records, "source_record_id")
        # None values are not deduped - each is unique
        assert len(result) == 3
        assert dedup_count == 0
