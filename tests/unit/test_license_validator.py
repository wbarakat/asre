"""Tests for asre.license.validator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from asre.license.validator import LicenseValidationResult, validate_license_key


@pytest.fixture()
def rsa_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh RSA keypair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
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
    return private_pem, public_pem


@pytest.fixture()
def public_key_file(tmp_path: Path, rsa_keypair: tuple[bytes, bytes]) -> Path:
    """Write the test public key to a temp file."""
    _, public_pem = rsa_keypair
    key_file = tmp_path / "public_key.pem"
    key_file.write_bytes(public_pem)
    return key_file


def _sign_token(
    private_pem: bytes,
    customer_id: str = "test_customer",
    days: int = 30,
) -> str:
    """Sign a test JWT token."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "customer_id": customer_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")


class TestValidateLicenseKey:
    """Tests for validate_license_key."""

    def test_valid_key(
        self,
        rsa_keypair: tuple[bytes, bytes],
        public_key_file: Path,
    ) -> None:
        """Valid key returns success."""
        private_pem, _ = rsa_keypair
        token = _sign_token(private_pem, customer_id="acme_health")

        result = validate_license_key(
            token, "acme_health", public_key_path=public_key_file,
        )
        assert result.valid is True
        assert result.error == ""
        assert result.customer_id == "acme_health"
        assert result.expires_at is not None

    def test_expired_key(
        self,
        rsa_keypair: tuple[bytes, bytes],
        public_key_file: Path,
    ) -> None:
        """Expired key returns error."""
        private_pem, _ = rsa_keypair
        token = _sign_token(private_pem, days=-1)

        result = validate_license_key(
            token, "test_customer", public_key_path=public_key_file,
        )
        assert result.valid is False
        assert "expired" in result.error.lower()

    def test_tampered_key(
        self,
        rsa_keypair: tuple[bytes, bytes],
        public_key_file: Path,
    ) -> None:
        """Tampered key returns error."""
        private_pem, _ = rsa_keypair
        token = _sign_token(private_pem)
        # Corrupt the token by changing a character in the payload
        parts = token.split(".")
        parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
        tampered = ".".join(parts)

        result = validate_license_key(
            tampered, "test_customer", public_key_path=public_key_file,
        )
        assert result.valid is False
        assert "invalid" in result.error.lower() or "malformed" in result.error.lower()

    def test_wrong_key(
        self,
        public_key_file: Path,
    ) -> None:
        """Token signed with different key returns error."""
        other_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = _sign_token(other_pem)

        result = validate_license_key(
            token, "test_customer", public_key_path=public_key_file,
        )
        assert result.valid is False
        assert "signature" in result.error.lower()

    def test_customer_id_mismatch(
        self,
        rsa_keypair: tuple[bytes, bytes],
        public_key_file: Path,
    ) -> None:
        """Mismatched customer_id returns error."""
        private_pem, _ = rsa_keypair
        token = _sign_token(private_pem, customer_id="acme_health")

        result = validate_license_key(
            token, "other_customer", public_key_path=public_key_file,
        )
        assert result.valid is False
        assert "does not match" in result.error

    def test_missing_public_key(self, tmp_path: Path) -> None:
        """Missing public key file returns error."""
        missing_path = tmp_path / "nonexistent.pem"
        result = validate_license_key(
            "some.jwt.token", "test", public_key_path=missing_path,
        )
        assert result.valid is False
        assert "not found" in result.error

    def test_malformed_token(self, public_key_file: Path) -> None:
        """Completely malformed token returns error."""
        result = validate_license_key(
            "not-a-jwt", "test", public_key_path=public_key_file,
        )
        assert result.valid is False
        assert "malformed" in result.error.lower()


class TestLicenseValidationResult:
    """Tests for LicenseValidationResult dataclass."""

    def test_valid_result(self) -> None:
        result = LicenseValidationResult(
            valid=True,
            error="",
            customer_id="test",
            expires_at=datetime.now(tz=timezone.utc),
        )
        assert result.valid is True

    def test_invalid_result(self) -> None:
        result = LicenseValidationResult(
            valid=False,
            error="some error",
            customer_id="",
            expires_at=None,
        )
        assert result.valid is False
        assert result.error == "some error"
