"""
CLI subcommands for the chat store.

Usage:
    suzent chats verify
"""

import typer

chats_app = typer.Typer(help="Inspect how chats are stored.")


@chats_app.command("verify")
def verify(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="List every chat that differs"
    ),
):
    """Check that every chat's JSONL log replays to the same chat as SQLite."""
    from suzent.database import get_database
    from suzent.database.chat_log import ChatEventLog, default_log_root

    db = get_database()
    chat_log = ChatEventLog(default_log_root(db.db_path))
    report = db.chat_log_differences(chat_log)
    total = len(db.all_chat_ids())

    if not report:
        typer.echo(f"All {total} chats match their logs in {chat_log.root}.")
        return

    typer.echo(f"{len(report)} of {total} chats differ from their logs:")
    shown = report.items() if verbose else list(report.items())[:20]
    for chat_id, fields in shown:
        typer.echo(f"  {chat_id}: {', '.join(fields)}")
    if not verbose and len(report) > 20:
        typer.echo(f"  ... and {len(report) - 20} more (use --verbose)")
    raise typer.Exit(code=1)
