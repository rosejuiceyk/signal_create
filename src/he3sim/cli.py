"""Command-line interface for Phase 0 configuration validation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from he3sim.config import config_hash, load_config

app = typer.Typer(
    name="he3sim",
    help="He-3 pulse simulation research tools (Phase 0 foundation).",
    no_args_is_help=True,
)


@app.callback()
def root_command() -> None:
    """Expose Phase 0 commands under the stable ``he3sim`` command group."""


@app.command("validate-config")
def validate_config_command(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML configuration to validate."),
    ],
) -> None:
    """Validate one YAML configuration and print its deterministic hash."""
    try:
        config = load_config(config_path)
    except (OSError, ValueError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"invalid configuration: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"valid configuration: {config_path}")
    typer.echo(f"config_hash: {config_hash(config)}")


def main() -> None:
    """Run the Typer application."""
    app()
