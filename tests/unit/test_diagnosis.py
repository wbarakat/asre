"""Tests for DiagnosisCode model."""

from asre.models.diagnosis import DiagnosisCode


class TestDiagnosisCode:
    def test_construct_with_all_fields(self) -> None:
        dx = DiagnosisCode(
            code="M17.11",
            type="ICD-10-CM",
            sequence=1,
            poa="Y",
        )
        assert dx.code == "M17.11"
        assert dx.type == "ICD-10-CM"
        assert dx.sequence == 1
        assert dx.poa == "Y"

    def test_optional_fields_default_to_none(self) -> None:
        dx = DiagnosisCode(code="J18.9", type="ICD-10-CM")
        assert dx.code == "J18.9"
        assert dx.type == "ICD-10-CM"
        assert dx.sequence is None
        assert dx.poa is None

    def test_to_dict(self) -> None:
        dx = DiagnosisCode(
            code="M17.11",
            type="ICD-10-CM",
            sequence=1,
            poa="Y",
        )
        result = dx.to_dict()
        assert result == {
            "code": "M17.11",
            "type": "ICD-10-CM",
            "sequence": 1,
            "poa": "Y",
        }

    def test_to_dict_with_none_fields(self) -> None:
        dx = DiagnosisCode(code="J18.9", type="ICD-10-CM")
        result = dx.to_dict()
        assert result == {
            "code": "J18.9",
            "type": "ICD-10-CM",
            "sequence": None,
            "poa": None,
        }

    def test_from_dict_full(self) -> None:
        data = {
            "code": "M17.11",
            "type": "ICD-10-CM",
            "sequence": 1,
            "poa": "Y",
        }
        dx = DiagnosisCode.from_dict(data)
        assert dx.code == "M17.11"
        assert dx.type == "ICD-10-CM"
        assert dx.sequence == 1
        assert dx.poa == "Y"

    def test_from_dict_partial(self) -> None:
        data = {"code": "J18.9", "type": "ICD-10-CM"}
        dx = DiagnosisCode.from_dict(data)
        assert dx.code == "J18.9"
        assert dx.type == "ICD-10-CM"
        assert dx.sequence is None
        assert dx.poa is None

    def test_round_trip_serialization(self) -> None:
        original = DiagnosisCode(
            code="Z87.39",
            type="ICD-10-CM",
            sequence=3,
            poa="N",
        )
        restored = DiagnosisCode.from_dict(original.to_dict())
        assert restored.code == original.code
        assert restored.type == original.type
        assert restored.sequence == original.sequence
        assert restored.poa == original.poa

    def test_round_trip_with_none_fields(self) -> None:
        original = DiagnosisCode(code="E11.9", type="ICD-10-CM")
        restored = DiagnosisCode.from_dict(original.to_dict())
        assert restored.code == original.code
        assert restored.type == original.type
        assert restored.sequence == original.sequence
        assert restored.poa == original.poa

    def test_field_types(self) -> None:
        dx = DiagnosisCode(
            code="M17.11",
            type="ICD-10-CM",
            sequence=1,
            poa="Y",
        )
        assert isinstance(dx.code, str)
        assert isinstance(dx.type, str)
        assert isinstance(dx.sequence, int)
        assert isinstance(dx.poa, str)

    def test_importable_from_models(self) -> None:
        """Verify the import path works as specified in acceptance criteria."""
        from asre.models.diagnosis import DiagnosisCode as DC
        assert DC is DiagnosisCode
