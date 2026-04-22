from typing import Any, Optional


def _get_history_text(deps: Any) -> str:
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    parts = []
    for msg in getattr(deps, "last_messages", None) or []:
        if not isinstance(msg, ModelRequest):
            continue
        for part in msg.parts:
            if isinstance(part, UserPromptPart):
                content = part.content if isinstance(part.content, str) else ""
                if content:
                    parts.append(content)
    return "\n".join(parts)


async def skills_reminder_hook(chat_id: str, deps: Any) -> Optional[str]:
    """Global system-reminder hook: injects enabled skills not yet seen in message history."""
    skill_mgr = getattr(deps, "skill_manager", None)
    if not skill_mgr or not skill_mgr.enabled_skills:
        return None

    sandbox_enabled = getattr(deps, "sandbox_enabled", True)
    history_text = _get_history_text(deps)

    new_lines = []
    for skill in skill_mgr.loader.list_skills():
        name = skill.metadata.name
        if not skill_mgr.is_skill_enabled(name):
            continue
        if sandbox_enabled:
            from suzent.tools.filesystem.path_resolver import PathResolver

            location = PathResolver.get_skill_virtual_path(name)
        else:
            location = str(skill.path.resolve())
        line = f"- {name}: {skill.metadata.description} (Location: {location})"
        if line not in history_text:
            new_lines.append(line)

    if not new_lines:
        return None

    return (
        "You have a SkillTool that loads specialized knowledge. "
        "Use it IMMEDIATELY when the user's task matches a skill.\n\n"
        + "\n".join(new_lines)
    )
