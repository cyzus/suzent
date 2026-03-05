"""CLI UI rendering utilities for terminal output."""

import typer
from typing import Any, Dict


def render_box(
    title: str,
    content_lines: list[str],
    color: str = typer.colors.YELLOW,
    width: int = 60,
):
    """Render a pretty box in the terminal."""
    border = color
    top_border = f"┌{'─' * (width - 2)}┐"
    bottom_border = f"└{'─' * (width - 2)}┘"

    typer.secho(top_border, fg=border)
    typer.secho(f"│ {title:<{width - 4}} │", fg=border, bold=True)
    typer.secho(f"├{'─' * (width - 2)}┤", fg=border)

    for line in content_lines:
        # Wrap or truncate if needed? For now just padding
        packed_line = line[: width - 4]
        typer.secho(f"│ {packed_line:<{width - 4}} │", fg=border)

    typer.secho(bottom_border, fg=border)


def render_approval_request(tool_name: str, request_id: str, args: Dict[str, Any]):
    """Render a tool approval request box in the terminal."""
    from suzent.core.stream_parser import ApprovalRequest

    typer.echo("")

    event = ApprovalRequest(request_id=request_id, tool_name=tool_name, args=args)
    alert_body = event.format_alert_text(markdown=False)

    content = [
        f"ID: {request_id}",
        "─" * 56,
        *alert_body.splitlines(),
    ]

    render_box(
        title="⚠️  APPROVAL REQUIRED",
        content_lines=content,
        color=typer.colors.YELLOW,
        width=62,
    )

    typer.secho(
        f"  Run: suzent agent approve {request_id}",
        fg=typer.colors.GREEN,
        bold=True,
    )
    typer.echo("")
