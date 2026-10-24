"""
CLI subcommands for plugins.

Usage:
    suzent plugin list
    suzent plugin install telegram     # by id or alias
    suzent plugin remove slack
    suzent plugin status
    suzent plugin sync                 # install what enabled plugins need

When the server is running, install and remove go through it, so the change
applies at once with no restart. Otherwise they edit the plugin state and
install packages directly, and the server loads the result when it starts.
"""

import typer

plugin_app = typer.Typer(help="Manage plugins (list, install, remove, status).")


def _manager():
    # Imported here so `suzent --help` stays clear of pydantic and the tool stack.
    from suzent.plugins import get_plugin_manager

    return get_plugin_manager()


def _project_dir():
    from suzent.config.paths import PROJECT_DIR

    return PROJECT_DIR


def _resolve(name: str):
    record = _manager().resolve(name)
    if record is None:
        typer.echo(f"❌ No plugin named '{name}'. Run `suzent plugin list`.")
        raise typer.Exit(code=1)
    return record


def _install_dependencies(record) -> None:
    from suzent.plugins.deps import DependencyError

    if not (record.manifest.extras or record.manifest.dependencies):
        return
    try:
        _manager().install_dependencies(record, _project_dir())
    except DependencyError as exc:
        typer.echo(f"❌ {exc}")
        typer.echo("   The plugin stays enabled; run `suzent plugin sync` to retry.")
        raise typer.Exit(code=1)


def _via_server(action: str, name: str) -> dict | None:
    """Have a running server apply ``action``; None when no server is running."""
    import asyncio

    from suzent.client import get_client
    from suzent.client.base import ClientError, ServerUnavailableError

    async def call() -> dict:
        client = get_client()
        try:
            api = client.plugins
            return await (api.install if action == "install" else api.remove)(name)
        finally:
            await client.aclose()

    try:
        return asyncio.run(call())
    except ServerUnavailableError:
        return None
    except ClientError as exc:
        typer.echo(f"❌ {exc}")
        raise typer.Exit(code=1)


@plugin_app.command("list")
def list_plugins():
    """List plugins and whether each is enabled."""
    records = _manager().discover()
    if not records:
        typer.echo("No plugins found.")
        return
    for record in sorted(records.values(), key=lambda r: r.id):
        if record.status == "error":
            state = "ERR"
        else:
            state = "ON " if record.enabled else "OFF"
        aliases = (
            f" ({', '.join(record.manifest.aliases)})"
            if record.manifest.aliases
            else ""
        )
        typer.echo(
            f"  [{state}]  {record.id + aliases:<48}  {record.source:<9}  {record.manifest.description}"
        )
        if record.error:
            typer.echo(f"           {record.error}")
    enabled = sum(1 for record in records.values() if record.enabled)
    typer.echo(f"\n  {len(records)} plugin(s), {enabled} enabled")


@plugin_app.command("install")
def install_plugin(name: str = typer.Argument(..., help="Plugin id or alias")):
    """Enable a plugin and install the packages it needs."""
    record = _resolve(name)
    if record.status == "error":
        typer.echo(f"❌ '{record.id}' cannot be loaded: {record.error}")
        raise typer.Exit(code=1)
    if record.has_code and record.source != "builtin":
        typer.echo("  ⚠️  This plugin's code runs inside Suzent with your permissions.")
    if record.manifest.extras or record.manifest.dependencies:
        typer.echo(f"  • Installing packages for '{record.id}'...")
    if _via_server("install", name) is not None:
        typer.echo(f"Enabled '{record.id}'. It is active in the running server.")
        return
    _manager().set_enabled(record.id, True, requested_as=name)
    _install_dependencies(record)
    typer.echo(f"Enabled '{record.id}'. It loads when Suzent starts.")


@plugin_app.command("remove")
def remove_plugin(name: str = typer.Argument(..., help="Plugin id or alias")):
    """Disable a plugin. Its packages are removed on the next upgrade."""
    record = _resolve(name)
    if _via_server("remove", name) is not None:
        typer.echo(f"Disabled '{record.id}'. The running server has unloaded it.")
        return
    _manager().set_enabled(record.id, False)
    typer.echo(f"Disabled '{record.id}'.")


@plugin_app.command("sync")
def sync_plugins():
    """Install the packages every enabled plugin needs."""
    manager = _manager()
    enabled = [r for r in manager.discover().values() if r.enabled]
    for record in enabled:
        if manager.missing_packages(record):
            typer.echo(f"  • Installing packages for '{record.id}'...")
            _install_dependencies(record)
    typer.echo(f"Packages are in place for {len(enabled)} enabled plugin(s).")


@plugin_app.command("status")
def plugin_status():
    """Show enabled plugins, missing packages and the upgrade sync command."""
    from suzent.plugins.deps import sync_command

    manager = _manager()
    problems = 0
    for record in sorted(manager.discover().values(), key=lambda r: r.id):
        if not record.enabled:
            continue
        missing = manager.missing_packages(record)
        problems += bool(missing or record.error)
        detail = record.error or (f"missing: {', '.join(missing)}" if missing else "ok")
        typer.echo(f"  {record.id:<24}  {detail}")
    typer.echo(
        f"\n  Upgrade runs: {' '.join(sync_command('uv', manager.enabled_extras()))}"
    )
    if problems:
        typer.echo("  Run `suzent plugin sync` to install missing packages.")
        raise typer.Exit(code=1)
