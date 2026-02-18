"""
CLI subcommands for viewing and managing configuration.

Usage:
    suzent config show
    suzent config get <key>
    suzent config set <key> <value>
"""

import json

import typer

from suzent.cli._http import _http_get, _http_post

config_app = typer.Typer(help="View and manage Suzent configuration")


@config_app.command("show")
def config_show():
    """Dump the current configuration."""
    data = _http_get("/config")
    typer.echo(json.dumps(data, indent=2))


@config_app.command("get")
def config_get(
    key: str = typer.Argument(help="Configuration key to read"),
):
    """Read a specific configuration value."""
    data = _http_get("/config")
    value = data.get(key)
    if value is None:
        typer.echo(f"❌ Key '{key}' not found in config")
        raise typer.Exit(code=1)

    if isinstance(value, (dict, list)):
        typer.echo(json.dumps(value, indent=2))
    else:
        typer.echo(str(value))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Configuration key to set"),
    value: str = typer.Argument(help="Value to set"),
):
    """Set a configuration value (persisted to config/default.yaml)."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value

    _http_post("/preferences", data={key: parsed})
    typer.echo(f"✅ Set {key} = {value}")
