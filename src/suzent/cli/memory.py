"""
CLI subcommands for memory files.

Usage:
    suzent memory lint
    suzent memory cleanup

Both work on the files directly, without the server. `cleanup` only writes drafts
into the vault's `.state/cleanup/<date>/`; nothing live is changed.
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from suzent.memory.markdown_store import MarkdownMemoryStore

memory_app = typer.Typer(help="Check memory files and draft their cleanup.")


def _store() -> "MarkdownMemoryStore":
    from suzent.config import CONFIG
    from suzent.memory.lifecycle import resolve_notebook_dir
    from suzent.memory.markdown_store import MarkdownMemoryStore

    return MarkdownMemoryStore(
        str(Path(CONFIG.sandbox_data_path) / "shared" / "memory"),
        notebook_dir=resolve_notebook_dir(),
    )


def _max_lines() -> int:
    from suzent.config import CONFIG

    return CONFIG.memory_map_max_lines


@memory_app.command("lint")
def lint() -> None:
    """Check MEMORY.md, user.md, persona.md, heartbeat.md and page sizes."""
    from suzent.memory import memory_map

    findings = asyncio.run(memory_map.lint_store(_store(), max_lines=_max_lines()))
    if not findings:
        typer.echo("No findings.")
        return
    for finding in findings:
        typer.echo(finding.render())
    raise typer.Exit(code=1)


@memory_app.command("cleanup")
def cleanup() -> None:
    """Draft the one-time cleanup of memory files for review. Changes nothing live."""
    from suzent.memory.cleanup import write_cleanup_drafts

    result = asyncio.run(write_cleanup_drafts(_store(), max_lines=_max_lines()))
    typer.echo(f"Drafts written to {result.out_dir}")
    for path in result.files:
        typer.echo(f"  {path.name}")
    typer.echo(
        f"{result.moved_lines} line(s) to move, {result.findings} lint finding(s). "
        "Read README.md there before applying anything."
    )
