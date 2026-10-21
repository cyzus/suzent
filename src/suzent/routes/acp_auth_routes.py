"""Local settings API for outbound ACP authentication jobs."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from suzent.acp import get_acp_manager
from suzent.routes.acp_pairing_routes import require_local_operator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method_id: str | None = Field(default=None, min_length=1, max_length=256)


async def login(request: Request) -> JSONResponse:
    require_local_operator(request)
    manager = get_acp_manager()
    agent_id = request.path_params["agent_id"]
    try:
        data = LoginRequest.model_validate(await request.json())
        agent = manager.registry.get(agent_id)
        from suzent.config import CONFIG

        cwd = agent.cwd or str(
            Path(CONFIG.sandbox_data_path).resolve() / "projects" / "default"
        )
        Path(cwd).mkdir(parents=True, exist_ok=True)
        return JSONResponse(
            manager.logins.start(agent_id, cwd, data.method_id).model_dump(),
            status_code=202,
            headers={"Cache-Control": "no-store"},
        )
    except KeyError:
        return JSONResponse({"error": "Agent not found"}, status_code=404)
    except ValueError:
        return JSONResponse(
            {"error": "Cannot start login; check installation and try again"},
            status_code=400,
        )


async def states(request: Request) -> JSONResponse:
    require_local_operator(request)
    logins = get_acp_manager().logins
    return JSONResponse(
        {key: logins.state(key).model_dump() for key in logins.states},
        headers={"Cache-Control": "no-store"},
    )


async def cancel(request: Request) -> JSONResponse:
    require_local_operator(request)
    logins = get_acp_manager().logins
    agent_id = request.path_params["agent_id"]
    await logins.cancel(agent_id)
    return JSONResponse(
        logins.state(agent_id).model_dump(), headers={"Cache-Control": "no-store"}
    )


acp_auth_routes = [
    Route("/acp/logins", states, methods=["GET"]),
    Route("/acp/agents/{agent_id}/login", login, methods=["POST"]),
    Route("/acp/agents/{agent_id}/login", cancel, methods=["DELETE"]),
]
