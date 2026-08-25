"""CLI entry point that serves Suzent as an ACP agent over stdio.

``suzent acp`` is meant to be *spawned by an ACP client* (Zed, enoxian, any
editor implementing the protocol) rather than run by hand: the client owns the
process, speaks JSON-RPC on its stdin/stdout, and passes the workspace as the
session ``cwd``. See ``docs/02-concepts/nodes/acp.md``.
"""

import asyncio

import typer


def register_acp_command(app: typer.Typer) -> None:
    """Attach the ``acp`` command to the top-level CLI app."""

    @app.command("acp")
    def acp(
        server_url: str = typer.Option(
            None,
            "--server-url",
            help="Backend URL to bridge to (default: the running local backend)",
        ),
        permission_mode: str = typer.Option(
            "default",
            "--permission-mode",
            help=(
                "Permission mode for ACP sessions: 'default' asks the client to "
                "approve tool calls, 'auto' and 'full_access' never ask"
            ),
        ),
        log_level: str = typer.Option(
            "WARNING",
            "--log-level",
            help="Log level for diagnostics on stderr (stdout carries the protocol)",
        ),
    ):
        """Serve this Suzent as an ACP agent on stdin/stdout."""
        modes = {"default", "auto", "full_access"}
        if permission_mode not in modes:
            # stderr: stdout belongs to the protocol even when we refuse to start.
            typer.secho(
                f"Unknown permission mode '{permission_mode}'. "
                f"Expected one of: {', '.join(sorted(modes))}.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

        from suzent.acp.server import redirect_logs_to_stderr, serve_stdio

        redirect_logs_to_stderr(log_level)
        raise typer.Exit(
            code=asyncio.run(
                serve_stdio(
                    base_url=server_url,
                    permission_mode=permission_mode,
                )
            )
        )
