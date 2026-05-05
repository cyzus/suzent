from __future__ import annotations

from pathlib import Path

import typer

from suzent.core.data_portability import (
    export_data,
    get_data_status,
    import_data,
    sync_pull,
    sync_push,
)

data_app = typer.Typer(help="Manage SUZENT user data, exports, imports, and sync.")


@data_app.command("path")
def data_path() -> None:
    """Print the active data directory."""
    typer.echo(get_data_status().data_dir)


@data_app.command("status")
def data_status() -> None:
    """Print portable data status."""
    status = get_data_status()
    typer.echo(f"Data dir: {status.data_dir}")
    typer.echo(f"Runtime dir: {status.runtime_dir}")
    typer.echo(f"Cache dir: {status.cache_dir}")
    typer.echo("Portable entries:")
    for entry in status.portable_entries:
        typer.echo(f"  - {entry}")


@data_app.command("export")
def data_export(
    output: Path | None = typer.Option(None, "--output", "-o", help="Output zip path"),
) -> None:
    """Export a complete portable data snapshot."""
    result = export_data(output)
    typer.echo(f"Exported data to {result.output_path}")


@data_app.command("import")
def data_import(
    archive: Path = typer.Argument(..., help="Export archive to import"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without writing"),
    mode: str = typer.Option("replace", "--mode", help="Import mode"),
) -> None:
    """Import a portable data snapshot."""
    result = import_data(archive, mode=mode, dry_run=dry_run)
    if dry_run:
        typer.echo(f"Archive is valid: {result.archive_path}")
        typer.echo("Entries:")
        for entry in result.entries:
            typer.echo(f"  - {entry}")
        return

    typer.echo(f"Imported data into {result.data_dir}")
    typer.echo(f"Backup created at {result.backup_path}")


sync_app = typer.Typer(help="Snapshot sync helpers.")


@sync_app.command("push")
def sync_push_cmd(
    target: Path = typer.Option(..., "--target", "-t", help="Sync folder"),
) -> None:
    """Push a snapshot to a sync folder."""
    result = sync_push(target)
    typer.echo(f"Pushed snapshot to {result.output_path}")


@sync_app.command("pull")
def sync_pull_cmd(
    target: Path = typer.Option(..., "--target", "-t", help="Sync folder"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without writing"),
) -> None:
    """Pull the newest snapshot from a sync folder."""
    result = sync_pull(target, dry_run=dry_run)
    if dry_run:
        typer.echo(f"Newest archive is valid: {result.archive_path}")
        return
    typer.echo(f"Pulled snapshot into {result.data_dir}")
    typer.echo(f"Backup created at {result.backup_path}")


data_app.add_typer(sync_app, name="sync")
