"""Event type resolver - maps HL7 events + patient class to canonical event types."""

from __future__ import annotations

from typing import Any

from asre.config.source_schema import EventTypeRules
from asre.models.canonical_event import CanonicalEvent


# All 16 canonical event types per SPEC §3.3
VALID_EVENT_TYPES = {
    "ADMIT",
    "DISCHARGE",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "ED_ARRIVAL",
    "ED_DEPARTURE",
    "OBS_START",
    "OBS_END",
    "OBS_TO_IP",
    "REGISTRATION",
    "PRE_ADMIT",
    "CANCEL_ADMIT",
    "CANCEL_DISCHARGE",
    "CANCEL_TRANSFER",
    "CLAIM_ADMIT",
    "CLAIM_DISCHARGE",
    "AUTH_REQUESTED",
    "AUTH_APPROVED",
    "AUTH_DENIED",
    "UNKNOWN",
}


class EventTypeResolver:
    """Resolves HL7 event codes + patient class into canonical ASRE event types.

    Resolution order:
    1. Conditional mappings (checked in order, first match wins)
    2. Direct mappings (HL7 code -> event type)
    3. Falls back to "UNKNOWN" if no match

    Also sets admit_flag and discharge_flag based on configured expressions.
    """

    def __init__(self, event_type_rules: EventTypeRules) -> None:
        self.rules = event_type_rules

    def resolve(self, event: CanonicalEvent, raw_record: dict[str, Any]) -> CanonicalEvent:
        """Resolve event_type, admit_flag, and discharge_flag on a CanonicalEvent.

        Args:
            event: CanonicalEvent with event_type="UNKNOWN" from FieldMapper.
            raw_record: Original raw record dict for evaluating conditional expressions.

        Returns:
            The same CanonicalEvent with event_type, admit_flag, discharge_flag set.
        """
        source_value = raw_record.get(self.rules.source_field)
        if source_value is None:
            return event

        source_code = str(source_value).strip()

        # 1. Check conditional mappings first (order matters, first match wins)
        for condition in self.rules.conditional_mappings:
            when_expr = condition.get("when", "")
            if self._evaluate_condition(when_expr, raw_record):
                event.event_type = condition.get("event_type", "UNKNOWN")
                break
        else:
            # 2. Fall back to direct mapping
            event.event_type = self.rules.mappings.get(source_code, "UNKNOWN")

        # 3. Set admit_flag and discharge_flag
        event.admit_flag = self._evaluate_flag(
            self.rules.admit_flag_expression, event.event_type
        )
        event.discharge_flag = self._evaluate_flag(
            self.rules.discharge_flag_expression, event.event_type
        )

        return event

    @staticmethod
    def _evaluate_condition(when_expr: str, record: dict[str, Any]) -> bool:
        """Evaluate a conditional mapping expression against a raw record.

        Supports simple expressions like:
        - "field == 'value'"
        - "field == 'value' AND other_field == 'value2'"

        This is a safe evaluator that only handles == comparisons with AND logic.
        """
        if not when_expr:
            return False

        # Split on AND and evaluate each clause
        clauses = [c.strip() for c in when_expr.split(" AND ")]
        for clause in clauses:
            if " == " not in clause:
                return False
            parts = clause.split(" == ", 1)
            if len(parts) != 2:
                return False
            field_name = parts[0].strip()
            expected_value = parts[1].strip().strip("'\"")
            actual_value = record.get(field_name)
            if actual_value is None or str(actual_value).strip() != expected_value:
                return False
        return True

    @staticmethod
    def _evaluate_flag(flag_expression: str | None, event_type: str) -> bool:
        """Evaluate a flag expression against the resolved event type.

        Supports expressions like:
        - "event_type IN ('ADMIT', 'ED_ARRIVAL', 'OBS_START', 'TRANSFER_IN')"

        Returns False if no expression configured.
        """
        if not flag_expression:
            return False

        # Parse "event_type IN ('VALUE1', 'VALUE2', ...)"
        expr = flag_expression.strip()
        if expr.startswith("event_type IN (") and expr.endswith(")"):
            values_str = expr[len("event_type IN ("):-1]
            values = [v.strip().strip("'\"") for v in values_str.split(",")]
            return event_type in values

        return False
