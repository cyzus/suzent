"""
CLI subcommands for plugins.

Usage:
    suzent plugin list
    suzent plugin enable my-plugin
    suzent plugin disable my-plugin

These read and write the plugin state file directly, so they work while the
server is stopped; a running server picks the change up on its next start.
"""

import typer

plugin_app = typer.Typer(help="Manage plugins (list, enable, disable).")

_RESTART_NOTE = "Restart Suzent for the change to take effect."


def _discovered() -> dict:
    # Imported here so `suzent --help` stays clear of pydantic and the tool stack.
    from suzent.plugins import get_plugin_manager

    return get_plugin_manager().discover()


@plugin_app.command("list")
def list_plugins():
    """List installed plugins and whether each is enabled."""
    records = _discovered()
    if not records:
        typer.echo("No plugins found.")
        return
    for record in sorted(records.values(), key=lambda r: r.id):
        state = (
            "ERR" if record.status == "error" else ("ON " if record.enabled else "OFF")
        )
        where = str(record.path) if record.path else "pip package"
        typer.echo(
            f"  [{state}]  {record.id:<24}  {record.manifest.version:<10}  {where}"
        )
        if record.error:
            typer.echo(f"           {record.error}")
    enabled = sum(1 for record in records.values() if record.enabled)
    typer.echo(f"\n  {len(records)} plugin(s), {enabled} enabled")


def _set_enabled(plugin_id: str, enabled: bool) -> None:
    from suzent.plugins import get_plugin_manager

    if enabled and plugin_id not in _discovered():
        typer.echo(f"❌ No plugin named '{plugin_id}'. Run `suzent plugin list`.")
        raise typer.Exit(code=1)
    get_plugin_manager().set_enabled(plugin_id, enabled)
    typer.echo(f"{'Enabled' if enabled else 'Disabled'} '{plugin_id}'. {_RESTART_NOTE}")


@plugin_app.command("enable")
def enable_plugin(plugin_id: str = typer.Argument(..., help="Plugin id")):
    """Enable a plugin. Its code runs inside Suzent with your permissions."""
    _set_enabled(plugin_id, True)


@plugin_app.command("disable")
def disable_plugin(plugin_id: str = typer.Argument(..., help="Plugin id")):
    """Disable a plugin."""
    _set_enabled(plugin_id, False)
