#!/usr/bin/env python3
"""Issue ASRE license keys.

Generates RSA-4096 keypair on first use and signs JWT license keys
containing customer_id and expiry claims.

Usage:
    python scripts/issue_license.py --customer-id acme_health --days 365
    python scripts/issue_license.py --customer-id acme_health --days 365 --embed-public-key
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


_DEFAULT_KEY_DIR = Path.home() / ".asre"
_PRIVATE_KEY_FILE = "license_private_key.pem"
_PUBLIC_KEY_FILE = "license_public_key.pem"
_EMBEDDED_PUBLIC_KEY = Path(__file__).parent.parent / "asre" / "license" / "public_key.pem"


def _ensure_keypair(key_dir: Path) -> tuple[bytes, bytes]:
    """Load or generate RSA-4096 keypair.

    Args:
        key_dir: Directory to store keys.

    Returns:
        Tuple of (private_key_pem, public_key_pem).
    """
    private_path = key_dir / _PRIVATE_KEY_FILE
    public_path = key_dir / _PUBLIC_KEY_FILE

    if private_path.exists() and public_path.exists():
        private_pem = private_path.read_bytes()
        public_pem = public_path.read_bytes()
        return private_pem, public_pem

    key_dir.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)
    public_path.write_bytes(public_pem)

    print(f"Generated RSA-4096 keypair at {key_dir}/", file=sys.stderr)
    return private_pem, public_pem


def issue_license(
    customer_id: str,
    days: int,
    private_key_pem: bytes,
) -> str:
    """Sign a license key JWT.

    Args:
        customer_id: Customer identifier.
        days: Number of days until expiry.
        private_key_pem: RSA private key in PEM format.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(tz=timezone.utc)
    payload = {
        "customer_id": customer_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Issue ASRE license keys",
    )
    parser.add_argument(
        "--customer-id",
        required=True,
        help="Customer identifier (must match ASRE_CUSTOMER_ID).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="License validity in days (default: 365).",
    )
    parser.add_argument(
        "--private-key",
        type=Path,
        default=None,
        help="Path to existing RSA private key PEM file.",
    )
    parser.add_argument(
        "--embed-public-key",
        action="store_true",
        help="Copy public key to asre/license/public_key.pem for embedding.",
    )

    args = parser.parse_args()

    if args.private_key:
        private_pem = args.private_key.read_bytes()
        public_pem = b""  # Not needed for signing
    else:
        private_pem, public_pem = _ensure_keypair(_DEFAULT_KEY_DIR)

    token = issue_license(args.customer_id, args.days, private_pem)

    if args.embed_public_key:
        if not public_pem:
            # Derive public key from private key
            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            private_key = load_pem_private_key(private_pem, password=None)
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        _EMBEDDED_PUBLIC_KEY.parent.mkdir(parents=True, exist_ok=True)
        _EMBEDDED_PUBLIC_KEY.write_bytes(public_pem)
        print(f"Public key embedded at {_EMBEDDED_PUBLIC_KEY}", file=sys.stderr)

    print(token)


if __name__ == "__main__":
    main()
