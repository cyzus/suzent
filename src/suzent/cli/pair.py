"""
`suzent pair` — manage social channel pairing requests.

Usage:
  suzent pair list                    List pending pairing requests (shows tokens)
  suzent pair approve <token>         Approve a pairing request by token
  suzent pair deny    <token>         Deny a pairing request by token
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
            table.add_column("Token", style="bold yellow", no_wrap=True)
            table.add_column("Platform", style="cyan", no_wrap=True)
            table.add_column("Name")
            table.add_column("Sender ID", style="dim")
            table.add_column("Intro")

            for p in pairings:
                intro = p.get("intro", "") or ""
                if len(intro) > 60:
                    intro = intro[:57] + "..."
                table.add_row(
                    p.get("token", ""),
                    p.get("platform", ""),
                    p.get("sender_name", ""),
                    p.get("sender_id", ""),
                    intro,
                )

            console.print(table)
        except ClientError as e:
            console.print(f"[red]❌ Error:[/red] {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@pair_app.command("approve")
def pair_approve(token: str = typer.Argument(..., help="Pairing token to approve")):
    """Approve a pending pairing request by token."""

    async def _run():
        try:
            client = get_client()
            await client.social.approve_pairing_by_token(token)
            console.print(f"[green]✅ Approved token:[/green] {token.upper()}")
        except ClientError as e:
            console.print(f"[red]❌ Error:[/red] {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@pair_app.command("deny")
def pair_deny(token: str = typer.Argument(..., help="Pairing token to deny")):
    """Deny a pending pairing request by token."""

    async def _run():
        try:
            client = get_client()
            await client.social.deny_pairing_by_token(token)
            console.print(f"[red]❌ Denied token:[/red] {token.upper()}")
        except ClientError as e:
            console.print(f"[red]❌ Error:[/red] {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())
