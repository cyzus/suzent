"""
CLI subcommands for the chat store.

Usage:
    suzent chats verify
    suzent chats rebuild-index
"""

import typer

chats_app = typer.Typer(help="Inspect and repair how chats are stored.")


@chats_app.command("verify")
def verify(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="List every chat that differs"
    ),
):
    """Check that every chat's JSONL log replays to the same chat as chats.db."""
    from suzent.database import get_database

    db = get_database()
    report = db.chat_log_differences(db.chat_log)
    total = len(db.all_chat_ids())

    if not report:
        typer.echo(f"All {total} chats match their logs in {db.chat_log.root}.")
        return

    typer.echo(f"{len(report)} of {total} chats differ from their logs:")
    shown = report.items() if verbose else list(report.items())[:20]
    for chat_id, fields in shown:
        typer.echo(f"  {chat_id}: {', '.join(fields)}")
    if not verbose and len(report) > 20:
        typer.echo(f"  ... and {len(report) - 20} more (use --verbose)")
    raise typer.Exit(code=1)


@chats_app.command("rebuild-index")
def rebuild_index():
    """Rewrite every chat in chats.db from its JSONL log. Stop Suzent first."""
    from suzent.database import get_database

    db = get_database()
    imported = db.import_unlogged_chats()
    changed = db.reconcile_chat_logs(rebuild=True)
    typer.echo(
        f"Rebuilt {len(db.all_chat_ids())} chats from {db.chat_log.root}: "
        f"{changed} rewritten, {imported} logs started from chats.db."
    )
