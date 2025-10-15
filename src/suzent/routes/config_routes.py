"""
Configuration-related API routes.

This module handles configuration endpoints that provide
frontend-consumable application settings.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import Config


async def get_config(request: Request) -> JSONResponse:
    """
    Return frontend-consumable configuration derived from Config class.
    
    Returns:
        JSONResponse with application configuration including:
        - title: Application title
        - models: Available model options
        - agents: Available agent types
        - tools: Available tool options
        - defaultTools: Default tools to enable
        - codeTag: Code tag identifier
    """
    data = {
        "title": Config.TITLE,
        "models": Config.MODEL_OPTIONS,
        "agents": Config.AGENT_OPTIONS,
        "tools": Config.TOOL_OPTIONS,
        "defaultTools": Config.DEFAULT_TOOLS,
        "codeTag": Config.CODE_TAG,
    }
    return JSONResponse(data)
