"""Facility name string normalization pipeline.

Pipeline steps (in order):
1. Uppercase
2. Strip punctuation
3. Expand abbreviations
4. Remove generic trailing suffixes
5. Normalize whitespace
"""

from __future__ import annotations

import re


# Default abbreviation expansions per SPEC §7.2
DEFAULT_ABBREVIATIONS: dict[str, str] = {
    "MED CTR": "MEDICAL CENTER",
    "MED": "MEDICAL",
    "CTR": "CENTER",
    "HOSP": "HOSPITAL",
    "HLTH": "HEALTH",
    "SYS": "SYSTEM",
    "SURG": "SURGERY",
    "REHAB": "REHABILITATION",
    "COMM": "COMMUNITY",
    "UNIV": "UNIVERSITY",
    "NATL": "NATIONAL",
    "REGL": "REGIONAL",
    "GEN": "GENERAL",
    "GOVT": "GOVERNMENT",
    "DEPT": "DEPARTMENT",
    "ASSOC": "ASSOCIATES",
    "SVCS": "SERVICES",
    "SVC": "SERVICE",
    "CNTY": "COUNTY",
    "DIST": "DISTRICT",
    "PKY": "PARKWAY",
    "BLVD": "BOULEVARD",
    "AVE": "AVENUE",
    "MT": "MOUNT",
    "FT": "FORT",
}

# Trailing generic suffixes to remove (order matters: longer phrases first)
GENERIC_SUFFIXES: list[str] = [
    "MEDICAL CENTER",
    "HEALTH SYSTEM",
    "HEALTH CENTER",
    "HOSPITAL",
    "HEALTH",
    "CLINIC",
    "CENTER",
]

# Tokens to preserve (directional + campus)
PRESERVED_DIRECTIONAL: set[str] = {"EAST", "WEST", "NORTH", "SOUTH"}
PRESERVED_CAMPUS: set[str] = {"MAIN", "DOWNTOWN", "CAMPUS", "MIDTOWN", "UPTOWN"}


class FacilityNormalizer:
    """Normalizes facility name strings for matching.

    Pipeline: uppercase -> strip punctuation -> expand abbreviations
    -> remove generic suffixes -> normalize whitespace.
    """

    def __init__(
        self,
        abbreviations: dict[str, str] | None = None,
    ) -> None:
        self._abbreviations = abbreviations if abbreviations is not None else DEFAULT_ABBREVIATIONS

    def normalize(self, name: str | None) -> str:
        """Normalize a facility name string.

        Args:
            name: Raw facility name string.

        Returns:
            Normalized facility name string.
        """
        if not name or not name.strip():
            return ""

        result = name

        # Step 1: Uppercase
        result = result.upper()

        # Step 2: Strip punctuation (apostrophes, periods, hyphens, commas)
        result = re.sub(r"[.'`,]", "", result)
        result = result.replace("-", " ")

        # Step 3: Normalize whitespace (interim, before abbreviation matching)
        result = re.sub(r"\s+", " ", result).strip()

        # Step 4: Expand abbreviations (multi-word first, then single-word)
        result = self._expand_abbreviations(result)

        # Step 5: Remove generic trailing suffixes
        result = self._remove_generic_suffixes(result)

        # Step 6: Final whitespace normalization
        result = re.sub(r"\s+", " ", result).strip()

        return result

    def _expand_abbreviations(self, text: str) -> str:
        """Expand known abbreviations at word boundaries.

        Multi-word abbreviations (e.g., 'MED CTR') are expanded first,
        then single-word abbreviations.
        """
        # Sort by number of words descending (multi-word first), then by length
        sorted_abbrevs = sorted(
            self._abbreviations.items(),
            key=lambda x: (-len(x[0].split()), -len(x[0])),
        )

        for abbrev, expansion in sorted_abbrevs:
            # Word boundary match to avoid partial replacements
            pattern = r"\b" + re.escape(abbrev) + r"\b"
            text = re.sub(pattern, expansion, text)

        return text

    def _remove_generic_suffixes(self, text: str) -> str:
        """Remove generic organizational suffixes.

        Removes suffixes whether trailing or followed only by preserved
        directional/campus tokens. Does not remove if the core name
        would become empty.
        """
        all_preserved = PRESERVED_DIRECTIONAL | PRESERVED_CAMPUS
        words = text.split()

        # Collect trailing preserved tokens
        trailing_preserved: list[str] = []
        core_words = list(words)
        while core_words and core_words[-1] in all_preserved:
            trailing_preserved.insert(0, core_words.pop())

        # Try to remove suffix from core words
        core_text = " ".join(core_words)
        for suffix in GENERIC_SUFFIXES:
            if core_text.endswith(suffix):
                candidate = core_text[: -len(suffix)].strip()
                if candidate:
                    core_text = candidate
                    break

        # Reassemble with preserved trailing tokens
        parts = [core_text] + trailing_preserved if trailing_preserved else [core_text]
        return " ".join(parts)
