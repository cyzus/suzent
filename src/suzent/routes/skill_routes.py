"""
API routes for skill management.
"""

from starlette.responses import JSONResponse
from suzent.skills import get_skill_manager
from suzent.skills.manager import get_skill_manager_for_chat
from suzent.tools.filesystem.path_resolver import PathResolver


async def get_skills(request):
    """
    Get list of available skills with metadata.
    """
    chat_id = request.query_params.get("chat_id")
    manager = get_skill_manager_for_chat(chat_id)
    skills = manager.loader.list_skills()

    response_data = [
        {
            "id": skill.id,
            "name": skill.metadata.name,
            "description": skill.metadata.description,
            "body": skill.body,
            "hostPath": str(skill.path),
            "path": skill.virtual_path
            or PathResolver.get_skill_virtual_path(skill.metadata.name),
            "source": skill.source,
            "sourceId": skill.source_id,
            "enabled": manager.is_skill_enabled(skill.id),
        }
        for skill in skills
    ]

    return JSONResponse(response_data)


async def toggle_skill(request):
    """
    Toggle a skill's enabled state.
    """
    skill_name = request.path_params.get("skill_name")
    requested_state = None
    if skill_name is None:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        skill_name = payload.get("id") or payload.get("name")
        requested_state = payload.get("enabled")
    if not isinstance(skill_name, str) or not skill_name:
        return JSONResponse({"error": "Skill id is required"}, status_code=400)

    chat_id = request.query_params.get("chat_id")
    manager = get_skill_manager_for_chat(chat_id)

    # Check if skill exists
    skill = manager.loader.get_skill(skill_name)
    if not skill:
        return JSONResponse({"error": "Skill not found"}, status_code=404)

    if isinstance(requested_state, bool):
        if requested_state:
            manager.enable_skill(skill_name)
        else:
            manager.disable_skill(skill_name)
        new_state = requested_state
    else:
        new_state = manager.toggle_skill(skill_name)
    return JSONResponse(
        {"id": skill.id, "name": skill.metadata.name, "enabled": new_state}
    )


async def reload_skills(request):
    """
    Force reload of all skills from disk.
    """
    manager = get_skill_manager()
    manager.reload()

    # Return updated list
    return await get_skills(request)
