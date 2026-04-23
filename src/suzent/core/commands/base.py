"""Unified slash command registry — works across frontend, social, and all other surfaces."""

from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
import asyncio
import io
import contextlib
import shlex

import typer
import click

# Handler signature for legacy commands, mostly replaced by direct Typer definition.
CommandHandler = Callable[["CommandContext", str, list], Awaitable[str | None]]


@dataclass
class CommandMeta:
    name: str  # primary name without slash, e.g. "compact"
    aliases: list[str]  # all registered aliases with slash, e.g. ["/compact"]
    description: str
    usage: str  # e.g. "/compact [focus text]"
    surfaces: list[str] = field(default_factory=lambda: ["all"])
    category: str = "tools"
    options: dict[str, str] = field(default_factory=dict)
    hidden: bool = False
    # "all" | "social" | "frontend" | "cli"


@dataclass
class CommandContext:
    chat_id: str
    user_id: str
    surface: str = "all"
    # Social-specific — None when called from frontend / API
    platform: str | None = None
    sender_id: str | None = None
    channel_manager: Any | None = None


# Global Typer registry for parsing
bot_cli = typer.Typer(add_completion=False, add_help_option=True, no_args_is_help=True)
_META: list[CommandMeta] = []


def register_command(
    aliases: list[str],
    description: str = "",
    usage: str = "",
    surfaces: list[str] | None = None,
    category: str = "tools",
    options: dict[str, str] | None = None,
    hidden: bool = False,
):
    """
    Decorator to register a Typer-compatible command handler.
    The decorated function should immediately return an Awaitable[str | None].
    Example:
        @register_command(["/mycmd"])
        def my_cmd(ctx: typer.Context, arg1: str):
            async def _impl():
                return f"Result: {arg1}"
            return _impl
    """

    def decorator(fn):
        meta = CommandMeta(
            name=aliases[0].lstrip("/"),
            aliases=aliases,
            description=description,
            usage=usage or aliases[0],
            surfaces=surfaces or ["all"],
            category=category,
            options=options or {},
            hidden=hidden,
        )
        _META.append(meta)

        # Determine the primary command name to route
        primary_name = aliases[0].lower()

        # Use Typer to wrap it, so standard parsing works across all aliases
        # However, it's simpler to just register the primary and pass the exact command name to click
        bot_cli.command(
            name=primary_name,
            help=description,
            hidden=False,
        )(fn)

        # Typer/Click doesn't easily let us rename the same function multiple times inside the same app
        # without making dummy wrappers. We will handle aliases manually during dispatch.
        for alias in aliases[1:]:
            bot_cli.command(name=alias.lower(), help=description, hidden=True)(fn)

        return fn

    return decorator


def list_commands(
    surface: str | None = None, include_hidden: bool = False
) -> list[CommandMeta]:
    """Return registered commands, optionally filtered by surface and visibility."""
    cmds = _META if include_hidden else [m for m in _META if not m.hidden]

    if surface is None:
        return list(cmds)

    return [m for m in cmds if "all" in m.surfaces or surface in m.surfaces]


async def dispatch(ctx: CommandContext, message: str) -> str | None:
    """
    Parse and execute a slash command using Typer.
    Returns response text if handled, None if not a command or unrecognised.
    """
    content = message.strip()
    if not content.startswith("/"):
        return None

    try:
        parts = shlex.split(content)
    except ValueError:
        return "Error: Unclosed quotation mark in command."

    cmd_name = parts[0].lower()

    # Check if the command exists and is allowed on this surface
    meta = next((m for m in _META if cmd_name in m.aliases), None)
    if meta is None:
        return None

    if "all" not in meta.surfaces and ctx.surface not in meta.surfaces:
        # If the command is not valid for this surface, let it fall through
        # to the LLM naturally (e.g. typing "/y" on frontend).
        return None

    from typer.main import get_command

    click_app = get_command(bot_cli)

    f = io.StringIO()
    try:
        # Redirect stdout/stderr so Typer's help and error outputs are captured
        with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
            # Parts array must include the command name so the Typer Group can route it
            with click_app.make_context("bot", parts, obj=ctx) as click_ctx:
                result = click_app.invoke(click_ctx)

        if result is not None and (
            asyncio.iscoroutine(result) or asyncio.iscoroutinefunction(result)
        ):
            return await result()

        return f.getvalue() or result
    except click.exceptions.UsageError as e:
        # Show specific usage error
        help_text = click_app.get_command(click.Context(click_app), cmd_name).get_help(
            click.Context(click_app)
        )
        return f"Usage error: {e.format_message()}\n\n{help_text}"
    except click.exceptions.Exit:
        # User requested --help or Typer exited gracefully
        return f.getvalue().strip()
    except Exception as e:
        return f"Command invocation error: {e}"
