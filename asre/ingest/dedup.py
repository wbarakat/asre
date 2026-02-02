"""Source record deduplication for ingest stage."""

from __future__ import annotations

from typing import Any


def dedup_by_source_record_id(
    records: list[dict[str, Any]],
    key_field: str,
) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate records by source_record_id, keeping first occurrence.

    Records with missing or None key values are always kept (not deduped).

    Args:
        records: List of raw record dicts from ingest.
        key_field: The field name to deduplicate on.

    Returns:
        Tuple of (deduplicated records, count of removed duplicates).
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    dedup_count = 0

    for record in records:
        key_value = record.get(key_field)
        if key_value is None:
            result.append(record)
            continue

        key_str = str(key_value)
        if key_str in seen:
            dedup_count += 1
        else:
            seen.add(key_str)
            result.append(record)

    return result, dedup_count
