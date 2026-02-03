"""Condition grouper dispatcher — DRG rules first, AHRQ CCS fallback (US-092).

Provides a simple function interface that creates and delegates to the
AHRQCCSGrouper, which internally checks DRG rules before ICD-10 classification.
"""

from __future__ import annotations

from asre.groupers.ahrq_ccs import AHRQCCSGrouper

# Module-level singleton to avoid repeated instantiation.
_DEFAULT_GROUPER = AHRQCCSGrouper()


def classify_episode_type(
    diagnosis_codes: list[dict[str, str | None]],
    drg: str | None,
) -> str:
    """Classify an episode type from diagnosis codes and DRG.

    Dispatches to AHRQCCSGrouper which checks DRG rules first,
    then falls back to AHRQ CCS ICD-10 classification.

    Returns one of: surgical, medical, chronic_exacerbation,
    maternity, behavioral_health, unclassified.
    """
    return _DEFAULT_GROUPER.group(diagnosis_codes, drg)
