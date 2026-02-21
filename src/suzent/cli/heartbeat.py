"""
CLI subcommands for heartbeat management.

Usage:
    suzent heartbeat status
    suzent heartbeat enable
    suzent heartbeat disable
    suzent heartbeat run
"""

import typer

from suzent.cli._http import _http_get, _http_post

heartbeat_app = typer.Typer(
    help="Manage the heartbeat system (periodic agent check-ins)."
)


@heartbeat_app.command("status")
def heartbeat_status():
    """Show heartbeat status."""
    data = _http_get("/heartbeat/status")

    enabled = data.get("enabled", False)
    running = data.get("running", False)
    interval = data.get("interval_minutes", 0)
    md_exists = data.get("heartbeat_md_exists", False)

    status = "ENABLED" if enabled else "DISABLED"
    if enabled and running:
        status = "RUNNING"

    typer.echo(f"  Heartbeat:     {status}")
    typer.echo(f"  Interval:      {interval} minutes")
    typer.echo(f"  HEARTBEAT.md:  {'found' if md_exists else 'not found'}")

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

    if not md_exists:
        typer.echo(
            "\n  To enable heartbeat, create /shared/HEARTBEAT.md with your checklist."
            "\n  See config/HEARTBEAT.example.md for an example."
        )


@heartbeat_app.command("enable")
def heartbeat_enable():
    """Enable the heartbeat system."""
    data = _http_post("/heartbeat/enable")
    if data.get("success"):
        typer.echo("Heartbeat enabled.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")


@heartbeat_app.command("disable")
def heartbeat_disable():
    """Disable the heartbeat system."""
    data = _http_post("/heartbeat/disable")
    if data.get("success"):
        typer.echo("Heartbeat disabled.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")


@heartbeat_app.command("run")
def heartbeat_run():
    """Trigger an immediate heartbeat tick."""
    data = _http_post("/heartbeat/trigger")
    if data.get("success"):
        typer.echo("Heartbeat triggered.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")


@heartbeat_app.command("interval")
def heartbeat_interval(
    minutes: int = typer.Argument(..., help="Interval in minutes (minimum 1)"),
):
    """Set the heartbeat interval in minutes."""
    if minutes < 1:
        typer.echo("Error: interval must be at least 1 minute.")
        raise typer.Exit(1)
    data = _http_post("/heartbeat/interval", data={"interval_minutes": minutes})
    if data.get("success"):
        typer.echo(f"Heartbeat interval set to {minutes} minutes.")
    else:
        typer.echo(f"Failed: {data.get('error', 'unknown error')}")
