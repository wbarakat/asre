"""EpisodeMetadataBuilder — populates Episode from encounters and group data (US-094).

Converts episode group data (encounter list, linkage flags) into a fully
populated Episode dataclass with all fields from SPEC section 3.4.
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.episode.condition_grouper import classify_episode_type
from asre.episode.episode_scorer import EpisodeScorer
from asre.models.encounter import Encounter
from asre.models.episode import Episode


class EpisodeMetadataBuilder:
    """Builds a fully populated Episode from encounters and episode group metadata."""

    def __init__(self) -> None:
        self._scorer = EpisodeScorer()

    def build(
        self,
        episode_id: str,
        encounters: list[Encounter],
        includes_readmission: bool,
        includes_post_acute: bool,
    ) -> Episode:
        """Build an Episode from its constituent encounters.

        Args:
            episode_id: Deterministic episode ID.
            encounters: Encounters belonging to this episode, sorted by admit_ts.
            includes_readmission: Whether the episode includes a readmission.
            includes_post_acute: Whether the episode includes post-acute care.

        Returns:
            Fully populated Episode dataclass.
        """
        now = datetime.now(tz=timezone.utc)

        patient_key = encounters[0].patient_key
        encounter_ids = [e.encounter_id for e in encounters]

        # Timestamps
        episode_start_ts = min(e.admit_ts for e in encounters)
        episode_end_ts = self._compute_end_ts(encounters)
        total_los_days = self._compute_total_los(episode_start_ts, episode_end_ts)

        # Status
        episode_status = self._compute_status(encounters)

        # Facilities
        facility_sequence = self._compute_facility_sequence(encounters)
        facility_count = len(facility_sequence)

        # Acuity
        is_acute = any(e.is_acute for e in encounters)

        # Diagnosis
        principal_diagnosis = self._first_principal_diagnosis(encounters)
        diagnosis_codes = self._aggregate_diagnosis_codes(encounters)

        # Episode type from condition grouper
        episode_type = self._classify(encounters)

        # Confidence
        confidence_score = self._scorer.compute_score(encounters)

        return Episode(
            episode_id=episode_id,
            patient_key=patient_key,
            episode_type=episode_type,
            episode_status=episode_status,
            episode_start_ts=episode_start_ts,
            episode_end_ts=episode_end_ts,
            total_los_days=total_los_days,
            encounter_ids=encounter_ids,
            encounter_count=len(encounters),
            facility_count=facility_count,
            facility_sequence=facility_sequence,
            includes_readmission=includes_readmission,
            includes_post_acute=includes_post_acute,
            is_acute=is_acute,
            principal_diagnosis=principal_diagnosis,
            diagnosis_codes=diagnosis_codes,
            confidence_score=confidence_score,
            created_at=now,
            updated_at=now,
        )

    def _compute_end_ts(self, encounters: list[Encounter]) -> datetime | None:
        """Episode end is the latest discharge_ts, or None if any encounter is open."""
        discharge_times: list[datetime] = []
        for e in encounters:
            if e.discharge_ts is None and e.status != "cancelled":
                return None
            if e.discharge_ts is not None:
                discharge_times.append(e.discharge_ts)
        return max(discharge_times) if discharge_times else None

    def _compute_total_los(
        self, start: datetime, end: datetime | None
    ) -> float | None:
        """Total LOS in days from episode start to end. None if episode open."""
        if end is None:
            return None
        return (end - start).total_seconds() / 86400.0

    def _compute_status(self, encounters: list[Encounter]) -> str:
        """Derive episode status from encounter statuses.

        - active: any encounter is open
        - closed: all encounters are closed (or cancelled)
        - reopened: reserved for future use (episode previously closed, now open)
        """
        statuses = {e.status for e in encounters}
        if "open" in statuses:
            return "active"
        # All closed or cancelled
        return "closed"

    def _compute_facility_sequence(self, encounters: list[Encounter]) -> list[str]:
        """Ordered unique facility IDs by first appearance in encounter order."""
        seen: set[str] = set()
        sequence: list[str] = []
        for e in sorted(encounters, key=lambda e: e.admit_ts):
            if e.facility_canonical_id not in seen:
                seen.add(e.facility_canonical_id)
                sequence.append(e.facility_canonical_id)
        return sequence

    def _first_principal_diagnosis(self, encounters: list[Encounter]) -> str | None:
        """Return principal diagnosis from the first encounter that has one."""
        for e in encounters:
            if e.principal_diagnosis:
                return e.principal_diagnosis
        return None

    def _aggregate_diagnosis_codes(
        self, encounters: list[Encounter]
    ) -> list[dict[str, str | None]] | None:
        """Aggregate diagnosis codes from all encounters, deduplicating by code value."""
        seen_codes: set[str] = set()
        result: list[dict[str, str | None]] = []
        for e in encounters:
            if not e.diagnosis_codes:
                continue
            for dx in e.diagnosis_codes:
                code = dx.get("code", "")
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    result.append(dx)
        return result if result else None

    def _classify(self, encounters: list[Encounter]) -> str:
        """Classify episode type using condition grouper."""
        # Collect diagnosis codes and DRG from encounters
        all_dx: list[dict[str, str | None]] = []
        drg: str | None = None
        for e in encounters:
            if e.drg and not drg:
                drg = e.drg
            if e.diagnosis_codes:
                all_dx.extend(e.diagnosis_codes)
        return classify_episode_type(all_dx, drg)
