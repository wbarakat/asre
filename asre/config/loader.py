"""YAML config loader with environment variable substitution (US-015)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from asre.config.facility_alias_schema import FacilityAliasConfig
from asre.config.schema import GlobalConfig
from asre.config.source_schema import SourceConfig

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} patterns in YAML values."""
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set but referenced in config"
                )
            return env_value

        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file, substituting env vars."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}, got {type(data).__name__}")
    result: dict[str, Any] = _substitute_env_vars(data)
    return result


def _parse_warehouse_credentials(value: str, warehouse_type: str | None) -> dict[str, Any]:
    """Parse ASRE_WAREHOUSE_CREDENTIALS into a connection dict."""
    path = Path(value)
    if path.exists() and path.is_file():
        data = _load_yaml_file(path)
        if not isinstance(data, dict):
            raise ValueError(
                f"ASRE_WAREHOUSE_CREDENTIALS file must contain a mapping, got {type(data).__name__}"
            )
        return data

    stripped = value.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "ASRE_WAREHOUSE_CREDENTIALS must be valid JSON or a path to a credentials file"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError("ASRE_WAREHOUSE_CREDENTIALS JSON must be an object")
        return data

    if "://" in stripped:
        parsed = urlparse(stripped)
        scheme = parsed.scheme.lower()
        if warehouse_type in ("postgres", "redshift") and scheme in (
            "postgres",
            "postgresql",
            "redshift",
        ):
            query = parse_qs(parsed.query)
            return {
                "host": parsed.hostname or "",
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/"),
                "user": parsed.username or "",
                "password": parsed.password or "",
                "schema": query.get("schema", ["public"])[0],
            }
        raise ValueError(
            "ASRE_WAREHOUSE_CREDENTIALS connection string only supported for postgres/redshift"
        )

    raise ValueError(
        "ASRE_WAREHOUSE_CREDENTIALS must be JSON, a file path, or a supported connection string"
    )


def _apply_warehouse_env_overrides(config_data: dict[str, Any]) -> None:
    """Apply ASRE_WAREHOUSE_* env vars to the loaded config data."""
    warehouse_type = os.environ.get("ASRE_WAREHOUSE_TYPE")
    credentials = os.environ.get("ASRE_WAREHOUSE_CREDENTIALS")
    require_utf8 = os.environ.get("ASRE_REQUIRE_UTF8")

    if warehouse_type is None and credentials is None:
        if require_utf8 is None:
            return

    warehouse = config_data.get("warehouse")
    if not isinstance(warehouse, dict):
        warehouse = {}
        config_data["warehouse"] = warehouse

    if warehouse_type:
        warehouse["type"] = warehouse_type
    if credentials:
        warehouse["connection"] = _parse_warehouse_credentials(credentials, warehouse_type)
    if require_utf8 is not None:
        conn = warehouse.get("connection")
        if not isinstance(conn, dict):
            conn = {}
            warehouse["connection"] = conn
        conn["require_utf8"] = _parse_bool(require_utf8)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config(config_path: str, customer_id: str) -> GlobalConfig:
    """Load customer config from filesystem with env var substitution.

    Args:
        config_path: Root config directory path.
        customer_id: Customer subdirectory name.

    Returns:
        Fully validated GlobalConfig with attached source configs and facility aliases.
    """
    customer_dir = Path(config_path) / customer_id

    if not customer_dir.is_dir():
        raise FileNotFoundError(
            f"Customer config directory not found: {customer_dir} "
            f"(customer_id='{customer_id}')"
        )

    config_file = customer_dir / "config.yaml"
    if not config_file.is_file():
        raise FileNotFoundError(f"config.yaml not found in {customer_dir}")

    # Load main config
    config_data = _load_yaml_file(config_file)
    _apply_warehouse_env_overrides(config_data)

    # Load source configs
    sources: list[SourceConfig] = []
    sources_dir = customer_dir / "sources"
    if sources_dir.is_dir():
        for source_file in sorted(sources_dir.glob("*.yaml")):
            source_data = _load_yaml_file(source_file)
            sources.append(SourceConfig(**source_data))

    # Load facility aliases (optional)
    facility_aliases: FacilityAliasConfig | None = None
    aliases_file = customer_dir / "facility_aliases.yaml"
    if aliases_file.is_file():
        aliases_data = _load_yaml_file(aliases_file)
        facility_aliases = FacilityAliasConfig(**aliases_data)

    # Build GlobalConfig then attach sources and aliases
    global_config = GlobalConfig(**config_data)
    global_config.sources = sources
    global_config.facility_aliases = facility_aliases

    return global_config
