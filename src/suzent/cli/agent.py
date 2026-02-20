"""
CLI subcommands for interacting with the Suzent agent.

Usage:
    suzent agent chat "message"
    suzent agent status
"""

import typer

from suzent.cli._http import _http_get

agent_app = typer.Typer(help="Interact with the Suzent agent")


@agent_app.command("chat")
def agent_chat(
    message: str = typer.Argument(help="Message to send to the agent"),
):
    """Send a message to the agent and print the response."""
    typer.echo(f"💬 Sending: {message}\n")
    from suzent.cli.stream_parser import (
        StreamParser,
        TextChunk,
        ToolCall,
        ToolOutput,
        ErrorEvent,
        FinalAnswer,
    )

    # Use streaming for better UX
    try:
        from suzent.cli._http import _http_post_stream

        parser = StreamParser()
        stream = _http_post_stream("/chat", data={"message": message, "stream": True})

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
                typer.echo(f"{event.output[:200]}...", err=True)  # Truncate long output

            elif isinstance(event, ErrorEvent):
                typer.secho(
                    f"\n❌ Error: {event.message}", fg=typer.colors.RED, err=True
                )

            elif isinstance(event, FinalAnswer):
                # Always print the final answer clearly
                typer.echo("")
                typer.secho(f"🤖 {event.content}", fg=typer.colors.CYAN, bold=True)

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
