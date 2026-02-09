"""Offline license key validation for ASRE.

Validates RSA-256 signed JWT license keys without any network dependency.
Keys contain customer_id and expiry claims, verified against an embedded
public key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jwt


_PUBLIC_KEY_PATH = Path(__file__).parent / "public_key.pem"


@dataclass
class LicenseValidationResult:
    """Result of license key validation.

    Attributes:
        valid: Whether the license key is valid.
        error: Human-readable error message if invalid, empty string if valid.
        customer_id: Customer ID from the license key, or empty string.
        expires_at: License expiry timestamp, or None.
    """

    valid: bool
    error: str
    customer_id: str
    expires_at: datetime | None


def validate_license_key(
    license_key: str,
    expected_customer_id: str,
    *,
    public_key_path: Path | None = None,
) -> LicenseValidationResult:
    """Validate an ASRE license key.

    Verifies the JWT signature, expiry, and customer_id claim.

    Args:
        license_key: The JWT license key string.
        expected_customer_id: The customer_id that must match the key's claim.
        public_key_path: Optional override for the public key file path.
            Defaults to the embedded public_key.pem.

    Returns:
        LicenseValidationResult with validation outcome.
    """
    key_path = public_key_path or _PUBLIC_KEY_PATH

    if not key_path.exists():
        return LicenseValidationResult(
            valid=False,
            error=f"License public key not found at {key_path}",
            customer_id="",
            expires_at=None,
        )

    try:
        public_key = key_path.read_text()
    except OSError as exc:
        return LicenseValidationResult(
            valid=False,
            error=f"Failed to read license public key: {exc}",
            customer_id="",
            expires_at=None,
        )

    try:
        payload: dict[str, Any] = jwt.decode(
            license_key,
            public_key,
            algorithms=["RS256"],
        )
    except jwt.ExpiredSignatureError:
        return LicenseValidationResult(
            valid=False,
            error="License key has expired",
            customer_id="",
            expires_at=None,
        )
    except jwt.InvalidSignatureError:
        return LicenseValidationResult(
            valid=False,
            error="License key signature is invalid",
            customer_id="",
            expires_at=None,
        )
    except jwt.DecodeError as exc:
        return LicenseValidationResult(
            valid=False,
            error=f"License key is malformed: {exc}",
            customer_id="",
            expires_at=None,
        )

    key_customer_id = payload.get("customer_id", "")
    if key_customer_id != expected_customer_id:
        return LicenseValidationResult(
            valid=False,
            error=(
                f"License key customer_id '{key_customer_id}' does not match "
                f"expected '{expected_customer_id}'"
            ),
            customer_id=key_customer_id,
            expires_at=None,
        )

    exp_claim = payload.get("exp")
    expires_at: datetime | None = None
    if exp_claim is not None:
        expires_at = datetime.fromtimestamp(exp_claim, tz=timezone.utc)

    return LicenseValidationResult(
        valid=True,
        error="",
        customer_id=key_customer_id,
        expires_at=expires_at,
    )
