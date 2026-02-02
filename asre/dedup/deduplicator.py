"""Deduplicator — identifies duplicate events within encounters.

Compares events pairwise on configurable match_fields within a
time_tolerance_minutes window. Events matching on all fields AND within
the tolerance are considered duplicates.

Also provides encounter-level dedup (US-056): merges overlapping encounters
for the same patient at the same facility.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from asre.models.canonical_event import CanonicalEvent

if TYPE_CHECKING:
    from asre.stitch.encounter_stitcher import StitchedEncounter


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

    @staticmethod
    def mark_roles(
        kept: list[CanonicalEvent],
        duplicates: list[CanonicalEvent],
    ) -> None:
        """Mark duplicate events with role_in_encounter = 'duplicate'.

        Kept events retain their existing role_in_encounter value.
        Duplicate events are marked with 'duplicate' for the detail table.

        Args:
            kept: Events kept after resolution (roles unchanged).
            duplicates: Events identified as duplicates (role set to 'duplicate').
        """
        for event in duplicates:
            event.role_in_encounter = "duplicate"

    def merge_overlapping_encounters(
        self,
        encounters: list[StitchedEncounter],
    ) -> list[StitchedEncounter]:
        """Merge overlapping encounters for the same patient at the same facility.

        Two encounters overlap when their time ranges intersect. An open
        encounter (no discharge) is treated as extending to infinity, so it
        overlaps with any later encounter at the same patient+facility.

        The merged encounter keeps the earlier encounter's ID, combines all
        events, and takes the earlier admit_ts / later discharge_ts.

        Args:
            encounters: List of StitchedEncounters to check for overlaps.

        Returns:
            List of encounters after merging overlapping ones.
        """
        if len(encounters) < 2:
            return list(encounters)

        from asre.stitch.encounter_stitcher import StitchedEncounter as _SE

        # Group by (patient_key, facility_canonical_id)
        groups: dict[tuple[str, str | None], list[_SE]] = {}
        for enc in encounters:
            key = (enc.patient_key, enc.facility_canonical_id)
            groups.setdefault(key, []).append(enc)

        result: list[_SE] = []

        for _key, group in groups.items():
            if len(group) < 2:
                result.extend(group)
                continue

            # Sort by earliest event timestamp (admit_ts proxy)
            group.sort(key=lambda e: self._earliest_event_ts(e))
            merged = self._merge_group(group)
            result.extend(merged)

        return result

    @staticmethod
    def _earliest_event_ts(encounter: StitchedEncounter) -> datetime:
        """Get the earliest event timestamp from an encounter."""
        if not encounter.events:
            return datetime.min
        return min(e.event_ts for e in encounter.events)

    @staticmethod
    def _latest_event_ts(encounter: StitchedEncounter) -> datetime | None:
        """Get the latest discharge-type event timestamp, or None if open."""
        if not encounter.has_discharge:
            return None
        discharge_types = {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"}
        discharge_ts: datetime | None = None
        for event in encounter.events:
            if event.event_type in discharge_types:
                if discharge_ts is None or event.event_ts > discharge_ts:
                    discharge_ts = event.event_ts
        return discharge_ts

    def _encounters_overlap(
        self,
        enc_a: StitchedEncounter,
        enc_b: StitchedEncounter,
    ) -> bool:
        """Check if two encounters have overlapping time ranges.

        An open encounter (no discharge) extends to infinity.
        enc_b is assumed to start at or after enc_a.
        """
        # enc_a's range: [admit_a, discharge_a] or [admit_a, +inf) if open
        discharge_a = self._latest_event_ts(enc_a)

        # If enc_a is open (no discharge), it overlaps with everything after it
        if discharge_a is None:
            return True

        # enc_b starts at its earliest event
        admit_b = self._earliest_event_ts(enc_b)

        # Overlap if enc_b starts before enc_a ends
        return admit_b <= discharge_a

    def _merge_group(
        self,
        sorted_encounters: list[StitchedEncounter],
    ) -> list[StitchedEncounter]:
        """Merge overlapping encounters within a sorted group (same patient+facility).

        Uses a sweep approach: maintains a 'current' encounter and merges
        subsequent overlapping encounters into it.
        """
        from asre.stitch.encounter_stitcher import StitchedEncounter as _SE

        result: list[_SE] = []
        current = sorted_encounters[0]

        for i in range(1, len(sorted_encounters)):
            candidate = sorted_encounters[i]
            if self._encounters_overlap(current, candidate):
                current = self._merge_two(current, candidate)
            else:
                result.append(current)
                current = candidate

        result.append(current)
        return result

    @staticmethod
    def _merge_two(
        earlier: StitchedEncounter,
        later: StitchedEncounter,
    ) -> StitchedEncounter:
        """Merge two overlapping encounters into one.

        The merged encounter uses the earlier encounter's ID and combines
        all events from both.
        """
        from asre.stitch.encounter_stitcher import StitchedEncounter as _SE

        merged = _SE(
            patient_key=earlier.patient_key,
            facility_canonical_id=earlier.facility_canonical_id,
        )
        # Combine events from both, re-sort by event_ts
        all_events = earlier.events + later.events
        all_events.sort(key=lambda e: e.event_ts)
        for event in all_events:
            merged.add_event(event)

        # Use the earlier encounter's ID (stability)
        merged.encounter_id = earlier.encounter_id

        return merged
