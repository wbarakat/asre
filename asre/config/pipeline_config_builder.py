"""Build pipeline config dict from GlobalConfig."""

from __future__ import annotations

from typing import Any, cast

from asre.config.schema import GlobalConfig


def build_pipeline_config(global_config: GlobalConfig) -> dict[str, Any]:
    """Convert GlobalConfig into the dict used by PipelineRunner."""
    config: dict[str, Any] = {}

    config["customer"] = {
        "customer_id": global_config.customer.customer_id,
        "customer_name": global_config.customer.customer_name,
    }

    # Sources (coerce models to dicts)
    sources: list[Any] = list(global_config.sources or [])
    normalized_sources: list[dict[str, Any]] = []
    for src in sources:
        if hasattr(src, "model_dump"):
            dumped = src.model_dump()
            if isinstance(dumped, dict):
                normalized_sources.append(cast(dict[str, Any], dumped))
        elif hasattr(src, "dict"):
            dumped = src.dict()
            if isinstance(dumped, dict):
                normalized_sources.append(cast(dict[str, Any], dumped))
        else:
            if isinstance(src, dict):
                normalized_sources.append(src)
    config["sources"] = normalized_sources

    config["facility_aliases"] = global_config.facility_aliases

    # Convert Pydantic configs to dicts so stages can use .get
    config["schedule"] = _as_dict(global_config.schedule)
    config["encounter_stitching"] = _as_dict(global_config.encounter_stitching)
    config["deduplication"] = _as_dict(global_config.deduplication)
    config["reconciliation"] = _as_dict(global_config.reconciliation)
    config["episode_stitching"] = _as_dict(global_config.episode_stitching)
    config["facility_normalization"] = _as_dict(global_config.facility_normalization)
    config["confidence_scoring"] = _as_dict(global_config.confidence_scoring)
    config["alerting"] = _as_dict(global_config.alerting)

    return config


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return cast(dict[str, Any], dumped)
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return cast(dict[str, Any], dumped)
        return {}
    return {}
