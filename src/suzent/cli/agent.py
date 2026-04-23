"""
CLI subcommands for interacting with the Suzent agent.

Usage:
    suzent agent chat "message"
    suzent agent status
"""

import typer
import asyncio
from suzent.client import get_client
from suzent.client.base import ClientError
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

    async def _resolve():
        client = get_client()
        return await client.chat.approve_tool_call(request_id, approved)

    try:
        asyncio.run(_resolve())
        if approved:
            typer.secho(f"✅ Approved tool call {request_id}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"⛔ Denied tool call {request_id}", fg=typer.colors.YELLOW)
    except ClientError as e:
        typer.secho(f"❌ {e}", fg=typer.colors.RED)


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

    async def _get_chat():
        client = get_client()
        return await client.chat.get_chat(chat_id)

    try:
        res = asyncio.run(_get_chat())
        title = res.get("title", "Unknown")
        typer.echo(f"Active Session: {chat_id}")
        typer.echo(f"Title: {title}")
    except ClientError:
        typer.secho(f"Session {chat_id} not found on server.", fg=typer.colors.YELLOW)
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
    message: str = typer.Argument(None, help="Initial message to send (optional)"),
    new: bool = typer.Option(False, "--new", help="Start a new chat session"),
):
    """Start an interactive chat REPL with the agent."""
    from suzent.cli.state import get_current_chat_id, set_current_chat_id
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion

    chat_id = None if new else get_current_chat_id()

    if not chat_id:
        typer.echo("Creating new chat session...", err=True)
        try:
            init_title = (
                message[:30] + "..."
                if message and len(message) > 30
                else (message or "CLI Session")
            )
            title = f"[CLI] {init_title}"

            async def _create_chat():
                client = get_client()
                return await client.chat.create_chat(
                    {"title": title, "messages": [], "config": {}}
                )

            res = asyncio.run(_create_chat())
            chat_id = res.get("id")
            set_current_chat_id(chat_id)
        except Exception as e:
            typer.secho(f"❌ Failed to create chat: {e}", fg=typer.colors.RED, err=True)
            return

    typer.echo(f"💬 Active Session: {chat_id}")
    typer.echo("Type /help for commands. Use 'exit' to quit.\n")

    # Fetch commands for the completer
    cmd_meta = {}
    cmd_words = []
    try:

        async def _get_cmds():
            client = get_client()
            return await client.chat.commands(surface="cli")

        cmds_res = asyncio.run(_get_cmds())
        cmds = cmds_res.get("commands", [])
        for cmd in cmds:
            if "name" in cmd:
                cmd_meta[cmd["name"]] = cmd["description"]
                cmd_words.extend(cmd.get("aliases", []))
    except Exception:
        pass  # ignore if server is unreachable

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if text.startswith("/"):
                # Only offer completions if typing the first word
                if " " not in text:
                    for wrd in cmd_words:
                        if wrd.startswith(text):
                            desc = next(
                                (cmd_meta[k] for k in cmd_meta if wrd in ["/" + k]), ""
                            )
                            yield Completion(
                                wrd, start_position=-len(text), display_meta=desc
                            )

    session = PromptSession(completer=SlashCompleter())

    async def _turn_async(user_msg: str):
        resume_approvals = []
        while True:
            parser = StreamParser()
            payload = {
                "message": user_msg if not resume_approvals else "",
                "chat_id": chat_id,
                "stream": True,
                "config_override": {"surface": "cli"},
            }
            if resume_approvals:
                payload["resume_approvals"] = resume_approvals

            client = get_client()
            chunks = [chunk async for chunk in client.chat.stream_message(payload)]

            pending_approvals = []
            for event in parser.parse(iter(chunks)):
                if isinstance(event, TextChunk):
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
                        f"\n❌ Error: {event.message}",
                        fg=typer.colors.RED,
                        err=True,
                    )

                elif isinstance(event, FinalAnswer):
                    typer.echo("")
                    typer.secho(f"🤖 {event.content}", fg=typer.colors.CYAN, bold=True)
                    return

                elif isinstance(event, ApprovalRequest):
                    render_approval_request(
                        tool_name=event.tool_name,
                        request_id=event.request_id,
                        tool_call_id=event.tool_call_id,
                        args=event.args,
                    )
                    pending_approvals.append(event)

            if pending_approvals:
                resume_approvals = []
                for i, approval in enumerate(pending_approvals, 1):
                    label = (
                        f"[{i}/{len(pending_approvals)}] "
                        if len(pending_approvals) > 1
                        else ""
                    )
                    approved = typer.confirm(
                        f"\n{label}Allow {approval.tool_name}?", default=True
                    )
                    resume_approvals.append(
                        {
                            "request_id": approval.request_id,
                            "tool_call_id": approval.tool_call_id,
                            "approved": approved,
                        }
                    )
                typer.echo("🔄 Resuming stream with your decision...")
                continue
            else:
                break

    def _turn(user_msg: str):
        try:
            asyncio.run(_turn_async(user_msg))
        except Exception as e:
            typer.echo(f"\n❌ Streaming failed: {e}")

    # Process initial message if provided
    if message:
        typer.echo(f"💬 Sending: {message}\n")
        _turn(message)

    # Enter REPL loop
    while True:
        try:
            line = session.prompt("> ")
            if not line.strip():
                continue
            if line.strip().lower() in ["exit", "quit", "/exit"]:
                break

            _turn(line)
        except (KeyboardInterrupt, EOFError):
            break


@agent_app.command("status")
def agent_status():
    """Show the agent/server status."""

    async def _get_status():
        client = get_client()
        config, nodes = await asyncio.gather(client.config.get(), client.nodes.list())
        return config, nodes

    try:
        data, node_data = asyncio.run(_get_status())
        typer.echo("🟢 Suzent server is running")
        typer.echo(f"   Title: {data.get('title', 'N/A')}")
        typer.echo(f"   Model options: {', '.join(data.get('model_options', []))}")
        typer.echo(f"   Tools: {len(data.get('tool_options', []))} available")

        # Also show node status
        nodes = node_data.get("nodes", [])
        connected = sum(1 for n in nodes if n.get("status") == "connected")
        typer.echo(f"   Nodes: {connected} connected")
    except Exception:
        typer.echo("🔴 Suzent server is not running")
