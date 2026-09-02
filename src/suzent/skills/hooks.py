import hashlib
import json
import re
from typing import Any, Iterable, Optional

# Emitted with the catalog and matched on the next turn to decide whether the
# model has already been told. A short opaque token rather than the rendered
# lines: matching those meant any edit to a description — or a switch between
# sandbox and host paths — silently re-sent the whole catalog as if it were new,
# while a cosmetic difference in one line re-sent that line forever.
CATALOG_MARKER_PREFIX = "skills-catalog rev="

# Single-sourced so the emitted text and the pattern that recognises it cannot
# drift apart.
CATALOG_HEADER = (
    "You have a SkillTool that loads specialized knowledge. "
    "Use it IMMEDIATELY when the user's task matches a skill."
)

# Anchored on the header, not on the marker alone. A bare marker pattern matches
# marker-shaped text anywhere in the prompt — a repository reminder, a goal, a
# message someone pasted — and since the newest match wins, that text could
# decide whether the catalog is advertised. Requiring our own header immediately
# before it scopes the match to something this hook actually wrote.
_MARKER_RE = re.compile(
    rf"{re.escape(CATALOG_HEADER)}\s*\[{re.escape(CATALOG_MARKER_PREFIX)}"
    rf"([0-9a-f]{{12}})\]"
)


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


def _neutralize_marker_shapes(text: str) -> str:
    """Stop catalog content from imitating the catalog's own header or marker.

    Descriptions, names and locations come from skill metadata, and they are
    rendered *after* the real marker. Text there that reproduced the header
    followed by a marker would be picked up as the advertised revision, never
    match the true one, and re-inject the catalog on every single turn — the
    runaway repetition this whole change exists to stop.

    A zero-width word joiner is enough: the rendered text reads identically and
    no longer matches the pattern. Content is preserved rather than dropped,
    since this is a rendering concern and not a security boundary.
    """
    if not text:
        return text
    return text.replace(CATALOG_MARKER_PREFIX, "skills-catalog\u2060 rev=").replace(
        CATALOG_HEADER, CATALOG_HEADER.replace(" ", "\u2060 ", 1)
    )


def catalog_revision(lines: Iterable[str]) -> str:
    """Fingerprint the catalog exactly as it would be emitted.

    Hashes the rendered lines rather than a chosen subset of their inputs. An
    earlier version covered ids, descriptions and the sandbox flag, and so
    missed a skill whose path changed on its own: same id, same description, a
    different ``Location`` the model was never told about. Fingerprinting the
    output cannot fall behind the rendering that way.

    Sorted, so loader ordering cannot cause a spurious re-injection.
    """
    payload = json.dumps(sorted(lines), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def latest_advertised_revision(history_text: str) -> Optional[str]:
    """The revision from the most recent marker, or None if never advertised.

    Only the last marker counts. Matching *any* of them meant a catalog that
    changed and then changed back stayed silent: history still held the old
    marker, while what the model had most recently been told was the
    intervening catalog.

    Catalog content cannot imitate the marker — see
    ``_neutralize_marker_shapes`` — so the reachable case is closed. A foreign
    reminder fragment reproducing this exact header verbatim would still be read
    as the latest advertisement; that direction fails toward re-advertising
    rather than toward silence, so the model's catalog stays correct and the
    cost is a repeated reminder.
    """
    found = _MARKER_RE.findall(history_text or "")
    return found[-1] if found else None


async def skills_reminder_hook(chat_id: str, deps: Any) -> Optional[str]:
    """Advertise the enabled skills, once per distinct catalog.

    Deduplication is by a revision marker carried in the reminder itself rather
    than by looking for the rendered lines in history. That matters in both
    directions: the catalog is re-advertised when what it would say changes, and
    it is not re-advertised merely because the lines were re-rendered.

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

    lines = []
    for skill in skill_mgr.loader.list_skills():
        if not skill_mgr.is_skill_enabled(skill.id):
            continue
        name = skill.metadata.name
        if sandbox_enabled:
            from suzent.tools.filesystem.path_resolver import PathResolver

            location = skill.virtual_path or PathResolver.get_skill_virtual_path(name)
        else:
            location = str(skill.path.resolve())
        lines.append(
            _neutralize_marker_shapes(
                f"- {skill.id}: {skill.metadata.description} "
                f"(Name: {name}; Location: {location})"
            )
        )

    if not lines:
        return None

    revision = catalog_revision(lines)
    if latest_advertised_revision(_get_history_text(deps)) == revision:
        return None

    return f"{CATALOG_HEADER}\n[{CATALOG_MARKER_PREFIX}{revision}]\n\n" + "\n".join(
        lines
    )
