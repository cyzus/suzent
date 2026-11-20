"""Onboarding checks. Recommendations never invoke a model."""

import asyncio
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.model_registry import get_model_registry
from suzent.core.providers.helpers import (
    get_configured_provider_ids,
    get_enabled_models_from_db,
)
from suzent.core.role_recommendations import recommend_roles


class ModelSelection(BaseModel):
    model: str = Field(min_length=1, max_length=512)


class RoleRequest(ModelSelection):
    # The models a connection check actually listed. A provider's catalog can
    # name models a custom endpoint does not serve, so recommendations stay
    # within these when given.
    models: list[str] | None = Field(default=None, max_length=2000)


# Overdue or empty accounts that pydantic-ai has no mapping for, matched in the
# error body: DashScope's 400 `Arrearage`, Volcengine's 403 `AccountOverdueError`.
_BALANCE_HINTS = (
    "arrearage",
    "overdue",
    "insufficient balance",
    "insufficient_balance",
    "余额不足",
    "欠费",
)


type ProbeFailure = Literal["auth", "quota", "busy", "model", "network", "unknown"]


def _probe_failure(error: BaseException) -> ProbeFailure:
    """A coarse, credential-free category the setup screen can explain."""
    from pydantic_ai.exceptions import (
        ModelAuthenticationError,
        ModelConnectionError,
        ModelHTTPError,
        ModelNotFoundError,
        ModelQuotaExceededError,
        ModelRateLimitError,
    )

    if isinstance(error, ModelHTTPError) and any(
        hint in str(error.body).lower() for hint in _BALANCE_HINTS
    ):
        return "quota"
    match error:
        case ModelAuthenticationError():
            return "auth"
        case ModelQuotaExceededError():
            return "quota"
        case ModelRateLimitError():
            return "busy"
        case ModelNotFoundError():
            return "model"
        case ModelConnectionError() | TimeoutError():
            return "network"
        case ModelHTTPError(status_code=401 | 403):
            return "auth"
        case ModelHTTPError(status_code=402):
            return "quota"
        case ModelHTTPError(status_code=429):
            return "busy"
        case ModelHTTPError(status_code=404):
            return "model"
    return "unknown"


async def role_recommendations(request: Request) -> JSONResponse:
    try:
        selection = RoleRequest.model_validate(await request.json())
        enabled = get_enabled_models_from_db()
        if selection.models is not None:
            listed = {*selection.models, selection.model}
            enabled = [m for m in enabled if m in listed]
        roles = recommend_roles(
            get_model_registry(),
            enabled,
            get_configured_provider_ids(),
            selection.model,
        )
        return JSONResponse({"roles": roles})
    except (ValidationError, ValueError):
        return JSONResponse(
            {"error": "Select an enabled chat model first"}, status_code=400
        )


async def verify_onboarding_model(request: Request) -> JSONResponse:
    """Explicit, bounded text-only probe; no tools or paid media generation."""
    try:
        selection = ModelSelection.model_validate(await request.json())
        recommend_roles(
            get_model_registry(),
            get_enabled_models_from_db(),
            get_configured_provider_ids(),
            selection.model,
        )
    except (ValidationError, ValueError):
        return JSONResponse({"success": False}, status_code=400)
    try:
        from pydantic_ai import Agent

        from suzent.core.model_factory import create_pydantic_ai_model

        model = create_pydantic_ai_model(selection.model)
        agent = Agent(model, retries=0, model_settings={"max_tokens": 32})
        await asyncio.wait_for(agent.run("Reply with OK."), timeout=30)
        return JSONResponse({"success": True})
    except Exception as error:  # noqa: BLE001 -- redact provider errors, including credential URLs
        # Provider exception strings may contain credential-bearing URLs, so
        # only a category leaves the server.
        return JSONResponse(
            {"success": False, "reason": _probe_failure(error)}, status_code=502
        )


async def check_onboarding_connection(request: Request) -> JSONResponse:
    """Check model-list access only; never invoke generation or catalog fallbacks."""
    try:
        selection = ModelSelection.model_validate(await request.json())
        recommend_roles(
            get_model_registry(),
            get_enabled_models_from_db(),
            get_configured_provider_ids(),
            selection.model,
        )
    except (ValidationError, ValueError):
        return JSONResponse({"status": "invalid"}, status_code=400)
    try:
        from suzent.core.model_factory import create_pydantic_ai_model
        from openai import AsyncOpenAI
        from anthropic import AsyncAnthropic
        from google.genai import Client

        model = create_pydantic_ai_model(selection.model)
        client = getattr(model, "client", None)

        async def check() -> bool:
            if isinstance(client, Client):
                await client.aio.models.list(config={"page_size": 1})
            elif isinstance(client, (AsyncOpenAI, AsyncAnthropic)):
                await client.models.list()
            else:
                return False
            return True

        supported = await asyncio.wait_for(check(), timeout=15)
        return JSONResponse({"status": "connected" if supported else "unsupported"})
    except Exception:  # noqa: BLE001 -- never expose credential-bearing SDK errors
        return JSONResponse({"status": "unconfirmed"})
