"""Tests for patient class normalization (HL7 + event-type overrides)."""

from __future__ import annotations

from asre.canonicalize.patient_class_normalizer import normalize_patient_class


class TestPatientClassNormalization:
    def test_hl7_codes_normalized(self) -> None:
        assert normalize_patient_class("I") == "inpatient"
        assert normalize_patient_class("E") == "ed"
        assert normalize_patient_class("O") == "outpatient"

    def test_event_type_overrides_observation(self) -> None:
        assert normalize_patient_class("O", event_type="OBS_START") == "observation"
        assert normalize_patient_class("O", event_type="OBS_END") == "observation"
        assert normalize_patient_class("I", event_type="OBS_TO_IP") == "observation"

    def test_event_type_overrides_ed(self) -> None:
        assert normalize_patient_class("I", event_type="ED_ARRIVAL") == "ed"
        assert normalize_patient_class("O", event_type="ED_DEPARTURE") == "ed"

    def test_passes_through_canonical_values(self) -> None:
        assert normalize_patient_class("inpatient") == "inpatient"
        assert normalize_patient_class("outpatient") == "outpatient"
        assert normalize_patient_class("ed") == "ed"
        assert normalize_patient_class("observation") == "observation"

    def test_unknown_class_returns_none(self) -> None:
        assert normalize_patient_class("Z") is None
        assert normalize_patient_class(None) is None
