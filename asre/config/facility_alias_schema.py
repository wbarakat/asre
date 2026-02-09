"""Facility alias config Pydantic schema (SPEC §7.4)."""

from __future__ import annotations

from pydantic import BaseModel


class FacilityAlias(BaseModel):
    """A canonical facility with known name variants, identifiers, and type."""

    canonical_id: str
    canonical_name: str
    npi: str | None = None
    ccn: str | None = None
    facility_type: str | None = None
    aliases: list[str] = []
    address: str | None = None


class FacilityAliasConfig(BaseModel):
    """Top-level facility alias configuration containing a list of facilities."""

    facilities: list[FacilityAlias] = []
