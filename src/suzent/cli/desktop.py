"""Install the agent-desktop CLI after an explicit yes."""

import asyncio

import typer

desktop_app = typer.Typer(help="Install the desktop control program (agent-desktop).")


def _via_server() -> dict | None:
    from suzent.client import get_client
    from suzent.client.base import ClientError, ServerUnavailableError

    async def call() -> dict:
        client = get_client()
        try:
            return await client.plugins.install_desktop_runtime()
        finally:
            await client.aclose()

    try:
        return asyncio.run(call())
    except ServerUnavailableError:
        return None
    except ClientError as exc:
        typer.echo(f"❌ {exc}")
        raise typer.Exit(code=1)


@desktop_app.command("status")
def desktop_status() -> None:
    """Show whether agent-desktop is available, without downloading it."""
    from suzent.tools.desktop.install import runtime_status

    status = runtime_status()
    if status["installed"]:
        typer.echo(f"agent-desktop: {status['source']} ({status['path']})")
        return
    typer.echo("agent-desktop is not installed.")
    typer.echo("Run `suzent desktop install` to download the pinned 1.0.x release.")


def install_after_consent(*, yes: bool) -> bool:
    """Download after consent. False when the user says no. Raises on failure."""
    from suzent.tools.desktop.install import (
        CONSENT_TEXT,
        DesktopInstallError,
        install_release,
        runtime_status,
    )

    status = runtime_status()
    if status["installed"]:
        typer.echo(
            f"agent-desktop is already available ({status['source']}: {status['path']})."
        )
        return True
    typer.echo(CONSENT_TEXT)
    if not yes and not typer.confirm("Install agent-desktop now?"):
        typer.echo("Skipped. Nothing was downloaded.")
        return False
    remote = _via_server()
    if remote is not None:
        _report(remote)
        return True
    try:
        result = install_release()
    except DesktopInstallError as exc:
        typer.echo(f"❌ {exc}")
        raise typer.Exit(code=1)
    _report(result)
    return True


def _report(result: dict) -> None:
    typer.echo(
        f"Installed agent-desktop ({result.get('source')}): {result.get('path')}"
    )
    if result.get("permissionsGuide") == "started":
        typer.echo("Opened the macOS Accessibility guide.")


@desktop_app.command("install")
def desktop_install(
    yes: bool = typer.Option(
        False, "--yes", help="Install without asking again. You have already agreed."
    ),
) -> None:
    """Download agent-desktop 1.0.x after you confirm."""
    if not install_after_consent(yes=yes):
        raise typer.Exit(code=1)
