"""DiagnosisCode model for structured diagnosis code representation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DiagnosisCode:
    """A structured diagnosis code used across canonical events and encounters.

    Supports round-trip serialization to/from dict for JSON/VARIANT storage.
    """

    code: str
    type: str
    sequence: int | None = None
    poa: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON/VARIANT column storage."""
        return {
            "code": self.code,
            "type": self.type,
            "sequence": self.sequence,
            "poa": self.poa,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagnosisCode:
        """Deserialize from dict."""
        return cls(
            code=data["code"],
            type=data["type"],
            sequence=data.get("sequence"),
            poa=data.get("poa"),
        )
