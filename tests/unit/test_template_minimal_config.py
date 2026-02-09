"""Validation tests for the minimal customer config template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asre.config.loader import load_config
from asre.config.schema import GlobalConfig

CUSTOMER_CONFIG_PATH = str(Path(__file__).parent.parent.parent / "customer_config")
CUSTOMER_ID = "template_minimal"


@pytest.fixture(autouse=True)
def _set_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide warehouse overrides for template loading."""
    creds = {
        "host": "localhost",
        "port": 5432,
        "database": "asre_test",
        "user": "asre_user",
        "password": "secret_password",
        "schema": "public",
    }
    monkeypatch.setenv("ASRE_WAREHOUSE_TYPE", "postgres")
    monkeypatch.setenv("ASRE_WAREHOUSE_CREDENTIALS", json.dumps(creds))


def test_template_minimal_config_loads() -> None:
    """Template config should load cleanly for first-time setup."""
    config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
    assert isinstance(config, GlobalConfig)


def test_template_minimal_facility_aliases_is_list() -> None:
    """Template facility aliases should default to an empty list, not null."""
    config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
    assert config.facility_aliases is not None
    assert isinstance(config.facility_aliases.facilities, list)
    assert len(config.facility_aliases.facilities) == 0
