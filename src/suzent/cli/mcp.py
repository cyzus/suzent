"""
CLI subcommands for MCP (Model Context Protocol) server management.

Usage:
    suzent mcp list
    suzent mcp add sqlite --command npx --args "-y,@modelcontextprotocol/server-sqlite,/db"
    suzent mcp add github --url https://example.com/mcp --header "Authorization: Bearer xxx"
    suzent mcp remove sqlite
    suzent mcp enable sqlite
    suzent mcp disable sqlite

Backend routes (see src/suzent/routes/mcp_routes.py):
    GET  /mcp_servers           -> {urls, stdio, headers, enabled} parallel dicts
    POST /mcp_servers           -> add (409 if name exists)
    POST /mcp_servers/remove    -> {name}
    POST /mcp_servers/enabled   -> {name, enabled}
"""

import asyncio
from typing import Optional

import typer

from suzent.client import get_client
from suzent.client.base import ClientError

mcp_app = typer.Typer(help="Manage MCP (Model Context Protocol) servers.")


def _parse_kv_list(items: list[str], what: str) -> dict[str, str]:
    """Parse ['KEY: VALUE', 'KEY2=VALUE2'] into a dict."""
    out: dict[str, str] = {}
    for item in items:
        if ":" in item and (item.index(":") < item.index("=") or "=" not in item):
            key, value = item.split(":", 1)
        elif "=" in item:
            key, value = item.split("=", 1)
        else:
            typer.echo(
                f"❌ Invalid {what} (expected 'KEY: VALUE' or 'KEY=VALUE'): {item}"
            )
            raise typer.Exit(code=1)
        out[key.strip()] = value.strip()
    return out


@mcp_app.command("list")
def list_servers():
    """List configured MCP servers with transport and enabled state."""

    async def _run():
        try:
            client = get_client()
            data = await client.mcp.list()
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

        urls = data.get("urls", {})
        stdio = data.get("stdio", {})
        enabled = data.get("enabled", {})

        names = sorted(set(urls) | set(stdio) | set(enabled))
        if not names:
            typer.echo("No MCP servers configured.")
            return

        for name in names:
            transport = "url" if name in urls else "stdio" if name in stdio else "?"
            state = "ON " if enabled.get(name) else "OFF"
            detail = urls.get(name) or stdio.get(name, {}).get("command", "")
            typer.echo(f"  [{state}]  {name:<20}  {transport:<6}  {detail}")

        typer.echo(
            f"\n  {len(names)} server(s), "
            f"{sum(1 for n in names if enabled.get(n))} enabled"
        )

    asyncio.run(_run())


@mcp_app.command("add")
def add_server(
    name: str = typer.Argument(..., help="Server name"),
    url: Optional[str] = typer.Option(None, "--url", help="HTTP MCP server URL"),
    header: list[str] = typer.Option(
        [], "--header", "-H", help="HTTP header 'Key: Value' (repeatable, --url only)"
    ),
    command: Optional[str] = typer.Option(
        None, "--command", help="Stdio command (e.g. npx)"
    ),
    args: Optional[str] = typer.Option(
        None, "--args", help="Comma-separated args for the stdio command"
    ),
    env: list[str] = typer.Option(
        [], "--env", "-e", help="Env var 'KEY=VALUE' (repeatable, --command only)"
    ),
):
    """Register a new MCP server. Provide either --url or --command."""

    if not url and not command:
        typer.echo("❌ Provide either --url or --command.")
        raise typer.Exit(code=1)
    if url and command:
        typer.echo("❌ Provide only one of --url or --command, not both.")
        raise typer.Exit(code=1)

    headers = _parse_kv_list(header, "header") if header else None
    stdio = None
    if command:
        stdio = {"command": command}
        if args:
            stdio["args"] = [a.strip() for a in args.split(",") if a.strip()]
        if env:
            stdio["env"] = _parse_kv_list(env, "env")

    async def _run():
        try:
            client = get_client()
            await client.mcp.add(name, url=url, headers=headers, stdio=stdio)
            typer.echo(f"Added MCP server: {name}")
            typer.echo("  (enabled by default — use 'suzent mcp disable' to turn off)")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@mcp_app.command("remove")
def remove_server(name: str = typer.Argument(..., help="Server name to remove")):
    """Remove an MCP server from the registry."""

    async def _run():
        try:
            client = get_client()
            await client.mcp.remove(name)
            typer.echo(f"Removed MCP server: {name}")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@mcp_app.command("enable")
def enable_server(name: str = typer.Argument(..., help="Server name to enable")):
    """Enable an MCP server."""
    _set_enabled(name, True)


@mcp_app.command("disable")
def disable_server(name: str = typer.Argument(..., help="Server name to disable")):
    """Disable an MCP server."""
    _set_enabled(name, False)


def _set_enabled(name: str, enabled: bool):
    async def _run():
        try:
            client = get_client()
            await client.mcp.set_enabled(name, enabled)
            typer.echo(f"{'Enabled' if enabled else 'Disabled'} MCP server: {name}")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
