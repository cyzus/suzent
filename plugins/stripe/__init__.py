"""Stripe, through its hosted MCP server and Stripe's own sign-in.

On Stripe's consent page the user picks the account (a sandbox or live
mode) and what the agent may do there. Some of its tools (``send_money``,
``get_balance_summary``) have generic names, so they are prefixed.
"""

from suzent.plugins import Integration, PluginContext


def _toolset(client):
    from pydantic_ai.mcp import MCPToolset

    return MCPToolset(client, id="stripe").prefixed("stripe")


def register(ctx: PluginContext) -> None:
    ctx.register_integration(
        Integration(
            id="stripe",
            name="Stripe",
            url="https://mcp.stripe.com",
            auth="oauth",
            build=_toolset,
        )
    )
