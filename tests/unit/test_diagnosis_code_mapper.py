"""Tests for DiagnosisCodeMapper — maps source diagnosis fields to DiagnosisCode objects."""

from __future__ import annotations

import json
from typing import Any

from asre.canonicalize.diagnosis_mapper import DiagnosisCodeMapper
from asre.config.source_schema import FieldMappings
from asre.models.diagnosis import DiagnosisCode


def _make_field_mappings(**overrides: Any) -> FieldMappings:
    """Create a FieldMappings with required fields and optional overrides."""
    defaults: dict[str, Any] = {
        "patient_key": "member_id",
        "event_ts": "admission_date",
        "source_record_id": "claim_id",
        "facility_raw": "facility_name",
    }
    defaults.update(overrides)
    return FieldMappings(**defaults)


class TestPrincipalDiagnosis:
    """Test mapping of principal_diagnosis field."""

    def test_maps_principal_diagnosis_from_source(self) -> None:
        fm = _make_field_mappings(principal_diagnosis="primary_dx")
        mapper = DiagnosisCodeMapper(fm)
        record = {"primary_dx": "J18.9"}

        result = mapper.map_principal_diagnosis(record)

        assert result == "J18.9"

    def test_returns_none_when_not_configured(self) -> None:
        fm = _make_field_mappings(principal_diagnosis=None)
        mapper = DiagnosisCodeMapper(fm)
        record = {"primary_dx": "J18.9"}

        result = mapper.map_principal_diagnosis(record)

        assert result is None

    def test_returns_none_when_source_value_missing(self) -> None:
        fm = _make_field_mappings(principal_diagnosis="primary_dx")
        mapper = DiagnosisCodeMapper(fm)
        record: dict[str, Any] = {}

        result = mapper.map_principal_diagnosis(record)

        assert result is None

    def test_returns_none_when_source_value_is_none(self) -> None:
        fm = _make_field_mappings(principal_diagnosis="primary_dx")
        mapper = DiagnosisCodeMapper(fm)
        record: dict[str, Any] = {"primary_dx": None}

        result = mapper.map_principal_diagnosis(record)

        assert result is None


class TestAdmittingDiagnosis:
    """Test mapping of admitting_diagnosis field."""

    def test_maps_admitting_diagnosis_from_source(self) -> None:
        fm = _make_field_mappings(admitting_diagnosis="admit_dx")
        mapper = DiagnosisCodeMapper(fm)
        record = {"admit_dx": "R07.9"}

        result = mapper.map_admitting_diagnosis(record)

        assert result == "R07.9"

    def test_returns_none_when_not_configured(self) -> None:
        fm = _make_field_mappings(admitting_diagnosis=None)
        mapper = DiagnosisCodeMapper(fm)
        record = {"admit_dx": "R07.9"}

        result = mapper.map_admitting_diagnosis(record)

        assert result is None

    def test_returns_none_when_source_value_missing(self) -> None:
        fm = _make_field_mappings(admitting_diagnosis="admit_dx")
        mapper = DiagnosisCodeMapper(fm)
        record: dict[str, Any] = {}

        result = mapper.map_admitting_diagnosis(record)

        assert result is None


