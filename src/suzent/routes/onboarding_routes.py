"""Onboarding checks. Recommendations never invoke a model."""

import asyncio

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


async def role_recommendations(request: Request) -> JSONResponse:
    try:
        selection = ModelSelection.model_validate(await request.json())
        roles = recommend_roles(
            get_model_registry(),
            get_enabled_models_from_db(),
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
    except Exception:  # noqa: BLE001 -- redact provider errors, including credential URLs
        # Provider exception strings may contain credential-bearing URLs.
        return JSONResponse({"success": False}, status_code=502)


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
