"""Notion, through its hosted MCP server and Notion's own sign-in."""

from suzent.plugins import Integration, PluginContext


def _toolset(client):
    from pydantic_ai_harness.notion import Notion

    return Notion(client=client).get_toolset()


def register(ctx: PluginContext) -> None:
    ctx.register_integration(
        Integration(
            id="notion",
            name="Notion",
            url="https://mcp.notion.com/mcp",
            auth="oauth",
            build=_toolset,
        )
    )
