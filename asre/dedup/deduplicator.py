"""Deduplicator — identifies duplicate events within encounters.

Compares events pairwise on configurable match_fields within a
time_tolerance_minutes window. Events matching on all fields AND within
the tolerance are considered duplicates.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from asre.models.canonical_event import CanonicalEvent


class Deduplicator:
    """Identifies duplicate canonical events within an encounter.

    Duplicate detection uses configurable match fields and a time tolerance.
    Events that match on all configured fields AND whose timestamps differ
    by no more than time_tolerance_minutes are considered duplicates.
    """

    def __init__(
        self,
        match_fields: list[str] | None = None,
        time_tolerance_minutes: int = 30,
    ) -> None:
        self.match_fields: list[str] = match_fields or [
            "patient_key",
            "event_type",
            "facility_canonical_id",
        ]
        self.time_tolerance_minutes: int = time_tolerance_minutes

    def _match_key(self, event: CanonicalEvent) -> tuple[Any, ...]:
        """Extract a hashable match key from an event based on match_fields."""
        return tuple(getattr(event, f, None) for f in self.match_fields)

    def find_duplicates(
        self, events: list[CanonicalEvent]
    ) -> list[list[CanonicalEvent]]:
        """Find groups of duplicate events.

        Groups events by match_fields, then within each group checks
        pairwise time proximity. Returns a list of duplicate groups
        (each group contains 2+ events that are duplicates of each other).

        Args:
            events: List of canonical events to check for duplicates.

        Returns:
            List of duplicate groups. Each group is a list of 2+ events.
            Empty list if no duplicates found.
        """
        if len(events) < 2:
            return []

        # Group events by match key
        groups: dict[tuple[Any, ...], list[CanonicalEvent]] = {}
        for event in events:
            key = self._match_key(event)
            groups.setdefault(key, []).append(event)

        tolerance = timedelta(minutes=self.time_tolerance_minutes)
        result: list[list[CanonicalEvent]] = []

        for group_events in groups.values():
            if len(group_events) < 2:
                continue

            # Sort by event_ts for efficient pairwise comparison
            sorted_events = sorted(group_events, key=lambda e: e.event_ts)

            # Use union-find to cluster events within time tolerance
            # Events are transitively linked: if A~B and B~C, then {A,B,C}
            parent: dict[str, str] = {e.event_id: e.event_id for e in sorted_events}

            def find(x: str) -> str:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(x: str, y: str) -> None:
                rx, ry = find(x), find(y)
                if rx != ry:
                    parent[rx] = ry

            for i in range(len(sorted_events)):
                for j in range(i + 1, len(sorted_events)):
                    diff = abs(sorted_events[j].event_ts - sorted_events[i].event_ts)
                    if diff <= tolerance:
                        union(sorted_events[i].event_id, sorted_events[j].event_id)
                    else:
                        # Since sorted, no further events can be within tolerance of i
                        break

            # Collect clusters
            clusters: dict[str, list[CanonicalEvent]] = {}
            for event in sorted_events:
                root = find(event.event_id)
                clusters.setdefault(root, []).append(event)

            for cluster in clusters.values():
                if len(cluster) >= 2:
                    result.append(cluster)

        return result

    @staticmethod
    def _source_type(source_system: str) -> str:
        """Extract source type prefix from source_system name."""
        for prefix in ("adt", "claims", "auth"):
            if source_system.startswith(prefix):
                return prefix
        return source_system

    def resolve_duplicates(
        self,
        duplicate_groups: list[list[CanonicalEvent]],
        source_priority: dict[str, int],
    ) -> tuple[list[CanonicalEvent], list[CanonicalEvent]]:
        """Resolve each duplicate group by keeping the highest-priority event.

        Within each group, the event from the source with the highest
        timestamp_priority is kept. If multiple events share the same
        source priority, the one with the earliest ingested_at wins.

        Args:
            duplicate_groups: Groups of duplicate events from find_duplicates().
            source_priority: Map of source type to priority (higher = more trusted).

        Returns:
            Tuple of (kept_events, duplicate_events).
        """
        kept: list[CanonicalEvent] = []
        duplicates: list[CanonicalEvent] = []

        for group in duplicate_groups:
            # Sort by: highest source priority desc, then earliest ingested_at asc
            sorted_group = sorted(
                group,
                key=lambda e: (
                    -source_priority.get(self._source_type(e.source_system), 0),
                    e.ingested_at,
                ),
            )
            kept.append(sorted_group[0])
            duplicates.extend(sorted_group[1:])

        return kept, duplicates
