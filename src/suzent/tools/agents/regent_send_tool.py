"""A send that only reaches Regent, for background runs that should not message anyone else."""

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.core.focal_agent import FOCAL_CHAT_ID, get_or_create_focal_chat
from suzent.tools.agents.agent_lifecycle_tools import AgentSendTool, _require_chat_id
from suzent.tools.base import ToolResult


class RegentSendTool(AgentSendTool):
    """Tell Regent something it or the user should know, and wake it.

    The target is fixed, so a run equipped with this instead of ``agent_send``
    can reach Regent and no one else. Regent's replies are not routed back to
    the sender, and Regent decides whether to pass anything on to the user.
    """

    name = "RegentSendTool"
    display_name = "Report to Regent"
    tool_name = "regent_send"
    # Equipped by name only (the dream's tool list), never picked or searched.
    group = ""
    deferrable = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        message: Annotated[
            str,
            Field(min_length=1, max_length=20_000, description="Message to deliver."),
        ],
    ) -> ToolResult:
        """Send one message to Regent, which decides whether the user hears it."""
        # A headless install may never have opened Regent, and _deliver only
        # reaches chats that exist.
        get_or_create_focal_chat()
        return await self._deliver(
            _require_chat_id(ctx), FOCAL_CHAT_ID, message.strip(), False
        )
