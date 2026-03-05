"""
CLI subcommands for interacting with the Suzent agent.

Usage:
    suzent agent chat "message"
    suzent agent status
"""

import typer
from suzent.cli._http import _http_get, _http_post, _http_post_stream
from suzent.core.stream_parser import (
    StreamParser,
    TextChunk,
    ToolCall,
    ToolOutput,
    ErrorEvent,
    FinalAnswer,
    ApprovalRequest,
)
from suzent.cli.ui import render_approval_request

agent_app = typer.Typer(help="Interact with the Suzent agent")


def _resolve_approval(request_id: str, approved: bool) -> None:
    """Send an approval resolution to the server and display the result."""
    result = _http_post(
        "/chat/approve", data={"request_id": request_id, "approved": approved}
    )
    if "error" in result:
        typer.secho(f"❌ {result['error']}", fg=typer.colors.RED)
        return

    if approved:
        typer.secho(f"✅ Approved tool call {request_id}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"⛔ Denied tool call {request_id}", fg=typer.colors.YELLOW)


@agent_app.command("approve")
def agent_approve(
    request_id: str = typer.Argument(help="The ID of the tool call to approve"),
):
    """Approve a pending tool call from the CLI."""
    _resolve_approval(request_id, approved=True)


@agent_app.command("deny")
def agent_deny(
    request_id: str = typer.Argument(help="The ID of the tool call to deny"),
):
    """Deny a pending tool call from the CLI."""
    _resolve_approval(request_id, approved=False)


@agent_app.command("current")
def agent_current():
    """Show the currently active CLI chat session."""
    from suzent.cli.state import get_current_chat_id

    chat_id = get_current_chat_id()
    if not chat_id:
        typer.echo("No active CLI chat session.")
        return

    try:
        res = _http_get(f"/chats/{chat_id}")
        if "error" in res:
            typer.secho(
                f"Session {chat_id} not found on server.", fg=typer.colors.YELLOW
            )
        else:
            title = res.get("title", "Unknown")
            typer.echo(f"Active Session: {chat_id}")
            typer.echo(f"Title: {title}")
    except Exception:
        typer.echo(f"Active Session: {chat_id} (Server unreachable)")


@agent_app.command("clear")
def agent_clear():
    """Clear the active CLI chat session (disconnects terminal from thread)."""
    from suzent.cli.state import set_current_chat_id

    set_current_chat_id(None)
    typer.echo("CLI chat session cleared. The next message will start a new session.")


@agent_app.command("chat")
def agent_chat(
    message: str = typer.Argument(help="Message to send to the agent"),
    new: bool = typer.Option(False, "--new", help="Start a new chat session"),
):
    """Send a message to the agent and print the response."""
    from suzent.cli.state import get_current_chat_id, set_current_chat_id

    chat_id = None if new else get_current_chat_id()

    if not chat_id:
        typer.echo("Creating new chat session...", err=True)
        try:
            title = (
                f"[CLI] {message[:30]}..." if len(message) > 30 else f"[CLI] {message}"
            )
            res = _http_post(
                "/chats", data={"title": title, "messages": [], "config": {}}
            )
            if "error" in res:
                typer.secho(
                    f"❌ Failed to create chat: {res['error']}",
                    fg=typer.colors.RED,
                    err=True,
                )
                return
            chat_id = res.get("id")
            set_current_chat_id(chat_id)
        except Exception as e:
            typer.secho(f"❌ Failed to create chat: {e}", fg=typer.colors.RED, err=True)
            return

    typer.echo(f"💬 Session: {chat_id}")
    typer.echo(f"💬 Sending: {message}\n")

    # Use streaming for better UX
    try:
        parser = StreamParser()
        stream = _http_post_stream(
            "/chat", data={"message": message, "chat_id": chat_id, "stream": True}
        )

        for event in parser.parse(stream):
            if isinstance(event, TextChunk):
                # Colorize code blocks if detected
                color = typer.colors.GREEN if event.is_code else None
                typer.secho(event.content, nl=False, fg=color)

            elif isinstance(event, ToolCall):
                typer.echo(f"\n[Tool Call: {event.tool_name}]", err=True)

            elif isinstance(event, ToolOutput):
                typer.secho(
                    f"\n[Tool Output: {event.tool_name}]",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
                typer.echo(f"{event.output[:200]}...", err=True)

            elif isinstance(event, ErrorEvent):
                typer.secho(
                    f"\n❌ Error: {event.message}", fg=typer.colors.RED, err=True
                )

            elif isinstance(event, FinalAnswer):
                typer.echo("")
                typer.secho(f"🤖 {event.content}", fg=typer.colors.CYAN, bold=True)

            elif isinstance(event, ApprovalRequest):
                render_approval_request(
                    tool_name=event.tool_name,
                    request_id=event.request_id,
                    args=event.args,
                )

    except Exception as e:
        typer.echo(f"\n❌ Streaming failed: {e}")


@agent_app.command("status")
def agent_status():
    """Show the agent/server status."""
    try:
        data = _http_get("/config")
        typer.echo("🟢 Suzent server is running")
        typer.echo(f"   Title: {data.get('title', 'N/A')}")
        typer.echo(f"   Model options: {', '.join(data.get('model_options', []))}")
        typer.echo(f"   Tools: {len(data.get('tool_options', []))} available")

        # Also show node status
        node_data = _http_get("/nodes")
        nodes = node_data.get("nodes", [])
        connected = sum(1 for n in nodes if n.get("status") == "connected")
        typer.echo(f"   Nodes: {connected} connected")
    except typer.Exit:
        typer.echo("🔴 Suzent server is not running")
