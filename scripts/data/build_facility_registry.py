#!/usr/bin/env python3
"""Build a combined facility registry from NPPES + POS sources."""

from __future__ import annotations

import argparse
from pathlib import Path

from asre.facility.registry_builder import build_combined_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Build combined facility registry.")
    parser.add_argument("--nppes", required=True, type=Path, help="Path to NPPES npidata CSV")
    parser.add_argument("--othernames", type=Path, help="Path to NPPES othername CSV")
    parser.add_argument("--pos-hospital", type=Path, help="Path to POS Hospital CSV")
    parser.add_argument("--pos-iqies", type=Path, help="Path to POS iQIES CSV")
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path")
    parser.add_argument("--limit", type=int, help="Optional row limit per source")
    args = parser.parse_args()

    build_combined_registry(
        nppes_path=args.nppes,
        othername_path=args.othernames,
        pos_hospital_path=args.pos_hospital,
        pos_iqies_path=args.pos_iqies,
        output_path=args.out,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
