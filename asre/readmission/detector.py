"""Readmission detection for encounters (US-074).

Flags encounters as readmissions when a patient is admitted to any acute
facility within 30 days of a prior discharge from an acute facility.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from asre.reconcile.stage import ReconciledEncounter

# Facility types considered acute for readmission detection
_ACUTE_FACILITY_TYPES = {"acute"}

# Default readmission window in days
_DEFAULT_READMISSION_WINDOW_DAYS = 30


class ReadmissionDetector:
    """Detects readmissions across encounters for the same patient.

    A readmission is defined as an admission to any acute facility within
    readmission_window_days of a prior discharge from an acute facility.
    """

    def __init__(
        self,
        facility_type_map: dict[str, str] | None = None,
        readmission_window_days: int = _DEFAULT_READMISSION_WINDOW_DAYS,
    ) -> None:
        self._facility_type_map = facility_type_map or {}
        self._readmission_window_days = readmission_window_days

    def _is_acute(self, facility_canonical_id: str | None) -> bool:
        """Check if a facility is acute based on the facility type map."""
        if facility_canonical_id is None:
            return False
        ftype = self._facility_type_map.get(facility_canonical_id, "")
        return ftype in _ACUTE_FACILITY_TYPES

    def _get_admit_ts(self, enc: ReconciledEncounter) -> datetime | None:
        """Get the reconciled admit timestamp for an encounter."""
        if enc.reconciled_timestamps is not None:
            return enc.reconciled_timestamps.admit_ts
        return None

    def _get_discharge_ts(self, enc: ReconciledEncounter) -> datetime | None:
        """Get the reconciled discharge timestamp for an encounter."""
        if enc.reconciled_timestamps is not None:
            return enc.reconciled_timestamps.discharge_ts
        return None

    def detect(self, encounters: list[ReconciledEncounter]) -> None:
        """Detect readmissions across all encounters, mutating them in place.

        Sets is_readmission and readmission_days on each encounter.

        Args:
            encounters: All encounters to process. They will be grouped by
                patient_key and sorted by admit_ts internally.
        """
        # Group encounters by patient_key
        by_patient: dict[str, list[ReconciledEncounter]] = defaultdict(list)
        for enc in encounters:
            by_patient[enc.patient_key].append(enc)

        for patient_key, patient_encounters in by_patient.items():
            self._detect_for_patient(patient_encounters)

    def _detect_for_patient(
        self, encounters: list[ReconciledEncounter]
    ) -> None:
        """Detect readmissions for a single patient's encounters."""
        # Sort by admit_ts
        sorted_encs = sorted(
            encounters,
            key=lambda e: self._get_admit_ts(e) or datetime.min,
        )

        for i, enc in enumerate(sorted_encs):
            admit_ts = self._get_admit_ts(enc)
            fac_id: str | None = enc.facility_canonical_id
            current_is_acute = self._is_acute(fac_id)

            # Default: not a readmission
            enc.is_readmission = False  # type: ignore[attr-defined]
            enc.readmission_days = None  # type: ignore[attr-defined]

            # First encounter or non-acute current facility: not a readmission
            if i == 0 or not current_is_acute or admit_ts is None:
                continue

            # Look backwards for the most recent acute discharge
            for j in range(i - 1, -1, -1):
                prior = sorted_encs[j]
                prior_discharge_ts = self._get_discharge_ts(prior)
                prior_fac_id: str | None = prior.facility_canonical_id

                # Prior must be acute and have a discharge
                if not self._is_acute(prior_fac_id):
                    continue
                if prior_discharge_ts is None:
                    continue

                # Check if within readmission window
                days_diff = (admit_ts - prior_discharge_ts).days
                if days_diff <= self._readmission_window_days:
                    enc.is_readmission = True  # type: ignore[attr-defined]
                    enc.readmission_days = days_diff  # type: ignore[attr-defined]
                    break
