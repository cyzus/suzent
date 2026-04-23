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
import asyncio
from suzent.client import get_client
from suzent.client.base import ClientError

pair_app = typer.Typer(help="Manage social channel pairing requests.")
console = Console()


@pair_app.command("list")
def pair_list():
    """List pending pairing requests."""

    async def _run():
        try:
            client = get_client()
            data = await client.social.pending_pairings()
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
        except ClientError as e:
            console.print(f"[red]❌ Error:[/red] {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@pair_app.command("approve")
def pair_approve(sender_id: str = typer.Argument(..., help="Sender ID to approve")):
    """Approve a pending pairing request."""

    async def _run():
        try:
            client = get_client()
            await client.social.approve_pairing(sender_id)
            console.print(f"[green]✅ Approved:[/green] {sender_id}")
        except ClientError as e:
            console.print(f"[red]❌ Error:[/red] {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@pair_app.command("deny")
def pair_deny(sender_id: str = typer.Argument(..., help="Sender ID to deny")):
    """Deny a pending pairing request."""

    async def _run():
        try:
            client = get_client()
            await client.social.deny_pairing(sender_id)
            console.print(f"[red]❌ Denied:[/red] {sender_id}")
        except ClientError as e:
            console.print(f"[red]❌ Error:[/red] {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
