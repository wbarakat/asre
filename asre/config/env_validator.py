"""Environment variable validation for ASRE (US-107).

Validates that required environment variables are set before any pipeline work
begins. Optional env vars are documented but not enforced.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_CORE_REQUIRED_ENV_VARS: tuple[str, ...] = (
    "ASRE_CUSTOMER_ID",
    "ASRE_CONFIG_PATH",
)

REQUIRED_ENV_VARS: list[str] = [
    "ASRE_CUSTOMER_ID",
    "ASRE_CONFIG_PATH",
    "ASRE_WAREHOUSE_TYPE",
    "ASRE_WAREHOUSE_CREDENTIALS",
]

OPTIONAL_ENV_VARS: list[str] = [
    "ASRE_RUN_MODE",
    "ASRE_LOG_LEVEL",
    "ASRE_ALERT_WEBHOOK_URL",
    "ASRE_DRY_RUN",
    "ASRE_REQUIRE_UTF8",
    "ASRE_LICENSE_KEY",
]


@dataclass
class EnvValidationResult:
    """Result of environment variable validation.

    Attributes:
        missing: List of required env var names that are not set.
        present: List of required env var names that are set.
    """

    missing: list[str]
    present: list[str]

    @property
    def is_valid(self) -> bool:
        """Return True if no required env vars are missing."""
        return len(self.missing) == 0

    def error_message(self) -> str:
        """Return a human-readable error message listing missing env vars.

        Returns an empty string if all required vars are present.
        """
        if self.is_valid:
            return ""
        missing_list = ", ".join(self.missing)
        return (
            f"Missing required environment variable(s): {missing_list}. "
            f"Set these before running ASRE."
        )


def validate_env_vars(
    *,
    overrides: dict[str, str] | None = None,
    require_warehouse: bool = True,
) -> EnvValidationResult:
    """Validate that all required ASRE environment variables are set.

    Checks each variable in REQUIRED_ENV_VARS against the current
    environment. Variables that are set to an empty string are treated
    as missing.

    Args:
        overrides: Optional explicit values used when env vars are unset.
        require_warehouse: Whether warehouse env vars must be present.

    Returns:
        EnvValidationResult with lists of missing and present vars.
    """
    missing: list[str] = []
    present: list[str] = []

    overrides = overrides or {}

    required_vars = list(_CORE_REQUIRED_ENV_VARS)
    if require_warehouse:
        required_vars.extend(["ASRE_WAREHOUSE_TYPE", "ASRE_WAREHOUSE_CREDENTIALS"])

    for var in required_vars:
        value = os.environ.get(var)
        if (value is None or value.strip() == "") and var in overrides:
            value = overrides[var]
        if value is None or str(value).strip() == "":
            missing.append(var)
        else:
            present.append(var)

    return EnvValidationResult(missing=missing, present=present)
