"""Example Suzent plugin: one tool, one slash command, one skill.

Try it:
    SUZENT_PLUGINS_DIR=examples/plugins suzent plugin enable dice
    SUZENT_PLUGINS_DIR=examples/plugins suzent start
"""

import random

import typer

from suzent.plugins import PluginContext
from suzent.tools.base import Tool, ToolErrorCode, ToolResult


def _roll(count: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(count)]


class RollDiceTool(Tool):
    # No ``group``: the tool is not shown in the tool picker and the agent
    # finds it through ToolSearch. Set ``group`` to list it in the picker.
    name = "RollDiceTool"
    tool_name = "roll_dice"
    description = "Roll dice and return each result and the total."

    def forward(self, count: int = 1, sides: int = 6) -> ToolResult:
        """Roll ``count`` dice with ``sides`` sides each."""
        if not 1 <= count <= 100 or not 2 <= sides <= 1000:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "count must be 1-100 and sides 2-1000"
            )
        rolls = _roll(count, sides)
        return ToolResult.success_result(
            f"Rolled {rolls}, total {sum(rolls)}", metadata={"rolls": rolls}
        )


def register(ctx: PluginContext) -> None:
    ctx.register_tool(RollDiceTool)
    ctx.register_skills("skills")

    @ctx.register_command(
        ["/roll"], description="Roll dice", usage="/roll [count] [sides]"
    )
    def roll_command(count: int = typer.Argument(1), sides: int = typer.Argument(6)):
        async def _impl() -> str:
            rolls = _roll(count, sides)
            return f"🎲 {rolls} (total {sum(rolls)})"

        return _impl
