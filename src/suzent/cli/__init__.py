"""
Suzent CLI — Your Digital Co-worker Manager.

This package splits CLI commands into focused modules:
- main:   start, doctor, upgrade, setup-build-tools
- nodes:  list, status, describe, invoke (companion devices)
- agent:  chat, status
- config: show, get, set
"""

import typer

from suzent.cli._http import _http_get, _http_post  # noqa: F401 — re-export for test patching
from suzent.cli.agent import agent_app
from suzent.cli.config import config_app
from suzent.cli.cron import cron_app
from suzent.cli.heartbeat import heartbeat_app
from suzent.cli.main import register_commands
from suzent.cli.nodes import nodes_app

app = typer.Typer(help="Suzent CLI - Your Digital Co-worker Manager")

# Register top-level commands (start, doctor, upgrade, setup-build_tools)
register_commands(app)

# Attach subcommand groups
app.add_typer(nodes_app, name="nodes")
app.add_typer(agent_app, name="agent")
app.add_typer(config_app, name="config")
app.add_typer(cron_app, name="cron")
app.add_typer(heartbeat_app, name="heartbeat")

if __name__ == "__main__":
    app()
