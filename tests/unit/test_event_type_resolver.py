"""Tests for EventTypeResolver."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asre.canonicalize.event_type_resolver import EventTypeResolver
from asre.config.source_schema import EventTypeRules
from asre.models.canonical_event import CanonicalEvent


def _make_event(event_type: str = "UNKNOWN") -> CanonicalEvent:
    """Create a minimal CanonicalEvent for testing."""
    return CanonicalEvent(
        event_id="test-id",
        patient_key="PAT001",
        event_type=event_type,
        event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="SRC001",
        facility_raw="TEST HOSPITAL",
        ingested_at=datetime.now(timezone.utc),
        batch_id="batch-001",
    )


def _make_adt_rules() -> EventTypeRules:
    """Create ADT event type rules matching the test customer config."""
    return EventTypeRules(
        source_field="hl7_event",
        mappings={
            "A01": "ADMIT",
            "A02": "TRANSFER_IN",
            "A03": "DISCHARGE",
            "A04": "REGISTRATION",
            "A05": "PRE_ADMIT",
            "A06": "OBS_TO_IP",
            "A07": "TRANSFER_OUT",
            "A11": "CANCEL_ADMIT",
            "A12": "CANCEL_TRANSFER",
            "A13": "CANCEL_DISCHARGE",
        },
        conditional_mappings=[
            {"when": "hl7_event == 'A01' AND patient_class == 'E'", "event_type": "ED_ARRIVAL"},
            {"when": "hl7_event == 'A01' AND patient_class == 'O'", "event_type": "OBS_START"},
            {"when": "hl7_event == 'A03' AND patient_class == 'E'", "event_type": "ED_DEPARTURE"},
            {"when": "hl7_event == 'A03' AND patient_class == 'O'", "event_type": "OBS_END"},
        ],
        admit_flag_expression="event_type IN ('ADMIT', 'ED_ARRIVAL', 'OBS_START', 'TRANSFER_IN')",
        discharge_flag_expression="event_type IN ('DISCHARGE', 'ED_DEPARTURE', 'OBS_END', 'TRANSFER_OUT')",
    )


class TestEventTypeResolverConstruction:
    """Tests for EventTypeResolver construction."""

    def test_construction(self) -> None:
        rules = _make_adt_rules()
        resolver = EventTypeResolver(rules)
        assert resolver.rules is rules

    def test_stores_rules_reference(self) -> None:
        rules = _make_adt_rules()
        resolver = EventTypeResolver(rules)
        assert resolver.rules.source_field == "hl7_event"


class TestDirectMappings:
    """Tests for direct HL7 code to event type mapping."""

    def test_a01_inpatient_admit(self) -> None:
        """A01 with patient_class=I -> ADMIT (direct mapping, no conditional match)."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "ADMIT"

    def test_a02_transfer_in(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A02", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "TRANSFER_IN"

    def test_a03_discharge(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "DISCHARGE"

    def test_a04_registration(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A04", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "REGISTRATION"

    def test_a05_pre_admit(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A05", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "PRE_ADMIT"

    def test_a06_obs_to_ip(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A06", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "OBS_TO_IP"

    def test_a07_transfer_out(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A07", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "TRANSFER_OUT"

    def test_a11_cancel_admit(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A11", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "CANCEL_ADMIT"

    def test_a12_cancel_transfer(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A12", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "CANCEL_TRANSFER"

    def test_a13_cancel_discharge(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A13", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "CANCEL_DISCHARGE"

    def test_unknown_hl7_code(self) -> None:
        """Unknown HL7 code falls back to UNKNOWN."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A99", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "UNKNOWN"


class TestConditionalMappings:
    """Tests for conditional mappings (HL7 code + patient class)."""

    def test_a01_ed_arrival(self) -> None:
        """A01 + patient_class=E -> ED_ARRIVAL."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "E"}
        result = resolver.resolve(event, record)
        assert result.event_type == "ED_ARRIVAL"

    def test_a01_obs_start(self) -> None:
        """A01 + patient_class=O -> OBS_START."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "O"}
        result = resolver.resolve(event, record)
        assert result.event_type == "OBS_START"

    def test_a03_ed_departure(self) -> None:
        """A03 + patient_class=E -> ED_DEPARTURE."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "E"}
        result = resolver.resolve(event, record)
        assert result.event_type == "ED_DEPARTURE"

    def test_a03_obs_end(self) -> None:
        """A03 + patient_class=O -> OBS_END."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "O"}
        result = resolver.resolve(event, record)
        assert result.event_type == "OBS_END"

    def test_conditional_takes_precedence_over_direct(self) -> None:
        """Conditional mappings are checked before direct mappings."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        # A01 would map to ADMIT directly, but E patient_class overrides to ED_ARRIVAL
        record = {"hl7_event": "A01", "patient_class": "E"}
        result = resolver.resolve(event, record)
        assert result.event_type == "ED_ARRIVAL"
        assert result.event_type != "ADMIT"

    def test_first_matching_conditional_wins(self) -> None:
        """First matching conditional is used (order matters)."""
        # Create rules where two conditionals could match
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"A01": "ADMIT"},
            conditional_mappings=[
                {"when": "hl7_event == 'A01'", "event_type": "FIRST_MATCH"},
                {"when": "hl7_event == 'A01'", "event_type": "SECOND_MATCH"},
            ],
        )
        resolver = EventTypeResolver(rules)
        event = _make_event()
        record = {"hl7_event": "A01"}
        result = resolver.resolve(event, record)
        assert result.event_type == "FIRST_MATCH"


class TestAdmitFlag:
    """Tests for admit_flag resolution."""

    def test_admit_sets_admit_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.admit_flag is True

    def test_ed_arrival_sets_admit_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "E"}
        result = resolver.resolve(event, record)
        assert result.admit_flag is True

    def test_obs_start_sets_admit_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "O"}
        result = resolver.resolve(event, record)
        assert result.admit_flag is True

    def test_transfer_in_sets_admit_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A02", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.admit_flag is True

    def test_discharge_does_not_set_admit_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.admit_flag is False


class TestDischargeFlag:
    """Tests for discharge_flag resolution."""

    def test_discharge_sets_discharge_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.discharge_flag is True

    def test_ed_departure_sets_discharge_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "E"}
        result = resolver.resolve(event, record)
        assert result.discharge_flag is True

    def test_obs_end_sets_discharge_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A03", "patient_class": "O"}
        result = resolver.resolve(event, record)
        assert result.discharge_flag is True

    def test_transfer_out_sets_discharge_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A07", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.discharge_flag is True

    def test_admit_does_not_set_discharge_flag(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.discharge_flag is False


class TestEdgeCases:
    """Tests for edge cases and fallbacks."""

    def test_missing_source_field_returns_unchanged(self) -> None:
        """If the source field is missing from the record, event_type stays UNKNOWN."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"patient_class": "I"}  # no hl7_event
        result = resolver.resolve(event, record)
        assert result.event_type == "UNKNOWN"

    def test_none_source_field_returns_unchanged(self) -> None:
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": None, "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "UNKNOWN"

    def test_no_conditional_mappings(self) -> None:
        """Rules without conditional mappings use only direct mappings."""
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"A01": "ADMIT", "A03": "DISCHARGE"},
        )
        resolver = EventTypeResolver(rules)
        event = _make_event()
        record = {"hl7_event": "A01"}
        result = resolver.resolve(event, record)
        assert result.event_type == "ADMIT"

    def test_no_flag_expressions_defaults_false(self) -> None:
        """When no flag expressions are configured, both flags are False."""
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"A01": "ADMIT"},
        )
        resolver = EventTypeResolver(rules)
        event = _make_event()
        record = {"hl7_event": "A01"}
        result = resolver.resolve(event, record)
        assert result.admit_flag is False
        assert result.discharge_flag is False

    def test_event_is_mutated_in_place(self) -> None:
        """resolve() mutates the event object and returns it."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": "A01", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result is event
        assert event.event_type == "ADMIT"

    def test_whitespace_in_source_code(self) -> None:
        """Source code with whitespace is stripped before lookup."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        record = {"hl7_event": " A01 ", "patient_class": "I"}
        result = resolver.resolve(event, record)
        assert result.event_type == "ADMIT"

    def test_conditional_with_missing_record_field(self) -> None:
        """Conditional referencing a missing field does not match."""
        resolver = EventTypeResolver(_make_adt_rules())
        event = _make_event()
        # A01 conditional checks patient_class, but it's missing
        record = {"hl7_event": "A01"}
        result = resolver.resolve(event, record)
        # No conditional matches, falls through to direct mapping
        assert result.event_type == "ADMIT"


class TestEvaluateCondition:
    """Tests for the static _evaluate_condition method."""

    def test_simple_equality(self) -> None:
        assert EventTypeResolver._evaluate_condition(
            "field == 'value'", {"field": "value"}
        ) is True

    def test_equality_mismatch(self) -> None:
        assert EventTypeResolver._evaluate_condition(
            "field == 'value'", {"field": "other"}
        ) is False

    def test_and_condition(self) -> None:
        assert EventTypeResolver._evaluate_condition(
            "a == '1' AND b == '2'", {"a": "1", "b": "2"}
        ) is True

    def test_and_condition_partial_match(self) -> None:
        assert EventTypeResolver._evaluate_condition(
            "a == '1' AND b == '2'", {"a": "1", "b": "3"}
        ) is False

    def test_empty_expression(self) -> None:
        assert EventTypeResolver._evaluate_condition("", {}) is False

    def test_missing_field_in_record(self) -> None:
        assert EventTypeResolver._evaluate_condition(
            "field == 'value'", {}
        ) is False


class TestEvaluateFlag:
    """Tests for the static _evaluate_flag method."""

    def test_in_expression_match(self) -> None:
        assert EventTypeResolver._evaluate_flag(
            "event_type IN ('ADMIT', 'DISCHARGE')", "ADMIT"
        ) is True

    def test_in_expression_no_match(self) -> None:
        assert EventTypeResolver._evaluate_flag(
            "event_type IN ('ADMIT', 'DISCHARGE')", "TRANSFER_IN"
        ) is False

    def test_none_expression(self) -> None:
        assert EventTypeResolver._evaluate_flag(None, "ADMIT") is False

    def test_empty_expression(self) -> None:
        assert EventTypeResolver._evaluate_flag("", "ADMIT") is False
