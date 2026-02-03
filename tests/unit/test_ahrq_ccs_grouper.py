"""Tests for AHRQ CCS grouper (US-092)."""

from __future__ import annotations

from asre.groupers.ahrq_ccs import AHRQCCSGrouper
from asre.groupers.base import ConditionGrouper


class TestAHRQCCSGrouper:
    """Tests for the AHRQ CCS grouper implementation."""

    def test_is_condition_grouper_subclass(self) -> None:
        """AHRQCCSGrouper implements ConditionGrouper ABC."""
        grouper = AHRQCCSGrouper()
        assert isinstance(grouper, ConditionGrouper)

    def test_hip_replacement_drg_produces_surgical(self) -> None:
        """Hip replacement DRG (469/470) produces surgical classification."""
        grouper = AHRQCCSGrouper()
        result = grouper.group([], "470")
        assert result == "surgical"

    def test_knee_replacement_drg_produces_surgical(self) -> None:
        """Knee replacement DRG (469) produces surgical classification."""
        grouper = AHRQCCSGrouper()
        result = grouper.group([], "469")
        assert result == "surgical"

    def test_cabg_drg_produces_surgical(self) -> None:
        """CABG DRG (231-236) produces surgical."""
        grouper = AHRQCCSGrouper()
        result = grouper.group([], "233")
        assert result == "surgical"

    def test_maternity_drg_produces_maternity(self) -> None:
        """Maternity DRGs (765-768, 774-775, 796-798) produce maternity."""
        grouper = AHRQCCSGrouper()
        result = grouper.group([], "765")
        assert result == "maternity"

    def test_maternity_drg_768(self) -> None:
        grouper = AHRQCCSGrouper()
        assert grouper.group([], "768") == "maternity"

    def test_behavioral_health_drg_produces_behavioral_health(self) -> None:
        """Behavioral health DRGs (876-887) produce behavioral_health."""
        grouper = AHRQCCSGrouper()
        result = grouper.group([], "880")
        assert result == "behavioral_health"

    def test_pneumonia_icd10_produces_medical(self) -> None:
        """Pneumonia ICD-10 (J18.9) produces medical classification."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = grouper.group(codes, None)
        assert result == "medical"

    def test_chf_icd10_produces_chronic_exacerbation(self) -> None:
        """CHF ICD-10 (I50.x) produces chronic_exacerbation."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "I50.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = grouper.group(codes, None)
        assert result == "chronic_exacerbation"

    def test_copd_icd10_produces_chronic_exacerbation(self) -> None:
        """COPD ICD-10 (J44.x) produces chronic_exacerbation."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "J44.1", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = grouper.group(codes, None)
        assert result == "chronic_exacerbation"

    def test_delivery_icd10_produces_maternity(self) -> None:
        """Delivery ICD-10 (O80) produces maternity."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "O80", "type": "ICD-10-CM", "sequence": "1", "poa": None},
        ]
        result = grouper.group(codes, None)
        assert result == "maternity"

    def test_schizophrenia_icd10_produces_behavioral_health(self) -> None:
        """Schizophrenia ICD-10 (F20.x) produces behavioral_health."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "F20.0", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = grouper.group(codes, None)
        assert result == "behavioral_health"

    def test_unknown_code_produces_unclassified(self) -> None:
        """Unknown/unmapped code produces unclassified."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "999.99", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = grouper.group(codes, None)
        assert result == "unclassified"

    def test_no_codes_no_drg_produces_unclassified(self) -> None:
        """No codes and no DRG produces unclassified."""
        grouper = AHRQCCSGrouper()
        result = grouper.group([], None)
        assert result == "unclassified"

    def test_drg_takes_precedence_over_icd10(self) -> None:
        """DRG-based rules are checked before ICD-10 classification."""
        grouper = AHRQCCSGrouper()
        # Pneumonia code (medical) but surgical DRG
        codes: list[dict[str, str | None]] = [
            {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = grouper.group(codes, "470")
        assert result == "surgical"

    def test_uses_principal_diagnosis_first(self) -> None:
        """When multiple codes, the first (principal) drives classification."""
        grouper = AHRQCCSGrouper()
        codes: list[dict[str, str | None]] = [
            {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
            {"code": "F20.0", "type": "ICD-10-CM", "sequence": "2", "poa": "Y"},
        ]
        result = grouper.group(codes, None)
        assert result == "medical"

    def test_return_value_in_valid_episode_types(self) -> None:
        """All return values are in VALID_EPISODE_TYPES."""
        grouper = AHRQCCSGrouper()
        test_cases: list[tuple[list[dict[str, str | None]], str | None]] = [
            ([], "470"),
            ([{"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"}], None),
            ([], None),
            ([{"code": "ZZZ.999", "type": None, "sequence": None, "poa": None}], None),
        ]
        for codes, drg in test_cases:
            result = grouper.group(codes, drg)
            assert result in ConditionGrouper.VALID_EPISODE_TYPES, (
                f"Result {result!r} not in VALID_EPISODE_TYPES for codes={codes}, drg={drg}"
            )


class TestConditionGrouperDispatcher:
    """Tests for the episode/condition_grouper.py dispatcher."""

    def test_dispatches_drg_first(self) -> None:
        """Dispatcher checks DRG rules before AHRQ CCS fallback."""
        from asre.episode.condition_grouper import classify_episode_type

        result = classify_episode_type([], "470")
        assert result == "surgical"

    def test_falls_back_to_icd10(self) -> None:
        """Dispatcher falls back to ICD-10 when no DRG match."""
        from asre.episode.condition_grouper import classify_episode_type

        codes: list[dict[str, str | None]] = [
            {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        result = classify_episode_type(codes, None)
        assert result == "medical"

    def test_unclassified_fallback(self) -> None:
        """Dispatcher returns unclassified when nothing matches."""
        from asre.episode.condition_grouper import classify_episode_type

        result = classify_episode_type([], None)
        assert result == "unclassified"
