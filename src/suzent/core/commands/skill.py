"""
/skill command — list skills, or start a turn that uses a chosen skill.

Usage:
  /skill                  — list the enabled skills
  /skill <name> [task]    — have the agent load <name>, then do the task

A turn that names an enabled skill is not answered here: the chat processor
sends it on to the agent with a reminder to load the skill first (see
``skill_invocation_reminder``). This handler only answers what is left — the
bare listing and names it cannot use.
"""

from typing import Any

import typer

from suzent.core.commands.base import register_command, CommandContext

SKILL_ALIASES = ("/skill", "/skills")


def _split_invocation(message: str) -> tuple[str, str] | None:
    """Return (skill name, task) when ``message`` is ``/skill <name> ...``.

    Split on whitespace rather than shlex: the task is free text, and an
    apostrophe in it must not read as an unclosed quote.
    """
    parts = message.strip().split(maxsplit=2)
    if len(parts) < 2 or parts[0].lower() not in SKILL_ALIASES:
        return None
    return parts[1], parts[2] if len(parts) > 2 else ""


def skill_invocation_reminder(message: str, skill_manager: Any) -> str | None:
    """Reminder that makes the agent load the skill a ``/skill`` turn names.

    None when the message is not such a turn, or names a skill that is missing
    or disabled; those fall through to the command, which says why.
    """
    invocation = _split_invocation(message)
    if invocation is None or skill_manager is None:
        return None
    name, task = invocation
    skill = skill_manager.loader.get_skill(name)
    if skill is None or not skill_manager.is_skill_enabled(skill.id):
        return None
    follow_up = (
        "then carry out the rest of their message with it."
        if task
        else "then briefly say what it can do and ask what they want done with it."
    )
    return (
        f"The user invoked the `{skill.metadata.name}` skill with /skill. Before "
        f"anything else, load it with skill_execute (skill_name="
        f'"{skill.metadata.name}"), {follow_up}'
    )


@register_command(
    list(SKILL_ALIASES),
    description="List skills, or use a skill for a task",
    usage="/skill [<name> [task]]",
    surfaces=["cli", "frontend", "social"],
    category="tools",
    options={"<name>": "Load this skill, then do the task that follows"},
)
def handle_skill(
    ctx: typer.Context,
    args: list[str] = typer.Argument(None, help="A skill name, then the task"),
):
    async def _impl():
        from suzent.skills.manager import get_skill_manager_for_chat

        cmd_ctx: CommandContext = ctx.obj
        manager = get_skill_manager_for_chat(cmd_ctx.chat_id)
        enabled = [
            s for s in manager.loader.list_skills() if manager.is_skill_enabled(s.id)
        ]

        if not args:
            if not enabled:
                return "No skills are enabled. Turn some on in the Skills view."
            lines = ["Enabled skills — use one with `/skill <name> <task>`:"]
            lines += [
                f"  `{s.metadata.name}` — {s.metadata.description}" for s in enabled
            ]
            return "\n".join(lines)

        name = args[0]
        skill = manager.loader.get_skill(name)
        if skill is None:
            return f"No skill named `{name}`. Use /skill to list the enabled skills."
        if not manager.is_skill_enabled(skill.id):
            return (
                f"The `{skill.metadata.name}` skill is turned off. "
                "Turn it on in the Skills view first."
            )
        # An enabled skill normally never reaches here; the chat processor sends
        # it to the agent instead. Reaching here means no agent turn follows.
        return f"The `{skill.metadata.name}` skill can only be used in a chat turn."

    return _impl
