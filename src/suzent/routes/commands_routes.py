"""GET /commands — returns the registered slash command list for UI hints."""

from starlette.requests import Request
from starlette.responses import JSONResponse


async def get_commands(request: Request) -> JSONResponse:
    """Return slash command metadata for a given surface (default: all)."""
    surface = request.query_params.get("surface")  # "frontend" | "social" | None
    import suzent.core.commands  # noqa: F401 - import for registration side effects
    from suzent.core.commands.base import list_commands

    commands = list_commands(surface=surface)
    return JSONResponse(
        [
            {
                "name": m.name,
                "aliases": m.aliases,
                "description": m.description,
                "usage": m.usage,
                "surfaces": m.surfaces,
            }
            for m in commands
        ]
    )
