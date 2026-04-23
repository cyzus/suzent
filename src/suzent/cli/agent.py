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

    typer.echo(f"💬 Active Session: {chat_id}")
    typer.echo("Type /help for commands. Use 'exit' to quit.\n")

    # Fetch commands for the completer
    cmd_words = []
    cmd_meta = {}
    try:
        cmds_res = _http_get("/commands?surface=cli")
        if isinstance(cmds_res, list):
            for cmd in cmds_res:
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

    def _turn(user_msg: str):
        try:
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

                stream = _http_post_stream("/chat", data=payload)
                pending_approvals: list[ApprovalRequest] = []

                for event in parser.parse(stream):
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
                        typer.secho(
                            f"🤖 {event.content}", fg=typer.colors.CYAN, bold=True
                        )
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
