"""Cloudflare, through its hosted API server and Cloudflare's own sign-in.

The server exposes the whole Cloudflare API as a few code-mode tools: the
agent searches the API, then runs a short script against it in Cloudflare's
sandbox. Its tools have generic names (``search``, ``execute``), so they are
prefixed.
"""

from suzent.plugins import Integration, PluginContext


def _toolset(client):
    from pydantic_ai.mcp import MCPToolset

    return MCPToolset(client, id="cloudflare").prefixed("cloudflare")


def register(ctx: PluginContext) -> None:
    ctx.register_integration(
        Integration(
            id="cloudflare",
            name="Cloudflare",
            url="https://mcp.cloudflare.com/mcp",
            auth="oauth",
            build=_toolset,
        )
    )
