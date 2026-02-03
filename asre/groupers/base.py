"""ConditionGrouper ABC — pluggable interface for episode type classification (US-091).

Implementers map diagnosis codes and/or DRG to an episode type category.
Return values: surgical, medical, chronic_exacerbation, maternity,
behavioral_health, unclassified.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ConditionGrouper(ABC):
    """Abstract base class for episode type classification.

    Subclasses must implement ``group()`` which maps diagnosis codes and/or
    DRG to one of the defined episode type categories.
    """

    VALID_EPISODE_TYPES = frozenset(
        {
            "surgical",
            "medical",
            "chronic_exacerbation",
            "maternity",
            "behavioral_health",
            "unclassified",
        }
    )

    @abstractmethod
    def group(
        self,
        diagnosis_codes: list[dict[str, str | None]],
        drg: str | None,
    ) -> str:
        """Classify an episode based on diagnosis codes and DRG.

        Args:
            diagnosis_codes: List of diagnosis code dicts, each with keys
                ``code``, ``type``, ``sequence``, ``poa``.
            drg: DRG code string, or None if unavailable.

        Returns:
            One of: surgical, medical, chronic_exacerbation, maternity,
            behavioral_health, unclassified.
        """
        ...
