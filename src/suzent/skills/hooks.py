import hashlib
import json
from typing import Any, Iterable, Optional

# Emitted with the catalog and matched on the next turn to decide whether the
# model has already been told. A short opaque token rather than the rendered
# lines: matching those meant any edit to a description — or a switch between
# sandbox and host paths — silently re-sent the whole catalog as if it were new,
# while a cosmetic difference in one line re-sent that line forever.
CATALOG_MARKER_PREFIX = "skills-catalog rev="


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


def catalog_revision(entries: Iterable[tuple[str, str]], sandbox_enabled: bool) -> str:
    """Fingerprint of what the catalog would say, not of how it is worded.

    Covers skill ids and descriptions because those are what the model routes
    on, and the sandbox flag because it decides whether locations are virtual or
    host paths. Sorted, so catalog order cannot cause a spurious re-injection.
    """
    payload = json.dumps(
        {"skills": sorted(entries), "sandbox": bool(sandbox_enabled)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


async def skills_reminder_hook(chat_id: str, deps: Any) -> Optional[str]:
    """Advertise the enabled skills, once per distinct catalog.

    Deduplication is by a revision marker carried in the reminder itself rather
    than by looking for the rendered lines in history. That matters in both
    directions: the catalog is re-advertised when it actually changes, and it is
    not re-advertised merely because a description was reworded.

    History is the source of truth on purpose. A durable store of "already told"
    would drift from what the model can still see — context compaction drops old
    turns, and reminder blocks from an earlier process are removed on restart —
    leaving skills the agent was told about long ago silently unavailable. Since
    the marker travels with the message, it disappears exactly when the catalog
    does, and the next turn re-advertises.
    """
    skill_mgr = getattr(deps, "skill_manager", None)
    if not skill_mgr or not skill_mgr.has_enabled_skills():
        return None

    sandbox_enabled = getattr(deps, "sandbox_enabled", True)

    enabled = [
        skill
        for skill in skill_mgr.loader.list_skills()
        if skill_mgr.is_skill_enabled(skill.id)
    ]
    if not enabled:
        return None

    revision = catalog_revision(
        ((skill.id, skill.metadata.description) for skill in enabled), sandbox_enabled
    )
    marker = f"[{CATALOG_MARKER_PREFIX}{revision}]"
    if marker in _get_history_text(deps):
        return None

    lines = []
    for skill in enabled:
        name = skill.metadata.name
        if sandbox_enabled:
            from suzent.tools.filesystem.path_resolver import PathResolver

            location = skill.virtual_path or PathResolver.get_skill_virtual_path(name)
        else:
            location = str(skill.path.resolve())
        lines.append(
            f"- {skill.id}: {skill.metadata.description} "
            f"(Name: {name}; Location: {location})"
        )

    return (
        "You have a SkillTool that loads specialized knowledge. "
        "Use it IMMEDIATELY when the user's task matches a skill.\n"
        f"{marker}\n\n" + "\n".join(lines)
    )
