"""
`suzent pair` — manage social channel pairing requests.

Usage:
  suzent pair list                       List pending pairing requests
  suzent pair approve <sender_id>        Approve a pairing request
  suzent pair deny    <sender_id>        Deny a pairing request
"""

import typer
from rich.console import Console
from rich.table import Table

from suzent.cli._http import _http_get, _http_post

pair_app = typer.Typer(help="Manage social channel pairing requests.")
console = Console()


@pair_app.command("list")
def pair_list():
    """List pending pairing requests."""
    data = _http_get("/social/pairing")
    pairings = data.get("pairings", [])

    if not pairings:
        console.print("[dim]No pending pairing requests.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Sender ID", style="yellow", no_wrap=True)
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Intro")

    for p in pairings:
        intro = p.get("intro", "") or ""
        if len(intro) > 60:
            intro = intro[:57] + "..."
        table.add_row(
            p.get("platform", ""),
            p.get("sender_id", ""),
            p.get("sender_name", ""),
            p.get("state", ""),
            intro,
        )

    console.print(table)


@pair_app.command("approve")
def pair_approve(sender_id: str = typer.Argument(..., help="Sender ID to approve")):
    """Approve a pending pairing request."""
    _http_post(f"/social/pairing/{sender_id}/approve")
    console.print(f"[green]✅ Approved:[/green] {sender_id}")


@pair_app.command("deny")
def pair_deny(sender_id: str = typer.Argument(..., help="Sender ID to deny")):
    """Deny a pending pairing request."""
    _http_post(f"/social/pairing/{sender_id}/deny")
    console.print(f"[red]❌ Denied:[/red] {sender_id}")
