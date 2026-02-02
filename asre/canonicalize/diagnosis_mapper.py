"""Diagnosis code mapper — maps source diagnosis fields to DiagnosisCode objects."""

from __future__ import annotations

import json
import re
from typing import Any

from asre.config.source_schema import FieldMappings
from asre.models.diagnosis import DiagnosisCode


class DiagnosisCodeMapper:
    """Maps source diagnosis fields to structured DiagnosisCode objects.

    Handles:
    - principal_diagnosis: single string field mapping
    - admitting_diagnosis: single string field mapping
    - diagnosis_codes: JSON array (strings or objects) or delimited string (comma, semicolon, pipe)
    """

    def __init__(self, field_mappings: FieldMappings) -> None:
        self.field_mappings = field_mappings

    def map_principal_diagnosis(self, record: dict[str, Any]) -> str | None:
        """Map principal_diagnosis from source record."""
        return self._get_optional(record, self.field_mappings.principal_diagnosis)

    def map_admitting_diagnosis(self, record: dict[str, Any]) -> str | None:
        """Map admitting_diagnosis from source record."""
        return self._get_optional(record, self.field_mappings.admitting_diagnosis)

    def map_diagnosis_codes(self, record: dict[str, Any]) -> list[DiagnosisCode]:
        """Map diagnosis_codes from source record.

        Handles:
        - JSON array of strings: '["J18.9", "R06.0"]'
        - JSON array of objects: '[{"code": "J18.9", "type": "ICD-10-CM", ...}]'
        - Native Python list (already parsed by adapter)
        - Delimited string (comma, semicolon, pipe): "J18.9,R06.0,J96.01"
        """
        mapping_field = self.field_mappings.diagnosis_codes
        if mapping_field is None:
            return []

        raw_value = record.get(mapping_field)
        if raw_value is None:
            return []

        # Native list (already parsed by adapter)
        if isinstance(raw_value, list):
            return self._parse_list(raw_value)

        raw_str = str(raw_value).strip()
        if not raw_str:
            return []

        # Try JSON parse first
        if raw_str.startswith("["):
            try:
                parsed = json.loads(raw_str)
                if isinstance(parsed, list):
                    return self._parse_list(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        # Fall back to delimited string
        return self._parse_delimited(raw_str)

    @staticmethod
    def to_serializable(codes: list[DiagnosisCode]) -> list[dict[str, Any]] | None:
        """Convert DiagnosisCode list to serializable format for CanonicalEvent.diagnosis_codes.

        Returns None when no codes present (matches CanonicalEvent field semantics).
        """
        if not codes:
            return None
        return [c.to_dict() for c in codes]

    @staticmethod
    def _parse_list(items: list[Any]) -> list[DiagnosisCode]:
        """Parse a list of strings or dicts into DiagnosisCode objects."""
        codes: list[DiagnosisCode] = []
        for i, item in enumerate(items):
            if isinstance(item, dict):
                codes.append(DiagnosisCode.from_dict(item))
            else:
                code_str = str(item).strip()
                if code_str:
                    codes.append(DiagnosisCode(
                        code=code_str,
                        type="ICD-10-CM",
                        sequence=i + 1,
                    ))
        return codes

    @staticmethod
    def _parse_delimited(raw_str: str) -> list[DiagnosisCode]:
        """Parse a delimited string into DiagnosisCode objects."""
        parts = re.split(r"[,;|]", raw_str)
        codes: list[DiagnosisCode] = []
        seq = 1
        for part in parts:
            code_str = part.strip()
            if code_str:
                codes.append(DiagnosisCode(
                    code=code_str,
                    type="ICD-10-CM",
                    sequence=seq,
                ))
                seq += 1
        return codes

    @staticmethod
    def _get_optional(record: dict[str, Any], mapping_field: str | None) -> str | None:
        """Get an optional field value from the record using the mapping."""
        if mapping_field is None:
            return None
        val = record.get(mapping_field)
        if val is None:
            return None
        return str(val)
