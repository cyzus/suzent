"""GitHub, through its hosted MCP server.

GitHub does not let apps register themselves for sign-in, so the user pastes a
fine-grained personal access token instead; its permissions bound the agent's.
"""

from suzent.plugins import Integration, PluginContext


def _toolset(token: str):
    from pydantic_ai_harness.github import GitHub

    return GitHub(auth=token).get_toolset()


def register(ctx: PluginContext) -> None:
    ctx.register_integration(
        Integration(
            id="github",
            name="GitHub",
            url="https://api.githubcopilot.com/mcp/",
            auth="token",
            build=_toolset,
            token_help_url="https://github.com/settings/personal-access-tokens/new",
        )
    )
