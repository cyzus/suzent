"""
Configuration-related API routes.

This module handles configuration endpoints that provide
frontend-consumable application settings.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import CONFIG
from suzent.database import get_database


async def get_config(request: Request) -> JSONResponse:
    """
    Return frontend-consumable configuration derived from Config class,
    merged with user preferences from database.

    Returns:
        JSONResponse with application configuration including:
        - title: Application title
        - models: Available model options
        - agents: Available agent types
        - tools: Available tool options
        - defaultTools: Default tools to enable
        - codeTag: Code tag identifier
        - userPreferences: Saved user preferences (model, agent, tools, memory_enabled)
    """
    db = get_database()
    user_prefs = db.get_user_preferences()

    data = {
        "title": CONFIG.title,
        "models": CONFIG.model_options,
        "agents": CONFIG.agent_options,
        "tools": CONFIG.tool_options,
        "defaultTools": CONFIG.default_tools,
        "codeTag": CONFIG.code_tag,
        "userId": CONFIG.user_id,
        # Include global sandbox configuration
        "globalSandboxVolumes": CONFIG.sandbox_volumes or [],
        "sandboxEnabled": getattr(CONFIG, "sandbox_enabled", False),
    }

    # Add user preferences if they exist
    if user_prefs:
        data["userPreferences"] = {
            "model": user_prefs["model"],
            "agent": user_prefs["agent"],
            "tools": user_prefs["tools"],
            "memory_enabled": user_prefs["memory_enabled"],
        }

    return JSONResponse(data)


async def save_preferences(request: Request) -> JSONResponse:
    """
    Save user preferences to the database.

    Body: {
        "model": str (optional),
        "agent": str (optional),
        "tools": list (optional),
        "memory_enabled": bool (optional)
    }

    Returns:
        JSONResponse with success status
    """
    data = await request.json()

    model = data.get("model")
    agent = data.get("agent")
    tools = data.get("tools")
    memory_enabled = data.get("memory_enabled")

    db = get_database()
    success = db.save_user_preferences(
        model=model, agent=agent, tools=tools, memory_enabled=memory_enabled
    )

    if success:
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Failed to save preferences"}, status_code=500)
