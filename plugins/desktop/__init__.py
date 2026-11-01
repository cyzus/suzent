"""Opt-in desktop computer use via the agent-desktop CLI."""

from suzent.plugins import PluginContext
from suzent.tools.desktop import DesktopTool


def register(ctx: PluginContext) -> None:
    ctx.register_tool(DesktopTool)
    ctx.register_skills("skills")
