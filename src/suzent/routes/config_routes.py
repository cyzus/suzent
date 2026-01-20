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

    # Determine sandbox settings (DB prefs override CONFIG if present)
    sandbox_enabled = getattr(CONFIG, "sandbox_enabled", False)
    sandbox_volumes = CONFIG.sandbox_volumes or []

    data = {
        "title": CONFIG.title,
        "models": CONFIG.model_options,
        "agents": CONFIG.agent_options,
        "tools": [t for t in CONFIG.tool_options if t != "SkillTool"],
        "defaultTools": [t for t in CONFIG.default_tools if t != "SkillTool"],
        "codeTag": CONFIG.code_tag,
        "userId": CONFIG.user_id,
        "globalSandboxVolumes": sandbox_volumes,
        "sandboxEnabled": sandbox_enabled,
    }

    # Add user preferences if they exist
    if user_prefs:
        data["userPreferences"] = {
            "model": user_prefs.model,
            "agent": user_prefs.agent,
            "tools": user_prefs.tools,
            "memory_enabled": user_prefs.memory_enabled,
            "sandbox_enabled": user_prefs.sandbox_enabled,
            "sandbox_volumes": user_prefs.sandbox_volumes,
        }

    return JSONResponse(data)


async def save_preferences(request: Request) -> JSONResponse:
    """
    Save user preferences to the database.

    Body: {
        "model": str (optional),
        "agent": str (optional),
        "tools": list (optional),
        "memory_enabled": bool (optional),
        "sandbox_enabled": bool (optional),
        "sandbox_volumes": list (optional)
    }

    Returns:
        JSONResponse with success status
    """
    data = await request.json()

    model = data.get("model")
    agent = data.get("agent")
    tools = data.get("tools")
    memory_enabled = data.get("memory_enabled")
    sandbox_enabled = data.get("sandbox_enabled")
    sandbox_volumes = data.get("sandbox_volumes")

    db = get_database()
    success = db.save_user_preferences(
        model=model,
        agent=agent,
        tools=tools,
        memory_enabled=memory_enabled,
        sandbox_enabled=sandbox_enabled,
        sandbox_volumes=sandbox_volumes,
    )

    if success:
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Failed to save preferences"}, status_code=500)
