"""Tests for PatientClassResolver - resolves patient_class from claims bill type codes."""

from __future__ import annotations

from asre.canonicalize.patient_class_resolver import PatientClassResolver
from asre.config.source_schema import PatientClassRules


def _make_rules() -> PatientClassRules:
    """Create patient class rules matching the test_customer claims config."""
    return PatientClassRules(
        conditions=[
            {"when": "bill_type_code LIKE '11%'", "patient_class": "inpatient"},
            {"when": "bill_type_code LIKE '12%'", "patient_class": "inpatient"},
            {"when": "bill_type_code LIKE '13%'", "patient_class": "outpatient"},
            {"when": "bill_type_code LIKE '14%'", "patient_class": "outpatient"},
            {"when": "bill_type_code LIKE '85%'", "patient_class": "ed"},
        ]
    )


class TestPatientClassResolver:
    """Tests for PatientClassResolver."""

    def test_construction(self) -> None:
        """PatientClassResolver can be constructed with PatientClassRules."""
        resolver = PatientClassResolver(_make_rules())
        assert resolver is not None

    def test_bill_type_111_is_inpatient(self) -> None:
        """bill_type_code '111' matches '11%' -> inpatient."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": "111"}
        result = resolver.resolve(record)
        assert result == "inpatient"

    def test_bill_type_121_is_inpatient(self) -> None:
        """bill_type_code '121' matches '12%' -> inpatient."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": "121"}
        result = resolver.resolve(record)
        assert result == "inpatient"

    def test_bill_type_131_is_outpatient(self) -> None:
        """bill_type_code '131' matches '13%' -> outpatient."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": "131"}
        result = resolver.resolve(record)
        assert result == "outpatient"

    def test_bill_type_141_is_outpatient(self) -> None:
        """bill_type_code '141' matches '14%' -> outpatient."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": "141"}
        result = resolver.resolve(record)
        assert result == "outpatient"

    def test_bill_type_851_is_ed(self) -> None:
        """bill_type_code '851' matches '85%' -> ed."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": "851"}
        result = resolver.resolve(record)
        assert result == "ed"

    def test_bill_type_999_is_none(self) -> None:
        """bill_type_code '999' matches no rule -> None."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": "999"}
        result = resolver.resolve(record)
        assert result is None

    def test_first_matching_condition_wins(self) -> None:
        """When multiple conditions could match, the first one wins."""
        rules = PatientClassRules(
            conditions=[
                {"when": "code LIKE '1%'", "patient_class": "first"},
                {"when": "code LIKE '11%'", "patient_class": "second"},
            ]
        )
        resolver = PatientClassResolver(rules)
        result = resolver.resolve({"code": "111"})
        assert result == "first"

    def test_missing_field_in_record_returns_none(self) -> None:
        """If the field referenced in the condition is not in the record, returns None."""
        resolver = PatientClassResolver(_make_rules())
        record = {"some_other_field": "111"}
        result = resolver.resolve(record)
        assert result is None

    def test_none_field_value_returns_none(self) -> None:
        """If the field value is None, returns None."""
        resolver = PatientClassResolver(_make_rules())
        record = {"bill_type_code": None}
        result = resolver.resolve(record)
        assert result is None

    def test_equality_condition(self) -> None:
        """Supports equality conditions: field = 'value'."""
        rules = PatientClassRules(
            conditions=[
                {"when": "status = 'active'", "patient_class": "inpatient"},
            ]
        )
        resolver = PatientClassResolver(rules)
        assert resolver.resolve({"status": "active"}) == "inpatient"
        assert resolver.resolve({"status": "inactive"}) is None

    def test_in_condition(self) -> None:
        """Supports IN conditions: field IN ('v1', 'v2')."""
        rules = PatientClassRules(
            conditions=[
                {"when": "code IN ('IP', 'INP')", "patient_class": "inpatient"},
            ]
        )
        resolver = PatientClassResolver(rules)
        assert resolver.resolve({"code": "IP"}) == "inpatient"
        assert resolver.resolve({"code": "INP"}) == "inpatient"
        assert resolver.resolve({"code": "OP"}) is None

    def test_empty_conditions_returns_none(self) -> None:
        """No conditions configured -> always returns None."""
        rules = PatientClassRules(conditions=[])
        resolver = PatientClassResolver(rules)
        assert resolver.resolve({"bill_type_code": "111"}) is None