class TestDiagnosisCodesJsonArray:
    """Test mapping diagnosis_codes from JSON array format."""

    def test_parses_json_array_of_code_strings(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": '["J18.9", "R06.0", "J96.01"]'}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 3
        assert result[0].code == "J18.9"
        assert result[1].code == "R06.0"
        assert result[2].code == "J96.01"

    def test_json_array_codes_have_icd10_type(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": '["J18.9"]'}

        result = mapper.map_diagnosis_codes(record)

        assert result[0].type == "ICD-10-CM"

    def test_json_array_codes_have_sequential_sequence(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": '["J18.9", "R06.0"]'}

        result = mapper.map_diagnosis_codes(record)

        assert result[0].sequence == 1
        assert result[1].sequence == 2

    def test_parses_json_array_of_objects(self) -> None:
        """Handle JSON array with full DiagnosisCode objects."""
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        codes = [
            {"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"},
            {"code": "R06.0", "type": "ICD-10-CM", "sequence": 2, "poa": "N"},
        ]
        record = {"all_diagnosis_codes": json.dumps(codes)}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 2
        assert result[0].code == "J18.9"
        assert result[0].poa == "Y"
        assert result[1].code == "R06.0"
        assert result[1].poa == "N"

    def test_handles_native_list_input(self) -> None:
        """When the source returns a Python list (not JSON string)."""
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record: dict[str, Any] = {"all_diagnosis_codes": ["J18.9", "R06.0"]}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 2
        assert result[0].code == "J18.9"
        assert result[1].code == "R06.0"


class TestDiagnosisCodesDelimitedString:
    """Test mapping diagnosis_codes from delimited string format."""

    def test_parses_comma_delimited_string(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9,R06.0,J96.01"}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 3
        assert result[0].code == "J18.9"
        assert result[1].code == "R06.0"
        assert result[2].code == "J96.01"

    def test_parses_semicolon_delimited_string(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9;R06.0;J96.01"}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 3
        assert result[0].code == "J18.9"

    def test_parses_pipe_delimited_string(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9|R06.0"}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 2
        assert result[0].code == "J18.9"
        assert result[1].code == "R06.0"

    def test_strips_whitespace_from_delimited_codes(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9, R06.0, J96.01"}

        result = mapper.map_diagnosis_codes(record)

        assert result[0].code == "J18.9"
        assert result[1].code == "R06.0"
        assert result[2].code == "J96.01"

    def test_delimited_codes_have_icd10_type(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9,R06.0"}

        result = mapper.map_diagnosis_codes(record)

        assert all(c.type == "ICD-10-CM" for c in result)

    def test_delimited_codes_have_sequential_sequence(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9,R06.0"}

        result = mapper.map_diagnosis_codes(record)

        assert result[0].sequence == 1
        assert result[1].sequence == 2


class TestDiagnosisCodesEdgeCases:
    """Edge cases for diagnosis_codes mapping."""

    def test_returns_empty_list_when_not_configured(self) -> None:
        fm = _make_field_mappings(diagnosis_codes=None)
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9"}

        result = mapper.map_diagnosis_codes(record)

        assert result == []

    def test_returns_empty_list_when_source_value_missing(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record: dict[str, Any] = {}

        result = mapper.map_diagnosis_codes(record)

        assert result == []

    def test_returns_empty_list_when_source_value_none(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record: dict[str, Any] = {"all_diagnosis_codes": None}

        result = mapper.map_diagnosis_codes(record)

        assert result == []

    def test_returns_empty_list_when_source_value_empty_string(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": ""}

        result = mapper.map_diagnosis_codes(record)

        assert result == []

    def test_single_code_string_no_delimiter(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9"}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 1
        assert result[0].code == "J18.9"
        assert result[0].sequence == 1

    def test_filters_out_empty_codes_from_delimited(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": "J18.9,,R06.0,"}

        result = mapper.map_diagnosis_codes(record)

        assert len(result) == 2
        assert result[0].code == "J18.9"
        assert result[1].code == "R06.0"


class TestToSerializableFormat:
    """Test conversion of DiagnosisCode list to serializable format for CanonicalEvent."""

    def test_converts_to_list_of_dicts(self) -> None:
        fm = _make_field_mappings(diagnosis_codes="all_diagnosis_codes")
        mapper = DiagnosisCodeMapper(fm)
        record = {"all_diagnosis_codes": '["J18.9", "R06.0"]'}

        codes = mapper.map_diagnosis_codes(record)
        serialized = DiagnosisCodeMapper.to_serializable(codes)

        assert len(serialized) == 2
        assert serialized[0] == {"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": None}
        assert serialized[1] == {"code": "R06.0", "type": "ICD-10-CM", "sequence": 2, "poa": None}

    def test_empty_list_returns_none(self) -> None:
        """CanonicalEvent.diagnosis_codes is None when no codes present."""
        result = DiagnosisCodeMapper.to_serializable([])

        assert result is None
