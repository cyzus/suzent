"""
CLI subcommands for the chat store.

Usage:
    suzent chats show <chat_id>
    suzent chats verify
    suzent chats rebuild-index
"""

import json

import typer

chats_app = typer.Typer(help="Inspect and repair how chats are stored.")


@chats_app.command("show")
def show(chat_id: str = typer.Argument(..., help="The chat to print")):
    """Print a chat as its JSONL log records it."""
    from suzent.database import get_database
    from suzent.database.chat_log import ChatLogError

    db = get_database()
    try:
        chat, seq = db.chat_log.fold(chat_id)
    except ChatLogError as exc:
        typer.echo(f"The log of {chat_id} cannot be read: {exc}", err=True)
        raise typer.Exit(code=1)
    if chat is None:
        typer.echo(f"No chat {chat_id} in {db.chat_log.root}.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"{chat['title']}  ({len(chat['messages'])} messages, {seq} events)")
    for message in chat["messages"]:
        content = message.get("content") if isinstance(message, dict) else message
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        role = message.get("role", "?") if isinstance(message, dict) else "?"
        typer.echo(f"\n[{role}]\n{content}")


@chats_app.command("read")
def read(
    chat_id: str = typer.Argument(..., help="The chat to read"),
    offset: int = typer.Option(0, min=0, help="Offset in visible messages"),
    limit: int = typer.Option(20, min=1, max=100, help="Messages per page"),
) -> None:
    """Read a sanitized conversation page without assistant reasoning traces."""
    from suzent.database import get_database

    session = get_database().read_chat_session(chat_id, offset=offset, page_size=limit)
    if session is None:
        typer.echo("Referenced chat not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(session, ensure_ascii=False))


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
