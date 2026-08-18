"""CLI commands for the Suzent background service."""

from __future__ import annotations

import json

import typer

from suzent.service import get_service_controller
from suzent.service.runtime import run_service

service_app = typer.Typer(help="Manage the Suzent background service.")


@service_app.command("run")
def service_run() -> None:
    """Run the service in the foreground for debugging or supervision."""
    run_service()


@service_app.command("install")
def service_install(
    start: bool = typer.Option(
        True, "--start/--no-start", help="Start after installing."
    ),
) -> None:
    """Install the current-user service and enable login startup."""
    controller = get_service_controller()
    try:
        controller.install(start=start)
    except Exception as exc:
        typer.echo(f"Failed to install Suzent service: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Suzent service installed.")


@service_app.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the service without deleting user data."""
    try:
        get_service_controller().uninstall()
    except Exception as exc:
        typer.echo(f"Failed to uninstall Suzent service: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("Suzent service uninstalled. User data was preserved.")


def _run_action(action: str) -> None:
    controller = get_service_controller()
    try:
        getattr(controller, action)()
    except Exception as exc:
        typer.echo(f"Failed to {action} Suzent service: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Suzent service {action} requested.")


@service_app.command("start")
def service_start() -> None:
    """Start the installed service."""
    _run_action("start")


@service_app.command("stop")
def service_stop() -> None:
    """Stop the running service."""
    _run_action("stop")


@service_app.command("restart")
def service_restart() -> None:
    """Restart the installed service."""
    _run_action("restart")


@service_app.command("status")
def service_status(
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show installation, runtime, readiness, and memory status."""
    status = get_service_controller().status()
    payload = status.to_dict()
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(f"Installed: {'yes' if status.installed else 'no'}")
    typer.echo(f"Running:   {'yes' if status.running else 'no'}")
    typer.echo(f"Ready:     {'yes' if status.ready else 'no'}")
    if status.pid is not None:
        typer.echo(f"PID:       {status.pid}")
    if status.port is not None:
        typer.echo(f"Address:   http://127.0.0.1:{status.port}")
    if status.rss_bytes is not None:
        typer.echo(f"Memory:    {status.rss_bytes / 1024 / 1024:.1f} MiB")
    if status.error:
        typer.echo(f"Error:     {status.error}")


@service_app.command("logs")
def service_logs() -> None:
    """Print the service log path."""
    typer.echo(str(get_service_controller().platform_manager.log_path))


@service_app.command("doctor")
def service_doctor() -> None:
    """Check service installation, process identity, readiness, and resources."""
    status = get_service_controller().status()
    checks = [
        ("Service definition", status.installed),
        ("Login autostart", status.autostart),
        ("Service process", status.running),
        ("Runtime readiness", status.ready),
    ]
    for label, passed in checks:
        typer.echo(f"{'OK' if passed else '--':>2}  {label}")
    if status.running:
        typer.echo(f"OK  PID {status.pid} on 127.0.0.1:{status.port}")
        if status.rss_bytes is not None:
            typer.echo(f"OK  RSS {status.rss_bytes / 1024 / 1024:.1f} MiB")
    if status.error:
        typer.echo(f"!!  {status.error}")
    if status.installed and not status.ready:
        raise typer.Exit(code=1)
