"""
CLI subcommands for AgentSkill management.

Usage:
    suzent skill list
    suzent skill toggle my-skill
    suzent skill reload

Installing and creating skills is intentionally NOT a CLI command — those are
agent-driven flows handled by the bundled `skill-installer` and `skill-creator`
skills. See docs/design/plugin_system_cli.md §5.

Backend routes (see src/suzent/routes/skill_routes.py):
    GET  /skills                  -> [{name, description, path, source, enabled}]
    POST /skills/{name}/toggle    -> {name, enabled}
    POST /skills/reload           -> refreshed skill list
"""

import asyncio

import typer

from suzent.client import get_client
from suzent.client.base import ClientError

skill_app = typer.Typer(help="Manage AgentSkills (list, toggle, reload).")


def _print_skills(skills: list) -> None:
    if not skills:
        typer.echo("No skills found.")
        return

    for skill in sorted(skills, key=lambda s: (s.get("source", ""), s["name"])):
        state = "ON " if skill.get("enabled") else "OFF"
        source = skill.get("source", "?")
        desc = (skill.get("description") or "").replace("\n", " ")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        typer.echo(f"  [{state}]  {skill['name']:<24}  {source:<9}  {desc}")

    enabled = sum(1 for s in skills if s.get("enabled"))
    typer.echo(f"\n  {len(skills)} skill(s), {enabled} enabled")


@skill_app.command("list")
def list_skills():
    """List discovered skills with source bucket and enabled state."""

    async def _run():
        try:
            client = get_client()
            skills = await client.skill.list()
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)
        _print_skills(skills)

    asyncio.run(_run())


@skill_app.command("toggle")
def toggle_skill(name: str = typer.Argument(..., help="Skill name to toggle")):
    """Toggle a skill's enabled state."""

    async def _run():
        try:
            client = get_client()
            result = await client.skill.toggle(name)
            state = "enabled" if result.get("enabled") else "disabled"
            typer.echo(f"Skill '{name}' {state}")
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)

    asyncio.run(_run())


@skill_app.command("reload")
def reload_skills():
    """Ask the backend to rescan the skills directory from disk."""

    async def _run():
        try:
            client = get_client()
            skills = await client.skill.reload()
        except ClientError as e:
            typer.echo(f"❌ {e}")
            raise typer.Exit(code=1)
        typer.echo("Reloaded skills from disk.\n")
        _print_skills(skills)

    asyncio.run(_run())
