"""ASRE CLI entry point."""

import click


@click.group()
def cli() -> None:
    """ASRE - Admission Signal Reliability Engine."""


if __name__ == "__main__":
    cli()
