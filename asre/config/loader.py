"""YAML config loader with environment variable substitution (US-015)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

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
