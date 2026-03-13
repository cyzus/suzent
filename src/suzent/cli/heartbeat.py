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
    suzent heartbeat interval 15   # same

"""

import os
import typer
from typing import Optional

from suzent.cli._http import _http_get, _http_post

heartbeat_app = typer.Typer(
    help="Manage the heartbeat system (periodic agent check-ins)."
)


def _resolve_chat_id(chat_id: Optional[str]) -> Optional[str]:
    """Return chat_id if given, otherwise fall back to $CHAT_ID env var."""
    return chat_id or os.environ.get("CHAT_ID") or None


def _require_chat_id(chat_id: Optional[str]) -> str:
    """Same as _resolve_chat_id, but exits with an error if no ID is found."""
    resolved = _resolve_chat_id(chat_id)
    if not resolved:
        typer.echo(
            "Error: --chat-id is required (or set the CHAT_ID environment variable).",
            err=True,
        )
        raise typer.Exit(1)
    return resolved


@heartbeat_app.command("status")
def heartbeat_status(
    chat_id: Optional[str] = typer.Option(
        None, "--chat-id", "-c", help="ID of the chat session (or $CHAT_ID env var)"
    ),
):
    """Show heartbeat status."""
    chat_id = _resolve_chat_id(chat_id)
    url = f"/heartbeat/status?chat_id={chat_id}" if chat_id else "/heartbeat/status"
    data = _http_get(url)

    if chat_id:
        # Per-session detail
        enabled = data.get("enabled", False)
        running = data.get("running", False)
        interval = data.get("interval_minutes")

        status = "ENABLED" if enabled else "DISABLED"
        if enabled and running:
            status = "RUNNING"

        typer.echo(f"  Heartbeat:     {status}")
        typer.echo(f"  Chat ID:       {chat_id}")
        if interval is not None:
            typer.echo(f"  Interval:      {interval} minutes")

        if data.get("last_run_at"):
            typer.echo(f"  Last run:      {data['last_run_at']}")

        if data.get("last_result"):
            result = data["last_result"]
            if result == "HEARTBEAT_OK":
                typer.echo("  Last result:   OK (nothing needed attention)")
            else:
                typer.echo(f"  Last result:   {result[:100]}")

        if data.get("last_error"):
            typer.echo(f"  Last error:    {data['last_error']}")
    else:
        # Global overview
        running = data.get("running", False)
        polling = data.get("polling_interval")
        sessions = data.get("active_sessions", [])

        typer.echo(f"  Runner:        {'RUNNING' if running else 'STOPPED'}")
        if polling is not None:
            typer.echo(f"  Polling:       {polling} minutes")
        typer.echo(f"  Active:        {len(sessions)} session(s)")

        if sessions:
            typer.echo("")
            typer.echo(f"  {'CHAT ID':<38}  {'TITLE':<30}  {'INTERVAL':>8}  LAST RUN")
            typer.echo(f"  {'-' * 38}  {'-' * 30}  {'-' * 8}  {'-' * 20}")
            for s in sessions:
                cid = s.get("chat_id", "")[:36]
                title = (s.get("title") or "")[:30]
                interval = f"{s.get('interval_minutes', 30)}m"
                last_run = s.get("last_run_at") or "never"
                if len(last_run) > 20:
                    last_run = last_run[:19]
                typer.echo(f"  {cid:<38}  {title:<30}  {interval:>8}  {last_run}")
        else:
            typer.echo("\n  No sessions have heartbeat enabled.")


@heartbeat_app.command("enable")
def heartbeat_enable(
    chat_id: Optional[str] = typer.Option(
        None, "--chat-id", "-c", help="ID of the chat session (or $CHAT_ID env var)"
    ),
):
    """Enable the heartbeat system."""
    chat_id = _require_chat_id(chat_id)
    data = _http_post("/heartbeat/enable", data={"chat_id": chat_id} if chat_id else {})
    if data.get("success"):
        typer.echo(f"Heartbeat enabled{' for chat ' + chat_id if chat_id else ''}.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")


@heartbeat_app.command("disable")
def heartbeat_disable(
    chat_id: Optional[str] = typer.Option(
        None, "--chat-id", "-c", help="ID of the chat session (or $CHAT_ID env var)"
    ),
):
    """Disable the heartbeat system."""
    chat_id = _require_chat_id(chat_id)
    data = _http_post(
        "/heartbeat/disable", data={"chat_id": chat_id} if chat_id else {}
    )
    if data.get("success"):
        typer.echo(f"Heartbeat disabled{' for chat ' + chat_id if chat_id else ''}.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")


@heartbeat_app.command("run")
def heartbeat_run(
    chat_id: Optional[str] = typer.Option(
        None, "--chat-id", "-c", help="ID of the chat session (or $CHAT_ID env var)"
    ),
):
    """Trigger an immediate heartbeat tick."""
    chat_id = _require_chat_id(chat_id)
    data = _http_post(
        "/heartbeat/trigger", data={"chat_id": chat_id} if chat_id else {}
    )
    if data.get("success"):
        typer.echo(f"Heartbeat triggered{' for chat ' + chat_id if chat_id else ''}.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")


@heartbeat_app.command("interval")
def heartbeat_interval(
    minutes: int = typer.Argument(..., help="Interval in minutes (minimum 1)"),
    chat_id: Optional[str] = typer.Option(
        None, "--chat-id", "-c", help="ID of the chat session (or $CHAT_ID env var)"
    ),
):
    """Set the heartbeat interval in minutes."""
    if minutes < 1:
        typer.echo("Error: interval must be at least 1 minute.")
        raise typer.Exit(1)

    chat_id = _require_chat_id(chat_id)
    payload = {"interval_minutes": minutes}
    if chat_id:
        payload["chat_id"] = chat_id

    data = _http_post("/heartbeat/interval", data=payload)
    if data.get("success"):
        typer.echo(
            f"Heartbeat interval set to {minutes} minutes{' for chat ' + chat_id if chat_id else ''}."
        )
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")
