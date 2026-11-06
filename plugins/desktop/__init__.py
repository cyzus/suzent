"""Opt-in desktop computer use via the agent-desktop CLI."""

from suzent.plugins import PluginContext

from . import runner
from .tool import DesktopTool


def register(ctx: PluginContext) -> None:
    runner.use_binary(ctx.binary("agent-desktop"))
    ctx.register_tool(DesktopTool)
    ctx.register_skills("skills")
