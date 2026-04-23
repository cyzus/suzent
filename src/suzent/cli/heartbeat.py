"""
CLI subcommands for heartbeat management.

Usage:
    suzent heartbeat status [--chat-id <id>]
    suzent heartbeat enable [--chat-id <id>]
    suzent heartbeat disable [--chat-id <id>]
    suzent heartbeat run [--chat-id <id>]
    suzent heartbeat interval <minutes> [--chat-id <id>]

If --chat-id is omitted, the CHAT_ID environment variable is used.
This allows the agent to manage its own session's heartbeat from bash:

    suzent heartbeat status        # uses $CHAT_ID automatically
    suzent heartbeat status
    suzent heartbeat enable [--chat <id>]
    suzent heartbeat disable
    suzent heartbeat interval <minutes>

"""

import typer
from typing import Optional
import asyncio
from suzent.client import get_client
from suzent.client.base import ClientError

heartbeat_app = typer.Typer(
    help="Manage the heartbeat system (periodic agent check-ins)."
)


@heartbeat_app.command("status")
def heartbeat_status():
    """Check if the desktop heartbeat ping logic is currently active."""

    async def _run():
        try:
            client = get_client()
            res = await client.heartbeat.status()

            enabled = res.get("enabled", False)
            interval = res.get("interval_minutes", 10)
            last = res.get("last_ping_time", "Never")

            if enabled:
                typer.echo(f"💓 Heartbeat: ENABLED (every {interval} min)")
                typer.echo(f"   Last ping: {last}")
            else:
                typer.echo("🖤 Heartbeat: DISABLED")
        except ClientError as e:
            typer.echo(f"❌ Cannot connect to server: {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@heartbeat_app.command("enable")
def heartbeat_enable(
    chat_id: Optional[str] = typer.Option(
        None, "--chat", "-c", help="Specific chat ID to link the heartbeat to."
    ),
):
    """Enable heartbeat background tracking."""

    async def _run():
        try:
            client = get_client()
            data = await client.heartbeat.enable(chat_id)
            if data.get("success"):
                typer.echo("✅ Heartbeat tracking enabled.")
                if chat_id:
                    typer.echo(f"   Linked to chat: {chat_id}")
            else:
                typer.echo(f"❌ Failed to enable: {data.get('error')}")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@heartbeat_app.command("disable")
def heartbeat_disable():
    """Disable heartbeat background tracking."""

    async def _run():
        try:
            client = get_client()
            data = await client.heartbeat.disable()
            if data.get("success"):
                typer.echo("✅ Heartbeat tracking disabled.")
            else:
                typer.echo(f"❌ Failed to disable: {data.get('error')}")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@heartbeat_app.command("interval")
def heartbeat_set_interval(
    minutes: int = typer.Argument(..., help="Number of minutes between pings"),
):
    """Update the heartbeat interval."""

    async def _run():
        if minutes < 1:
            typer.echo("Interval must be at least 1 minute.")
            raise typer.Exit(code=1)

        payload = {"minutes": minutes}
        try:
            client = get_client()
            data = await client.heartbeat.update_interval(payload)
            if data.get("success"):
                typer.echo(f"✅ Heartbeat interval set to {minutes} minutes.")
            else:
                typer.echo(f"❌ Failed: {data.get('error', 'unknown error')}")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
