"""
API routes for skill management.
"""

from starlette.responses import JSONResponse
from suzent.skills import get_skill_manager
from suzent.tools.filesystem.path_resolver import PathResolver


async def get_skills(request):
    """
    Get list of available skills with metadata.
    """
    manager = get_skill_manager()
    skills = manager.loader.list_skills()

    response_data = [
        {
            "name": skill.metadata.name,
            "description": skill.metadata.description,
            "path": PathResolver.get_skill_virtual_path(skill.metadata.name),
            "enabled": manager.is_skill_enabled(skill.metadata.name),
        }
        for skill in skills
    ]

    return JSONResponse(response_data)


async def toggle_skill(request):
    """
    Toggle a skill's enabled state.
    """
    skill_name = request.path_params["skill_name"]
    manager = get_skill_manager()

    # Check if skill exists
    skill = manager.loader.get_skill(skill_name)
    if not skill:
        return JSONResponse({"error": "Skill not found"}, status_code=404)

    new_state = manager.toggle_skill(skill_name)
    return JSONResponse({"name": skill_name, "enabled": new_state})


async def reload_skills(request):
    """
    Force reload of all skills from disk.
    """
    manager = get_skill_manager()
    manager.reload()

    # Return updated list
    return await get_skills(request)
