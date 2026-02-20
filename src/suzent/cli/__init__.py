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
from suzent.cli.main import register_commands, configure_logging, load_environment
from suzent.cli.nodes import nodes_app

app = typer.Typer(help="Suzent CLI - Your Digital Co-worker Manager")


@app.callback()
def main(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging (DEBUG level)"
    ),
):
    """
    Suzent CLI - Your Digital Co-worker Manager.
    """
    configure_logging(verbose)
    load_environment()


# Register top-level commands (start, doctor, upgrade, setup-build_tools)
register_commands(app)

# Attach subcommand groups
app.add_typer(nodes_app, name="nodes")
app.add_typer(agent_app, name="agent")
app.add_typer(config_app, name="config")

if __name__ == "__main__":
    app()
