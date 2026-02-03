"""Tests for ConditionGrouper ABC (US-091)."""

from __future__ import annotations

import pytest

from asre.groupers.base import ConditionGrouper


class TestConditionGrouperInterface:
    """Verify the ConditionGrouper ABC cannot be instantiated directly."""

    def test_cannot_instantiate_directly(self) -> None:
        """ConditionGrouper is abstract and should not be instantiated."""
        with pytest.raises(TypeError):
            ConditionGrouper()  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        """A concrete subclass implementing group() can be instantiated."""

        class _StubGrouper(ConditionGrouper):
            def group(
                self,
                diagnosis_codes: list[dict[str, str | None]],
                drg: str | None,
            ) -> str:
                return "unclassified"

        grouper = _StubGrouper()
        result = grouper.group([], None)
        assert result == "unclassified"

    def test_subclass_must_implement_group(self) -> None:
        """A subclass that does not implement group() cannot be instantiated."""

        class _IncompleteGrouper(ConditionGrouper):
            pass

        with pytest.raises(TypeError):
            _IncompleteGrouper()  # type: ignore[abstract]

    def test_valid_episode_types(self) -> None:
        """VALID_EPISODE_TYPES contains all expected classification categories."""
        expected = {
            "surgical",
            "medical",
            "chronic_exacerbation",
            "maternity",
            "behavioral_health",
            "unclassified",
        }
        assert ConditionGrouper.VALID_EPISODE_TYPES == expected

    def test_group_with_diagnosis_codes(self) -> None:
        """Concrete grouper receives diagnosis codes and DRG correctly."""

        class _DiagGrouper(ConditionGrouper):
            def group(
                self,
                diagnosis_codes: list[dict[str, str | None]],
                drg: str | None,
            ) -> str:
                if drg and drg.startswith("4"):
                    return "surgical"
                if diagnosis_codes:
                    return "medical"
                return "unclassified"

        grouper = _DiagGrouper()

        # DRG-based classification
        assert grouper.group([], "470") == "surgical"

        # Diagnosis-based classification
        codes: list[dict[str, str | None]] = [
            {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
        ]
        assert grouper.group(codes, None) == "medical"

        # Fallback
        assert grouper.group([], None) == "unclassified"
