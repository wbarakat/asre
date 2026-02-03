"""EpisodeStitcher — groups encounters into episodes of care (US-086).

Algorithm per SPEC section 9.2:
1. Query encounters per patient ordered by admit_ts.
2. For each encounter, check linkage rules against prior encounters in the
   current episode.
3. If any rule links the encounter, add it to the existing episode;
   otherwise create a new episode.

Linkage rules (checked in order):
- Readmission: acute readmit within readmission_window_days of prior acute
  discharge.
- Post-acute: non-acute admit within post_acute_linkage_days of prior
  acute discharge.
- ED bounce-back: ED encounter within ed_bounceback_days of prior
  discharge.
- Planned return: same facility admit within planned_return_days of prior
  discharge.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from asre.models.encounter import Encounter


@dataclass
class _EpisodeGroup:
    """Mutable accumulator for encounters being grouped into an episode."""

    encounter_ids: list[str] = field(default_factory=list)
    encounters: list[Encounter] = field(default_factory=list)
    patient_key: str = ""

    @property
    def last_encounter(self) -> Encounter:
        return self.encounters[-1]

    def add(self, enc: Encounter) -> None:
        self.encounter_ids.append(enc.encounter_id)
        self.encounters.append(enc)
        if not self.patient_key:
            self.patient_key = enc.patient_key


class EpisodeStitcher:
    """Groups encounters into episodes based on temporal and clinical linkage rules."""

    def __init__(
        self,
        readmission_window_days: int = 30,
        post_acute_linkage_days: int = 14,
        planned_return_days: int = 90,
        ed_bounceback_days: int = 7,
    ) -> None:
        self.readmission_window_days = readmission_window_days
        self.post_acute_linkage_days = post_acute_linkage_days
        self.planned_return_days = planned_return_days
        self.ed_bounceback_days = ed_bounceback_days

    def stitch(self, encounters: list[Encounter]) -> list[_EpisodeGroup]:
        """Group encounters into episode groups.

        Returns a list of _EpisodeGroup, each containing the encounter_ids
        and encounters belonging to that episode.
        """
        # Partition by patient_key
        by_patient: dict[str, list[Encounter]] = defaultdict(list)
        for enc in encounters:
            by_patient[enc.patient_key].append(enc)

        all_groups: list[_EpisodeGroup] = []

        for patient_key in sorted(by_patient.keys()):
            patient_encounters = sorted(by_patient[patient_key], key=lambda e: e.admit_ts)
            groups = self._stitch_patient(patient_encounters)
            all_groups.extend(groups)

        return all_groups

    def _stitch_patient(self, encounters: list[Encounter]) -> list[_EpisodeGroup]:
        """Stitch sorted encounters for a single patient into episode groups."""
        if not encounters:
            return []

        groups: list[_EpisodeGroup] = []
        current = _EpisodeGroup()
        current.add(encounters[0])
        groups.append(current)

        for enc in encounters[1:]:
            linked = self._try_link(current, enc)
            if linked:
                current.add(enc)
            else:
                current = _EpisodeGroup()
                current.add(enc)
                groups.append(current)

        return groups

    def _try_link(self, group: _EpisodeGroup, enc: Encounter) -> bool:
        """Check if enc should link to the current episode group.

        Checks against the last encounter in the group that has a discharge_ts,
        since linkage requires a prior discharge timestamp.
        """
        # Find the last encounter in the group with a discharge_ts
        prior = self._last_discharged(group)
        if prior is None:
            # No discharged encounter to link from
            return False

        gap = enc.admit_ts - prior.discharge_ts  # type: ignore[operator]

        # Rule 1: Readmission linkage (both must be acute)
        if self._is_readmission_link(prior, enc, gap):
            return True

        # Rule 2: Post-acute linkage (prior acute, current non-acute)
        if self._is_post_acute_link(prior, enc, gap):
            return True

        # Rule 3: ED bounce-back linkage
        if self._is_ed_bounceback_link(enc, gap):
            return True

        # Rule 4: Planned return (same facility)
        if self._is_planned_return_link(prior, enc, gap):
            return True

        return False

    def _last_discharged(self, group: _EpisodeGroup) -> Encounter | None:
        """Return the last encounter in the group that has a discharge_ts."""
        for enc in reversed(group.encounters):
            if enc.discharge_ts is not None:
                return enc
        return None

    def _is_readmission_link(
        self, prior: Encounter, current: Encounter, gap: timedelta
    ) -> bool:
        """Both acute, current admits within readmission_window_days of prior discharge."""
        if not prior.is_acute or not current.is_acute:
            return False
        return gap <= timedelta(days=self.readmission_window_days)

    def _is_post_acute_link(
        self, prior: Encounter, current: Encounter, gap: timedelta
    ) -> bool:
        """Prior acute, current non-acute (SNF/LTACH/rehab), within post_acute_linkage_days."""
        if not prior.is_acute:
            return False
        if current.is_acute:
            return False
        return gap <= timedelta(days=self.post_acute_linkage_days)

    def _is_ed_bounceback_link(
        self, current: Encounter, gap: timedelta
    ) -> bool:
        """ED visit within ed_bounceback_days of prior discharge."""
        if current.encounter_type != "ed_only":
            return False
        return gap <= timedelta(days=self.ed_bounceback_days)

    def _is_planned_return_link(
        self, prior: Encounter, current: Encounter, gap: timedelta
    ) -> bool:
        """Same facility admit within planned_return_days of prior discharge.

        Only applies when the gap exceeds the readmission window — encounters
        within the readmission window are governed solely by the readmission
        rule to avoid conflicting overlap.
        """
        if prior.facility_canonical_id != current.facility_canonical_id:
            return False
        # Don't override readmission rule for acute-to-acute within readmission window
        if prior.is_acute and current.is_acute:
            if gap <= timedelta(days=self.readmission_window_days):
                return False
        return gap <= timedelta(days=self.planned_return_days)
