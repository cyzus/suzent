"""Linear, through its hosted MCP server and Linear's own sign-in."""

from suzent.plugins import Integration, PluginContext


def _toolset(client):
    from pydantic_ai_harness.linear import Linear

    return Linear(client=client).get_toolset()


def register(ctx: PluginContext) -> None:
    ctx.register_integration(
        Integration(
            id="linear",
            name="Linear",
            url="https://mcp.linear.app/mcp",
            auth="oauth",
            build=_toolset,
        )
    )
