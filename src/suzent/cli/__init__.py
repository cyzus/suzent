"""
Suzent CLI — Your Digital Co-worker Manager.

This package splits CLI commands into focused modules:
- main:   start, doctor, update, upgrade, setup-build-tools
- node:   list, status, describe, invoke (companion devices)
- agent:  chat, status
- config: show, get, set
"""

import typer

# Must precede every other suzent import: quiets logging that would otherwise
# escape onto stderr while the modules below are imported.
import suzent.cli._early_logging  # noqa: F401
from suzent.cli.acp import register_acp_command
from suzent.cli.agent import agent_app
from suzent.cli.config import config_app
from suzent.cli.main import (
    format_version_line,
    get_project_root,
    register_commands,
    configure_logging,
    load_environment,
    _configure_console_encoding,
)
from suzent.cli.cron import cron_app
from suzent.cli.heartbeat import heartbeat_app
from suzent.cli.mcp import mcp_app
from suzent.cli.node import node_app
from suzent.cli.pair import pair_app
from suzent.cli.skill import skill_app
from suzent.cli.service import service_app

app = typer.Typer(help="Suzent CLI - Your Digital Co-worker Manager")


def _version_callback(value: bool) -> None:
    """Print the version and exit before any subcommand is resolved."""
    if not value:
        return
    typer.echo(format_version_line(get_project_root()))
    raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging (DEBUG level)"
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the Suzent version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """
    Suzent CLI - Your Digital Co-worker Manager.
    """
    _configure_console_encoding()
    if ctx.invoked_subcommand == "acp":
        # `suzent acp` speaks JSON-RPC on stdout, so no log line may land there
        # -- not even the DEBUG output -v would otherwise enable.
        from suzent.acp.server import redirect_logs_to_stderr

        redirect_logs_to_stderr("DEBUG" if verbose else "WARNING")
    else:
        configure_logging(verbose)
    load_environment()


# Register top-level commands (start, doctor, update, upgrade, setup-build_tools)
register_commands(app)
register_acp_command(app)

# Attach subcommand groups
app.add_typer(node_app, name="nodes")
app.add_typer(agent_app, name="agent")
app.add_typer(config_app, name="config")
app.add_typer(cron_app, name="cron")
app.add_typer(heartbeat_app, name="heartbeat")
app.add_typer(pair_app, name="pair")
app.add_typer(mcp_app, name="mcp")
app.add_typer(skill_app, name="skill")
app.add_typer(service_app, name="service")

if __name__ == "__main__":
    app()
