"""
CLI subcommands for viewing and managing configuration.

Usage:
    suzent config show
    suzent config get <key>
    suzent config set <key> <value>
"""

import json
import typer
import asyncio
from suzent.client import get_client
from suzent.client.base import ClientError
from suzent.cli.utils import infer_type

config_app = typer.Typer(help="View and manage Suzent configuration")


@config_app.command("show")
def config_show():
    """Show raw system configuration fields."""

    async def _run():
        try:
            client = get_client()
            data = await client.config.get()
            typer.echo(json.dumps(data, indent=2))
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@config_app.command("get")
def config_get(
    key: str = typer.Argument(help="Configuration key to read"),
):
    """Read a specific configuration value."""

    async def _run():
        try:
            client = get_client()
            data = await client.config.get()
            value = data.get(key)
            if value is None:
                typer.echo(f"❌ Key '{key}' not found in config")
                raise typer.Exit(code=1)

            if isinstance(value, (dict, list)):
                typer.echo(json.dumps(value, indent=2))
            else:
                typer.echo(str(value))
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="The preference key (e.g. general.theme)"),
    value: str = typer.Argument(
        help="The flat scalar value or valid JSON string (e.g. dark, true, 42)"
    ),
):
    """Update a specific user preference."""

    async def _run():
        try:
            parsed = infer_type(value)
            client = get_client()
            await client.config.update_preferences({key: parsed})
            typer.echo(f"✅ Preference '{key}' updated successfully.")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
