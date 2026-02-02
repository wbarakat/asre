"""Patient class resolver for claims sources.

Evaluates patient_class_rules conditions against raw records to derive
the patient_class value (e.g., inpatient, outpatient, ed) from bill type codes.
"""

from __future__ import annotations

import re
from typing import Any

from asre.config.source_schema import PatientClassRules


class PatientClassResolver:
    """Resolves patient_class from raw record using configured conditions.

    Conditions are evaluated in order. The first matching condition sets
    patient_class. If no condition matches, returns None.
    """

    def __init__(self, rules: PatientClassRules) -> None:
        self.rules = rules

    def resolve(self, record: dict[str, Any]) -> str | None:
        """Resolve patient_class from a raw record.

        Args:
            record: Raw record dict from ingest stage.

        Returns:
            Patient class string if a condition matches, None otherwise.
        """
        for condition in self.rules.conditions:
            when_expr = condition["when"]
            patient_class = condition["patient_class"]
            if self._evaluate_condition(when_expr, record):
                return str(patient_class)
        return None

    @staticmethod
    def _evaluate_condition(expression: str, record: dict[str, Any]) -> bool:
        """Evaluate a SQL-like condition expression against a record.

        Supports:
            - field LIKE 'pattern%' (prefix matching with %)
            - field = 'value' (equality)
            - field IN ('v1', 'v2') (membership)

        Args:
            expression: SQL-like condition string.
            record: Raw record dict.

        Returns:
            True if the condition matches.
        """
        expr = expression.strip()

        # LIKE pattern: field LIKE 'pattern'
        like_match = re.match(
            r"(\w+)\s+LIKE\s+'([^']*)'", expr, re.IGNORECASE
        )
        if like_match:
            field = like_match.group(1)
            pattern = like_match.group(2)
            value = record.get(field)
            if value is None:
                return False
            value_str = str(value)
            # Convert SQL LIKE pattern to simple prefix/suffix/contains check
            if pattern.endswith("%") and not pattern.startswith("%"):
                return value_str.startswith(pattern[:-1])
            if pattern.startswith("%") and not pattern.endswith("%"):
                return value_str.endswith(pattern[1:])
            if pattern.startswith("%") and pattern.endswith("%"):
                return pattern[1:-1] in value_str
            return value_str == pattern

        # IN pattern: field IN ('v1', 'v2')
        in_match = re.match(
            r"(\w+)\s+IN\s*\(([^)]+)\)", expr, re.IGNORECASE
        )
        if in_match:
            field = in_match.group(1)
            values_str = in_match.group(2)
            values = [v.strip().strip("'\"") for v in values_str.split(",")]
            value = record.get(field)
            if value is None:
                return False
            return str(value) in values

        # Equality: field = 'value'
        eq_match = re.match(
            r"(\w+)\s*=\s*'([^']*)'", expr
        )
        if eq_match:
            field = eq_match.group(1)
            expected = eq_match.group(2)
            value = record.get(field)
            if value is None:
                return False
            return str(value) == expected

        return False
