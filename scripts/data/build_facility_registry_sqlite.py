#!/usr/bin/env python3
"""Build SQLite facility registry from combined CSV.

Usage:
    python scripts/data/build_facility_registry_sqlite.py \
        --csv data/reference/registry/facility_registry.csv \
        --out data/reference/registry/facility_registry.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from asre.facility.sqlite_registry import build_sqlite_from_csv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build SQLite facility registry from combined CSV."
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to combined facility registry CSV.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output path for SQLite database.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    db_path = Path(args.out)

    print(f"Building SQLite registry from {csv_path} ...")
    count = build_sqlite_from_csv(csv_path, db_path)

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"Done: {count:,} rows, {size_mb:.1f} MB at {db_path}")


if __name__ == "__main__":
    main()
