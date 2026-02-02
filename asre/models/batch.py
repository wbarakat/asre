"""EventBatch abstraction for internal pipeline processing."""

from __future__ import annotations

from dataclasses import dataclass

from asre.models.canonical_event import CanonicalEvent


@dataclass
class EventBatch:
    """A batch of canonical events for pipeline processing.

    Per SPEC §2.4, EventBatch is the streaming-ready interface
    (batch-only in v1) used by all pipeline stages.
    """

    batch_id: str
    events: list[CanonicalEvent]
