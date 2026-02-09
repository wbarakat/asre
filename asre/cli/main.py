"""ASRE CLI entry point."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from asre.config.env_validator import validate_env_vars
from asre.config.loader import load_config


def _check_env_or_exit(
    *,
    overrides: dict[str, str] | None = None,
    require_warehouse: bool = True,
) -> None:
    """Validate required environment variables and exit if any are missing.

    This runs before any pipeline work to give operators a clear,
    actionable error message.
    """
    result = validate_env_vars(
        overrides=overrides,
        require_warehouse=require_warehouse,
    )
    if not result.is_valid:
        click.echo(f"Error: {result.error_message()}", err=True)
        sys.exit(1)


def _validate_license_or_exit() -> None:
    """Validate the ASRE license key and exit if invalid.

    Reads ASRE_LICENSE_KEY and ASRE_CUSTOMER_ID from environment.
    Called before pipeline operations but NOT for diagnostic commands.
    """
    from asre.license.validator import validate_license_key

    license_key = os.environ.get("ASRE_LICENSE_KEY", "").strip()
    if not license_key:
        click.echo(
            "Error: ASRE_LICENSE_KEY environment variable is required. "
            "Set it to your signed license key JWT.",
            err=True,
        )
        sys.exit(1)

    customer_id = os.environ.get("ASRE_CUSTOMER_ID", "").strip()
    if not customer_id:
        click.echo(
            "Error: ASRE_CUSTOMER_ID environment variable is required for license validation.",
            err=True,
        )
        sys.exit(1)

    result = validate_license_key(license_key, customer_id)
    if not result.valid:
        click.echo(f"Error: License validation failed: {result.error}", err=True)
        sys.exit(1)


def _start_health_server() -> tuple[Any, Any, Any]:
    """Start the health check server in a background thread."""
    from asre.observability.health import (
        PipelineHealthState,
        start_health_check_server,
    )

    port_raw = os.environ.get("ASRE_HEALTH_PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid ASRE_HEALTH_PORT '{port_raw}'") from exc

    bind_address = os.environ.get("ASRE_HEALTH_BIND", "127.0.0.1")

    state = PipelineHealthState()
    server, thread = start_health_check_server(
        state=state,
        port=port,
        bind_address=bind_address,
    )
    return server, thread, state


def _run_auto_migration(adapter: Any) -> None:
    """Run schema migrations automatically before pipeline execution.

    Checks asre_metadata for current schema_version, runs any pending
    migrations, and updates the version. Raises on migration failure
    so the container exits with a non-zero code.

    Args:
        adapter: Connected IngestAdapter instance.
    """
    from asre.migration.migrator import Migrator

    migrator = Migrator(adapter)
    current_version = migrator.get_schema_version()

    if current_version == 0:
        click.echo("Fresh install detected. Running all migrations...")
    else:
        pending = [
            m for m in migrator.discover_migrations()
            if m.version > current_version
        ]
        if not pending:
            click.echo(f"Schema is up to date (version {current_version}).")
            return
        click.echo(
            f"Schema version {current_version} is behind. "
            f"Running {len(pending)} pending migration(s)..."
        )

    result = migrator.run()
    click.echo(
        f"Migrations complete: applied {result.applied}, "
        f"schema version now {result.current_version}."
    )


def _get_facility_adapter(config_path: str, customer_id: str) -> Any:
    """Create and connect a database adapter from customer config.

    Args:
        config_path: Root config directory path.
        customer_id: Customer subdirectory name.

    Returns:
        Connected IngestAdapter instance.
    """
    from asre.ingest.adapter_factory import create_adapter

    config = load_config(config_path, customer_id)
    adapter = create_adapter(config.warehouse.type, config.warehouse.connection)
    adapter.connect()
    return adapter


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ASRE - Admission Signal Reliability Engine."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command("validate-env")
def validate_env() -> None:
    """Validate that all required ASRE environment variables are set."""
    result = validate_env_vars()
    if result.is_valid:
        click.echo("All required environment variables are set.")
    else:
        click.echo(f"Error: {result.error_message()}", err=True)
        sys.exit(1)


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
    dry_run: bool = False,
    health_state: Any | None = None,
) -> Any:
    """Create a PipelineRunner from customer config.

    Args:
        config_path: Root config directory path.
        customer_id: Customer subdirectory name.
        mode: Pipeline run mode ('full' or 'incremental').

    Returns:
        Configured PipelineRunner instance.
    """
    from asre.config.pipeline_config_builder import build_pipeline_config
    from asre.ingest.adapter_factory import create_adapter
    from asre.pipeline.runner import PipelineRunner

    global_config = load_config(config_path, customer_id)

    pipeline_config = build_pipeline_config(global_config)

    # Connect adapter for database operations
    adapter = create_adapter(
        global_config.warehouse.type,
        global_config.warehouse.connection,
    )
    adapter.connect()
    pipeline_config["adapter"] = adapter

    # Auto-migrate schema before pipeline execution
    _run_auto_migration(adapter)

    if dry_run:
        pipeline_config["dry_run"] = True
    if health_state is not None:
        pipeline_config["health_state"] = health_state

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
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    envvar="ASRE_DRY_RUN",
    help="Run pipeline without writing to output tables.",
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
    dry_run: bool,
    config_path: str,
    customer_id: str,
) -> None:
    """Run the ASRE pipeline."""
    _check_env_or_exit(
        overrides={
            "ASRE_CONFIG_PATH": config_path,
            "ASRE_CUSTOMER_ID": customer_id,
        },
        require_warehouse=False,
    )
    _validate_license_or_exit()
    server = None
    thread = None
    health_state = None
    try:
        server, thread, health_state = _start_health_server()
        runner = _create_pipeline_runner(
            config_path=config_path,
            customer_id=customer_id,
            mode=mode,
            dry_run=dry_run,
            health_state=health_state,
        )
        result: dict[str, Any] = runner.run(resume_run_id=resume_run_id)
        click.echo(
            f"Pipeline completed: run_id={result['run_id']}, "
            f"mode={result['mode']}, "
            f"stages_completed={result['stages_completed']}"
        )
    except ValueError as exc:
        if health_state is not None:
            health_state.mark_failed(str(exc))
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        if health_state is not None:
            health_state.mark_failed(str(exc))
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        if server is not None:
            server.shutdown()
        if thread is not None:
            thread.join(timeout=2)


@cli.command("test-connection")
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
def test_connection(config_path: str, customer_id: str) -> None:
    """Test warehouse connectivity."""
    try:
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            adapter.read_source("test", "SELECT 1 AS connected")
            click.echo("Connection successful.")
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Connection failed: {exc}", err=True)
        sys.exit(1)


def _get_diagnostic_adapter(config_path: str, customer_id: str) -> Any:
    """Create and connect a database adapter for diagnostic queries.

    Args:
        config_path: Root config directory path.
        customer_id: Customer subdirectory name.

    Returns:
        Connected IngestAdapter instance.
    """
    from asre.ingest.adapter_factory import create_adapter

    config = load_config(config_path, customer_id)
    adapter = create_adapter(config.warehouse.type, config.warehouse.connection)
    adapter.connect()
    return adapter


@cli.command("status")
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
def status_command(config_path: str, customer_id: str) -> None:
    """Show last run status and summary."""
    try:
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            # Get latest run from checkpoints
            runs: list[dict[str, Any]] = adapter.read_source(
                "asre_checkpoints",
                "SELECT * FROM asre_checkpoints ORDER BY updated_at DESC LIMIT 1",
            )
            if not runs:
                click.echo("No pipeline runs found.")
                return

            run = runs[0]
            run_id: str = run["run_id"]
            click.echo(f"Last run: {run_id}")
            click.echo(f"  Status: {run['status']}")
            click.echo(f"  Last stage: {run['last_completed_stage']}")
            click.echo(f"  Updated: {run['updated_at']}")
            if run.get("error"):
                click.echo(f"  Error: {run['error']}")

            # Get stage metrics for the run
            metrics: list[dict[str, Any]] = adapter.read_source(
                "asre_run_metrics",
                "SELECT * FROM asre_run_metrics WHERE run_id = :rid ORDER BY stage_name",
                {"rid": run_id},
            )
            if metrics:
                total_in = sum(m.get("records_in", 0) or 0 for m in metrics)
                total_out = sum(m.get("records_out", 0) or 0 for m in metrics)
                total_errors = sum(m.get("errors", 0) or 0 for m in metrics)
                click.echo(f"  Stages: {len(metrics)}")
                click.echo(
                    f"  Total: {total_in} in / {total_out} out / {total_errors} errors"
                )
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.group("inspect", invoke_without_command=True)
@click.pass_context
def inspect_group(ctx: click.Context) -> None:
    """Inspect pipeline results."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@inspect_group.command("run")
