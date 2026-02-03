"""Tests for asre.config.env_validator (US-107)."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from asre.config.env_validator import (
    OPTIONAL_ENV_VARS,
    REQUIRED_ENV_VARS,
    EnvValidationResult,
    validate_env_vars,
)


class TestEnvValidationResult:
    """Tests for the EnvValidationResult dataclass."""

    def test_is_valid_when_no_missing(self) -> None:
        """Result is valid when no env vars are missing."""
        result = EnvValidationResult(missing=[], present=["VAR1", "VAR2"])
        assert result.is_valid is True

    def test_is_invalid_when_missing(self) -> None:
        """Result is invalid when env vars are missing."""
        result = EnvValidationResult(missing=["VAR1"], present=["VAR2"])
        assert result.is_valid is False

    def test_error_message_empty_when_valid(self) -> None:
        """Error message is empty when all vars present."""
        result = EnvValidationResult(missing=[], present=["VAR1"])
        assert result.error_message() == ""

    def test_error_message_lists_missing_vars(self) -> None:
        """Error message lists the missing variable names."""
        result = EnvValidationResult(missing=["VAR1", "VAR2"], present=[])
        msg = result.error_message()
        assert "VAR1" in msg
        assert "VAR2" in msg
        assert "Missing required" in msg


class TestValidateEnvVars:
    """Tests for the validate_env_vars function."""

    def test_all_required_vars_present(self) -> None:
        """Returns valid when all required vars are set."""
        env = {var: "value" for var in REQUIRED_ENV_VARS}
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate_env_vars()
        assert result.is_valid is True
        assert result.missing == []
        assert set(result.present) == set(REQUIRED_ENV_VARS)

    def test_missing_one_required_var(self) -> None:
        """Returns invalid when one required var is missing."""
        env = {var: "value" for var in REQUIRED_ENV_VARS[1:]}
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate_env_vars()
        assert result.is_valid is False
        assert REQUIRED_ENV_VARS[0] in result.missing

    def test_missing_all_required_vars(self) -> None:
        """Returns invalid when all required vars are missing."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = validate_env_vars()
        assert result.is_valid is False
        assert set(result.missing) == set(REQUIRED_ENV_VARS)

    def test_empty_string_treated_as_missing(self) -> None:
        """Empty string values are treated as missing."""
        env = {var: "" for var in REQUIRED_ENV_VARS}
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate_env_vars()
        assert result.is_valid is False
        assert set(result.missing) == set(REQUIRED_ENV_VARS)

    def test_whitespace_only_treated_as_missing(self) -> None:
        """Whitespace-only values are treated as missing."""
        env = {var: "   " for var in REQUIRED_ENV_VARS}
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate_env_vars()
        assert result.is_valid is False
        assert set(result.missing) == set(REQUIRED_ENV_VARS)

    def test_optional_vars_not_required(self) -> None:
        """Optional env vars don't affect validation."""
        # Set all required vars, but none of the optional
        env = {var: "value" for var in REQUIRED_ENV_VARS}
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate_env_vars()
        assert result.is_valid is True


class TestEnvVarLists:
    """Tests for the env var constant lists."""

    def test_required_env_vars_defined(self) -> None:
        """Required env vars list is defined correctly."""
        assert "ASRE_CUSTOMER_ID" in REQUIRED_ENV_VARS
        assert "ASRE_CONFIG_PATH" in REQUIRED_ENV_VARS
        assert "ASRE_WAREHOUSE_TYPE" in REQUIRED_ENV_VARS
        assert "ASRE_WAREHOUSE_CREDENTIALS" in REQUIRED_ENV_VARS

    def test_optional_env_vars_defined(self) -> None:
        """Optional env vars list is defined correctly."""
        assert "ASRE_RUN_MODE" in OPTIONAL_ENV_VARS
        assert "ASRE_LOG_LEVEL" in OPTIONAL_ENV_VARS
        assert "ASRE_ALERT_WEBHOOK_URL" in OPTIONAL_ENV_VARS
        assert "ASRE_DRY_RUN" in OPTIONAL_ENV_VARS
