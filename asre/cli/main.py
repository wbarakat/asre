"""ASRE CLI entry point."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from asre.config.loader import load_config


def _get_facility_adapter(config_path: str, customer_id: str) -> Any:
    """Create and connect a database adapter from customer config.

    Args:
        config_path: Root config directory path.
        customer_id: Customer subdirectory name.

    Returns:
        Connected IngestAdapter instance.
    """
    from asre.ingest.postgres import PostgresAdapter

    config = load_config(config_path, customer_id)
    adapter = PostgresAdapter(config.warehouse.connection)
    adapter.connect()
    return adapter


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ASRE - Admission Signal Reliability Engine."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command("validate-config")
@click.option(
    "--config-path",
    envvar="ASRE_CONFIG_PATH",
    required=True,
    help="Root config directory path.",
)
@click.option(
    "--customer-id",
    envvar="ASRE_CUSTOMER_ID",
    required=True,
    help="Customer subdirectory name.",
)
def validate_config(config_path: str, customer_id: str) -> None:
    """Load and validate customer configuration."""
    try:
        load_config(config_path, customer_id)
        click.echo("Configuration is valid.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


def _create_pipeline_runner(
    config_path: str,
    customer_id: str,
    mode: str,
) -> Any:
    """Create a PipelineRunner from customer config.

    Args:
        config_path: Root config directory path.
        customer_id: Customer subdirectory name.
        mode: Pipeline run mode ('full' or 'incremental').

    Returns:
        Configured PipelineRunner instance.
    """
    from asre.ingest.postgres import PostgresAdapter
    from asre.pipeline.runner import PipelineRunner

    global_config = load_config(config_path, customer_id)

    pipeline_config: dict[str, Any] = {}
    pipeline_config["customer"] = {
        "customer_id": global_config.customer.customer_id,
        "customer_name": global_config.customer.customer_name,
    }
    pipeline_config["sources"] = global_config.sources
    pipeline_config["facility_aliases"] = global_config.facility_aliases

    if hasattr(global_config, "encounter_stitching"):
        pipeline_config["encounter_stitching"] = global_config.encounter_stitching
    if hasattr(global_config, "deduplication"):
        pipeline_config["deduplication"] = global_config.deduplication
    if hasattr(global_config, "reconciliation"):
        pipeline_config["reconciliation"] = global_config.reconciliation
    if hasattr(global_config, "confidence_scoring"):
        pipeline_config["confidence_scoring"] = global_config.confidence_scoring
    if hasattr(global_config, "facility_normalization"):
        pipeline_config["facility_normalization"] = global_config.facility_normalization

    # Connect adapter for database operations
    adapter = PostgresAdapter(global_config.warehouse.connection)
    adapter.connect()
    pipeline_config["adapter"] = adapter

    return PipelineRunner(config=pipeline_config, mode=mode)


@cli.command("run")
@click.option(
    "--mode",
    type=click.Choice(["full", "incremental"]),
    default="incremental",
    help="Pipeline run mode (default: incremental).",
)
@click.option(
    "--resume",
    "resume_run_id",
    default=None,
    help="Resume a previously failed run by its run_id.",
)
@click.option(
    "--config-path",
    envvar="ASRE_CONFIG_PATH",
    required=True,
    help="Root config directory path.",
)
@click.option(
    "--customer-id",
    envvar="ASRE_CUSTOMER_ID",
    required=True,
    help="Customer subdirectory name.",
)
def run_pipeline(
    mode: str,
    resume_run_id: str | None,
    config_path: str,
    customer_id: str,
) -> None:
    """Run the ASRE pipeline."""
    try:
        runner = _create_pipeline_runner(
            config_path=config_path,
            customer_id=customer_id,
            mode=mode,
        )
        result: dict[str, Any] = runner.run(resume_run_id=resume_run_id)
        click.echo(
            f"Pipeline completed: run_id={result['run_id']}, "
            f"mode={result['mode']}, "
            f"stages_completed={result['stages_completed']}"
        )
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("test-connection")
def test_connection() -> None:
    """Test warehouse connectivity."""
    click.echo("Not yet implemented.")


@cli.group("facilities", invoke_without_command=True)
@click.option(
    "--unresolved",
    is_flag=True,
    default=False,
    help="List facilities flagged FACILITY_NEW_UNREVIEWED.",
)
@click.option(
    "--config-path",
    envvar="ASRE_CONFIG_PATH",
    required=True,
    help="Root config directory path.",
)
@click.option(
    "--customer-id",
    envvar="ASRE_CUSTOMER_ID",
    required=True,
    help="Customer subdirectory name.",
)
@click.pass_context
def facilities(
    ctx: click.Context,
    unresolved: bool,
    config_path: str,
    customer_id: str,
) -> None:
    """Manage facility registry."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["customer_id"] = customer_id

    if unresolved:
        _list_unresolved(config_path, customer_id)
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _list_unresolved(config_path: str, customer_id: str) -> None:
    """List facilities flagged FACILITY_NEW_UNREVIEWED."""
    try:
        adapter = _get_facility_adapter(config_path, customer_id)
        try:
            records: list[dict[str, Any]] = adapter.read_source(
                "asre_facility_registry",
                "SELECT * FROM asre_facility_registry",
            )
        finally:
            adapter.disconnect()

        unresolved_list: list[dict[str, Any]] = []
        for rec in records:
            flags_raw = rec.get("flags", "[]")
            flags: list[str] = (
                json.loads(flags_raw) if isinstance(flags_raw, str) else flags_raw
            )
            if "FACILITY_NEW_UNREVIEWED" in flags:
                unresolved_list.append(rec)

        if not unresolved_list:
            click.echo("No unresolved facilities found.")
            return

        for fac in unresolved_list:
            click.echo(
                f"{fac['canonical_id']}  {fac['canonical_name']}  "
                f"type={fac.get('facility_type') or 'unknown'}"
            )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@facilities.command("resolve")
@click.argument("facility_id")
@click.option(
    "--target",
    required=True,
    help="Target canonical facility ID to map the unresolved facility to.",
)
@click.pass_context
def facilities_resolve(ctx: click.Context, facility_id: str, target: str) -> None:
    """Map an unresolved facility to an existing canonical ID.

    FACILITY_ID is the unresolved facility's canonical_id.
    """
    config_path: str = ctx.obj["config_path"]
    customer_id: str = ctx.obj["customer_id"]
    try:
        adapter = _get_facility_adapter(config_path, customer_id)
        try:
            # Verify source facility exists
            source_records: list[dict[str, Any]] = adapter.read_source(
                "asre_facility_registry",
                "SELECT * FROM asre_facility_registry WHERE canonical_id = :fid",
                {"fid": facility_id},
            )
            if not source_records:
                click.echo(f"Error: Facility {facility_id} not found.", err=True)
                sys.exit(1)

            # Verify target facility exists
            target_records: list[dict[str, Any]] = adapter.read_source(
                "asre_facility_registry",
                "SELECT * FROM asre_facility_registry WHERE canonical_id = :fid",
                {"fid": target},
            )
            if not target_records:
                click.echo(f"Error: Target facility {target} not found.", err=True)
                sys.exit(1)

            click.echo(
                f"Mapped {facility_id} -> {target} "
                f"(target: {target_records[0]['canonical_name']})"
            )
        finally:
            adapter.disconnect()
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
