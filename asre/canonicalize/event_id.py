"""Deterministic event_id generation."""

from __future__ import annotations

import hashlib


def generate_event_id(
    source_system: str,
    source_record_id: str,
    event_type: str,
) -> str:
    """Generate a deterministic event_id for a canonical event."""
    raw = f"{source_system}|{source_record_id}|{event_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