@click.argument("run_id")
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
def inspect_run(run_id: str, config_path: str, customer_id: str) -> None:
    """Show per-stage metrics for a pipeline run.

    RUN_ID is the pipeline run identifier (e.g., run_20250101_120000).
    """
    try:
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            metrics: list[dict[str, Any]] = adapter.read_source(
                "asre_run_metrics",
                "SELECT * FROM asre_run_metrics WHERE run_id = :rid ORDER BY stage_name",
                {"rid": run_id},
            )
            if not metrics:
                click.echo(f"No metrics found for run {run_id}.")
                return

            click.echo(f"Run: {run_id}")
            click.echo(
                f"{'Stage':<20} {'In':>8} {'Out':>8} {'Errors':>8} {'Status':<12}"
            )
            click.echo("-" * 60)
            for m in metrics:
                click.echo(
                    f"{m.get('stage_name', ''):<20} "
                    f"{m.get('records_in', 0):>8} "
                    f"{m.get('records_out', 0):>8} "
                    f"{m.get('errors', 0):>8} "
                    f"{m.get('status', ''):<12}"
                )
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@inspect_group.command("encounter")
@click.argument("encounter_id")
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
def inspect_encounter(encounter_id: str, config_path: str, customer_id: str) -> None:
    """Show encounter details with all source events.

    ENCOUNTER_ID is the encounter identifier.
    """
    try:
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            # Get encounter record
            encounters: list[dict[str, Any]] = adapter.read_source(
                "admission_events_unified",
                "SELECT * FROM admission_events_unified WHERE encounter_id = :eid",
                {"eid": encounter_id},
            )
            if not encounters:
                click.echo(f"Encounter {encounter_id} not found.")
                return

            enc = encounters[0]
            click.echo(f"Encounter: {enc['encounter_id']}")
            click.echo(f"  Patient: {enc.get('patient_key', '')}")
            click.echo(f"  Type: {enc.get('encounter_type', '')}")
            click.echo(f"  Status: {enc.get('status', '')}")
            click.echo(f"  Facility: {enc.get('facility_name', '')}")
            click.echo(f"  Admit: {enc.get('admit_ts', '')}")
            click.echo(f"  Discharge: {enc.get('discharge_ts', '')}")
            click.echo(f"  Confidence: {enc.get('confidence_score', '')}")

            # Get source events
            events: list[dict[str, Any]] = adapter.read_source(
                "asre_encounters_detail",
                "SELECT * FROM asre_encounters_detail WHERE encounter_id = :eid ORDER BY event_ts",
                {"eid": encounter_id},
            )
            if events:
                click.echo(f"\n  Events ({len(events)}):")
                for evt in events:
                    click.echo(
                        f"    {evt.get('event_id', ''):<20} "
                        f"{evt.get('event_type', ''):<20} "
                        f"{evt.get('event_ts', ''):<24} "
                        f"{evt.get('source_system', ''):<20} "
                        f"{evt.get('role_in_encounter', '')}"
                    )
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@inspect_group.command("errors")
@click.option(
    "--last-run",
    is_flag=True,
    default=False,
    help="Show errors from the most recent pipeline run.",
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
def inspect_errors(last_run: bool, config_path: str, customer_id: str) -> None:
    """Show failed events from a pipeline run."""
    try:
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            if last_run:
                # Get latest run_id
                runs: list[dict[str, Any]] = adapter.read_source(
                    "asre_checkpoints",
                    "SELECT run_id FROM asre_checkpoints ORDER BY updated_at DESC LIMIT 1",
                )
                if not runs:
                    click.echo("No pipeline runs found.")
                    return
                run_id: str = runs[0]["run_id"]
            else:
                click.echo("Specify --last-run to view errors from the most recent run.")
                return

            # Query audit log for error entries
            errors: list[dict[str, Any]] = adapter.read_source(
                "asre_audit_log",
                "SELECT * FROM asre_audit_log WHERE run_id = :rid AND detail LIKE :pat ORDER BY timestamp",
                {"rid": run_id, "pat": "%"},
            )
            if not errors:
                click.echo(f"No errors found for run {run_id}.")
                return

            click.echo(f"Errors for run {run_id} ({len(errors)} entries):")
            for err in errors:
                click.echo(
                    f"  [{err.get('action', '')}] {err.get('entity_type', '')}/"
                    f"{err.get('entity_id', '')}: {err.get('detail', '')}"
                )
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.group("episodes", invoke_without_command=True)
@click.option(
    "--recompute",
    is_flag=True,
    default=False,
    help="Recompute episodes from materialized encounters without re-running full pipeline.",
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
def episodes(
    ctx: click.Context,
    recompute: bool,
    config_path: str,
    customer_id: str,
) -> None:
    """Manage episode computation."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["customer_id"] = customer_id

    if recompute:
        _recompute_episodes(config_path, customer_id)
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _recompute_episodes(config_path: str, customer_id: str) -> None:
    """Recompute episodes from materialized encounters.

    Reads encounters from admission_events_unified, then runs only the
    three episode stages (stitch, materialize, quality) without re-running
    ingest, canonicalize, stitch, dedup, reconcile, or score.
    """
    try:
        _validate_license_or_exit()
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            # Read all encounters from admission_events_unified
            records: list[dict[str, Any]] = adapter.read_source(
                "admission_events_unified",
                "SELECT * FROM admission_events_unified",
            )

            if not records:
                click.echo("No encounters found. Nothing to recompute.")
                return

            # Convert DB records to Encounter objects
            from asre.episode.stage import (
                EpisodeMaterializeStage,
                EpisodeQualityStage,
                EpisodeStitchStage,
                record_to_encounter,
            )
            from asre.models.batch import EventBatch
            from asre.pipeline.runner import PipelineContext

            encounters = [record_to_encounter(r) for r in records]

            # Load episode stitching config if available
            global_config = load_config(config_path, customer_id)
            ep_config: dict[str, Any] = {}
            if hasattr(global_config, "episode_stitching"):
                ep_config["episode_stitching"] = global_config.episode_stitching
            ep_config["adapter"] = adapter

            # Build pipeline context
            from datetime import datetime, timezone

            run_id = f"recompute_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            context = PipelineContext(
                run_id=run_id,
                config=ep_config,
                mode="recompute",
            )
            batch = EventBatch(batch_id=run_id, events=[])

            # Run episode stitch
            stitch_stage = EpisodeStitchStage()
            stitch_stage.encounters_in = encounters
            stitch_stage.run(batch, context)

            # Run episode materialize
            materialize_stage = EpisodeMaterializeStage()
            materialize_stage.episodes_in = list(stitch_stage.episodes)
            materialize_stage.run(batch, context)

            # Run episode quality
            quality_stage = EpisodeQualityStage()
            quality_stage.episodes_in = list(stitch_stage.episodes)
            quality_stage.run(batch, context)

            click.echo(
                f"Episode recomputation complete: "
                f"{len(encounters)} encounters -> "
                f"{quality_stage.episode_count} episodes, "
                f"readmission_rate={quality_stage.readmission_rate:.2f}, "
                f"mean_confidence={quality_stage.mean_confidence:.2f}"
            )
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


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
        _validate_license_or_exit()
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

            # Add source's canonical_name as alias on the target
            source_name: str = source_records[0]["canonical_name"]
            raw_aliases = target_records[0].get("aliases", "[]")
            target_aliases: list[str] = (
                json.loads(raw_aliases) if isinstance(raw_aliases, str) else raw_aliases
            )
            if source_name not in target_aliases:
                target_aliases.append(source_name)
                adapter.execute_dml(
                    "UPDATE asre_facility_registry SET aliases = :aliases "
                    "WHERE canonical_id = :cid",
                    {"aliases": json.dumps(target_aliases), "cid": target},
                )

            # Delete the source facility record
            adapter.execute_dml(
                "DELETE FROM asre_facility_registry WHERE canonical_id = :fid",
                {"fid": facility_id},
            )

            # Repoint encounters from old facility to target
            adapter.execute_dml(
                "UPDATE admission_events_unified SET facility_canonical_id = :target_id "
                "WHERE facility_canonical_id = :source_id",
                {"target_id": target, "source_id": facility_id},
            )

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


@cli.command("migrate")
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
@click.option(
    "--rollback",
    "rollback_version",
    type=int,
    default=None,
    help="Rollback migrations to this version (0 = rollback all).",
)
def migrate(config_path: str, customer_id: str, rollback_version: int | None) -> None:
    """Run or rollback database migrations."""
    try:
        _validate_license_or_exit()
        adapter = _get_diagnostic_adapter(config_path, customer_id)
        try:
            from asre.migration.migrator import Migrator

            migrator = Migrator(adapter)

            if rollback_version is not None:
                result = migrator.rollback(rollback_version)
                click.echo(
                    f"Rollback complete: reverted {result.applied} migration(s), "
                    f"schema version now {result.current_version}."
                )
            else:
                result = migrator.run()
                click.echo(
                    f"Migrations complete: applied {result.applied}, "
                    f"schema version now {result.current_version}."
                )
        finally:
            adapter.disconnect()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("build-registry")
@click.option(
    "--nppes",
    required=True,
    type=click.Path(exists=True),
    help="Path to NPPES organization extract CSV.",
)
@click.option(
    "--othernames",
    default=None,
    type=click.Path(exists=True),
    help="Path to NPPES other-names extract CSV.",
)
@click.option(
    "--pos-hospital",
    default=None,
    type=click.Path(exists=True),
    help="Path to CMS POS hospital CSV.",
)
@click.option(
    "--pos-iqies",
    default=None,
    type=click.Path(exists=True),
    help="Path to CMS POS iQIES CSV.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output path for SQLite database file.",
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Limit rows per source (for testing).",
)
def build_registry(
    nppes: str,
    othernames: str | None,
    pos_hospital: str | None,
    pos_iqies: str | None,
    output: str,
    limit: int | None,
) -> None:
    """Build SQLite facility registry from NPPES + CMS POS sources.

    Combines NPPES organization NPIs and CMS POS CCNs into a single
    SQLite database for NPI/CCN lookup during facility matching.
    """
    import tempfile
    from pathlib import Path

    from asre.facility.registry_builder import build_combined_registry
    from asre.facility.sqlite_registry import build_sqlite_from_csv

    try:
        # Step 1: Build intermediate CSV in a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp:
            tmp_csv = Path(tmp.name)

        click.echo("Building combined registry CSV ...")
        build_combined_registry(
            nppes_path=Path(nppes),
            othername_path=Path(othernames) if othernames else None,
            pos_hospital_path=Path(pos_hospital) if pos_hospital else None,
            pos_iqies_path=Path(pos_iqies) if pos_iqies else None,
            output_path=tmp_csv,
            limit=limit,
        )

        # Step 2: Convert CSV to SQLite
        click.echo("Converting to SQLite ...")
        count = build_sqlite_from_csv(tmp_csv, output)

        db_path = Path(output)
        size_mb = db_path.stat().st_size / (1024 * 1024)
        click.echo(f"Registry built: {count:,} rows, {size_mb:.1f} MB at {output}")

        # Clean up temp file
        tmp_csv.unlink(missing_ok=True)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
