"""SQLite-backed NPI/CCN facility registry lookup.

Provides read-only lookups against a bundled SQLite database built from
NPPES + CMS POS data. Used as tier 2b/3b fallback in the facility
matching cascade (after config-based NPI/CCN, before fuzzy).
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from asre.config.facility_alias_schema import FacilityAlias

logger = logging.getLogger(__name__)

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS facilities (
    canonical_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    npi TEXT,
    ccn TEXT,
    facility_type TEXT,
    aliases TEXT,
    source TEXT,
    address TEXT
)
"""

_CREATE_NPI_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_npi ON facilities(npi) "
    "WHERE npi IS NOT NULL AND npi != ''"
)
_CREATE_CCN_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_ccn ON facilities(ccn) "
    "WHERE ccn IS NOT NULL AND ccn != ''"
)

_INSERT_SQL = (
    "INSERT OR REPLACE INTO facilities "
    "(canonical_id, canonical_name, npi, ccn, facility_type, aliases, source, address) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_COLS = (
    "canonical_id, canonical_name, npi, ccn, facility_type, aliases, address"
)

_BATCH_SIZE = 10_000


def build_sqlite_from_csv(csv_path: str | Path, db_path: str | Path) -> int:
    """Build a SQLite facility registry from a combined CSV.

    Streams the CSV row-by-row and bulk-inserts into SQLite.
    Composes the address field from address_line1/2, city, state, zip
    columns (same logic as registry_loader.py).

    Args:
        csv_path: Path to the combined facility registry CSV.
        db_path: Output path for the SQLite database.

    Returns:
        Number of rows inserted.
    """
    csv_path = Path(csv_path)
    db_path = Path(db_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing DB to build fresh
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(_CREATE_TABLE)

        batch: list[tuple[Any, ...]] = []
        total = 0

        with csv_path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                canonical_id = (row.get("canonical_id") or "").strip()
                canonical_name = (row.get("canonical_name") or "").strip()
                if not canonical_id or not canonical_name:
                    continue

                npi = (row.get("npi") or "").strip() or None
                ccn = (row.get("ccn") or "").strip() or None
                facility_type = (row.get("facility_type") or "").strip() or None
                aliases = (row.get("aliases") or "").strip() or None
                source = (row.get("source") or "").strip() or None
                address = _compose_address(row)

                batch.append((
                    canonical_id, canonical_name, npi, ccn,
                    facility_type, aliases, source, address,
                ))

                if len(batch) >= _BATCH_SIZE:
                    conn.executemany(_INSERT_SQL, batch)
                    total += len(batch)
                    batch.clear()

            if batch:
                conn.executemany(_INSERT_SQL, batch)
                total += len(batch)

        # Create indexes after bulk insert for speed
        conn.execute(_CREATE_NPI_INDEX)
        conn.execute(_CREATE_CCN_INDEX)
        conn.commit()

        logger.info("Built SQLite registry: %d rows at %s", total, db_path)
        return total
    finally:
        conn.close()


def _compose_address(row: dict[str, str]) -> str | None:
    """Compose address from CSV address columns."""
    parts: list[str] = []
    addr1 = (row.get("address_line1") or "").strip()
    addr2 = (row.get("address_line2") or "").strip()
    city = (row.get("city") or "").strip()
    state = (row.get("state") or "").strip()
    zip_code = (row.get("zip") or "").strip()

    if addr1:
        parts.append(addr1)
    if addr2:
        parts.append(addr2)
    city_state_zip = ", ".join(filter(None, [city, state]))
    if zip_code:
        city_state_zip = f"{city_state_zip} {zip_code}".strip()
    if city_state_zip:
        parts.append(city_state_zip)

    return ", ".join(parts) if parts else None


def _row_to_alias(row: tuple[Any, ...]) -> FacilityAlias:
    """Convert a SQLite row tuple to a FacilityAlias."""
    canonical_id, canonical_name, npi, ccn, facility_type, aliases_raw, address = row

    aliases: list[str] = []
    if aliases_raw:
        try:
            parsed = json.loads(aliases_raw)
            if isinstance(parsed, list):
                aliases = [str(a) for a in parsed if str(a).strip()]
        except (json.JSONDecodeError, TypeError):
            if isinstance(aliases_raw, str) and aliases_raw.strip():
                aliases = [aliases_raw.strip()]

    return FacilityAlias(
        canonical_id=canonical_id,
        canonical_name=canonical_name,
        npi=npi,
        ccn=ccn,
        facility_type=facility_type,
        aliases=aliases,
        address=address,
    )


class SQLiteRegistryLookup:
    """Read-only NPI/CCN lookup against a bundled SQLite facility registry.

    Opened once at stage init, closed at stage teardown. Uses WAL mode
    and query_only pragma for safety.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA query_only=ON")

    def lookup_npi(self, npi: str) -> FacilityAlias | None:
        """Lookup facility by NPI. Returns FacilityAlias or None."""
        if not npi or not npi.strip():
            return None
        row = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM facilities WHERE npi = ? LIMIT 1",  # nosec B608
            (npi.strip(),),
        ).fetchone()
        if row is None:
            return None
        return _row_to_alias(row)

    def lookup_ccn(self, ccn: str) -> FacilityAlias | None:
        """Lookup facility by CCN. Returns FacilityAlias or None."""
        if not ccn or not ccn.strip():
            return None
        row = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM facilities WHERE ccn = ? LIMIT 1",  # nosec B608
            (ccn.strip(),),
        ).fetchone()
        if row is None:
            return None
        return _row_to_alias(row)

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
