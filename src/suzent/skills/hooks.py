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
# Announces the catalog; it does not repeat when to use a skill. That policy is
# standing advice and belongs in SkillTool.session_guidance, which is present on
# every turn — this reminder appears only when the catalog changes, so an
# instruction placed here would vanish after the first advertisement.
CATALOG_HEADER = "Skills available to load with SkillTool:"

# Recognised by position, not by pattern-matching loose text: the marker is a
# line of its own immediately after a line that is exactly the header. A bare
# marker pattern matches marker-shaped text anywhere in the prompt, and since the
# newest match wins, unrelated text could decide whether the catalog is
# advertised. Entries are folded onto single lines (see _one_line) so catalog
# content cannot contribute a line of either shape.
_MARKER_LINE_RE = re.compile(
    rf"^\[{re.escape(CATALOG_MARKER_PREFIX)}([0-9a-f]{{12}})\]$"
)
_NEWLINES_RE = re.compile(r"[\r\n]+")


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


def _one_line(text: str) -> str:
    """Fold a rendered entry onto a single line.

    Skill descriptions may span lines, and the marker is recognised by line
    position — so a multi-line entry could otherwise contribute a line that
    looks like the catalog header followed by a marker. Only newlines are
    touched: ids, names and paths never contain them, and the model has to be
    able to copy those verbatim into SkillTool.
    """
    return _NEWLINES_RE.sub(" ", text) if text else text


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
    """The revision from the most recent catalog block, or None if never sent.

    Only the last one counts. Matching *any* marker meant a catalog that changed
    and then changed back stayed silent: history still held the old marker, while
    what the model had most recently been told was the intervening catalog.

    A block qualifies only when the header is the first line of a reminder
    *fragment* and the marker is the line beneath it. Scanning history for that
    pair is not enough — fragments carry unrestricted multi-line text, including
    ``goal.objective`` from a hook registered after this one, and a lookalike
    pair there would be read as the current revision, never match, and re-inject
    the catalog every turn.

    Block and fragment structure comes from ``iter_reminder_fragments`` rather
    than line heuristics here. Deriving it locally went wrong twice: once by
    keeping only the last wrapper in a run of concatenated turns, which lost the
    catalog marker whenever a plan-only turn followed, and once by missing the
    display-trigger envelope that reminder-only turns prefix inside the wrapper,
    which made scheduled turns re-advertise every time.

    Only blocks this process wrote count. This hook runs before the history
    processor strips unauthenticated blocks, so on the first turn after a
    restart the previous process's catalog is still in history — accepting it
    would suppress the advertisement and then the processor would remove the
    block, leaving the model with neither the old catalog nor a new one.
    Re-advertising once per restart is the intended behaviour.
    """
    from suzent.core.system_reminder import iter_reminder_fragments

    found = None
    for fragments in iter_reminder_fragments(history_text, authenticated_only=True):
        for fragment in fragments:
            lines = [line.strip() for line in fragment.splitlines() if line.strip()]
            if len(lines) < 2 or lines[0] != CATALOG_HEADER:
                continue
            match = _MARKER_LINE_RE.match(lines[1])
            if match:
                found = match.group(1)
    return found


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

    def _render() -> list[str]:
        # In host mode this calls Path.resolve() per skill, which touches the
        # filesystem. Blocking before the first await makes the provider
        # deadline unenforceable — an unreachable network mount would stall not
        # just this hook but every provider sharing the loop.
        rendered: list[str] = []
        for skill in skill_mgr.loader.list_skills():
            if not skill_mgr.is_skill_enabled(skill.id):
                continue
            name = skill.metadata.name
            if sandbox_enabled:
                from suzent.tools.filesystem.path_resolver import PathResolver

                location = skill.virtual_path or PathResolver.get_skill_virtual_path(
                    name
                )
            else:
                location = str(skill.path.resolve())
            rendered.append(
                _one_line(
                    f"- {skill.id}: {skill.metadata.description} "
                    f"(Name: {name}; Location: {location})"
                )
            )
        return rendered

    from suzent.core.system_reminder import run_provider_blocking

    lines = await run_provider_blocking(_render)

    if not lines:
        return None

    revision = catalog_revision(lines)
    if latest_advertised_revision(_get_history_text(deps)) == revision:
        return None

    return f"{CATALOG_HEADER}\n[{CATALOG_MARKER_PREFIX}{revision}]\n\n" + "\n".join(
        lines
    )
