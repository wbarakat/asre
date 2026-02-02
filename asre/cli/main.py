"""ASRE CLI entry point."""

from __future__ import annotations

import sys

import click

from asre.config.loader import load_config


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


@cli.command("test-connection")
def test_connection() -> None:
    """Test warehouse connectivity."""
    click.echo("Not yet implemented.")


if __name__ == "__main__":
    cli()
