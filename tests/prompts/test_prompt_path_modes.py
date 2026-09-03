from pathlib import Path

from suzent.config import PROJECT_DIR
from suzent.memory.memory_context import format_core_memory_section
from suzent.prompts import build_execution_mode_section
from suzent.skills.manager import SkillManager


def _sample_blocks() -> dict[str, str]:
    return {
        "persona": "You are Suzent.",
        "user": "Test user.",
        "facts": "No facts.",
        "context": "No context.",
    }


def test_memory_context_host_mode_avoids_virtual_paths():
    text = format_core_memory_section(_sample_blocks(), sandbox_enabled=False)

    assert "/mnt/notebook" not in text
    assert "/shared/memory/" not in text
    assert "${SHARED_PATH}/memory/MEMORY.md" in text
    # No notebook mount was supplied, so the section says so rather than
    # pointing at a skill for a resource this session does not have.
    assert "No notebook is configured" in text
    assert "MOUNT_SKILLS" not in text


def test_memory_context_host_mode_points_at_the_skill_when_mounted():
    text = format_core_memory_section(
        _sample_blocks(), sandbox_enabled=False, mount_notebook="/host/vault"
    )

    assert "Load the `notebook` skill" in text
    assert "/mnt/notebook" not in text


def test_memory_context_sandbox_mode_keeps_virtual_paths():
    text = format_core_memory_section(_sample_blocks(), sandbox_enabled=True)

    assert "/mnt/notebook" in text
    assert "/shared/memory/MEMORY.md" in text
    assert "Load the `notebook` skill" in text
    assert "/mnt/skills" not in text
    assert "/workspace/context.md" in text
    assert "/shared/memory/sessions/" not in text


def test_memory_context_host_mode_uses_project_context_path(tmp_path: Path):
    context_path = str(tmp_path / "project" / "context.md").replace("\\", "/")
    text = format_core_memory_section(
        _sample_blocks(),
        sandbox_enabled=False,
        project_context_path=context_path,
    )

    assert context_path in text
    assert "/memory/sessions/" not in text


def test_skills_listing_host_mode_uses_host_locations():
    manager = SkillManager(skills_dir=PROJECT_DIR / "skills")
    manager.enabled_skills = {"notebook"}

    listing = manager.get_skills_listing(sandbox_enabled=False)

    assert "/mnt/skills/notebook/SKILL.md" not in listing
    assert "- notebook:" in listing
    assert "Location:" in listing
    assert "SKILL.md" in listing


def test_skill_content_host_mode_rewrites_virtual_paths():
    manager = SkillManager(skills_dir=PROJECT_DIR / "skills")

    content = manager.get_skill_content("notebook", sandbox_enabled=False)

    assert content is not None
    assert "/mnt/notebook" not in content
    assert "${MOUNT_NOTEBOOK}" in content


def _manager_with_path_skill(tmp_path: Path) -> SkillManager:
    skill_dir = tmp_path / "path-guide"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: path-guide\n"
        "description: Test path adaptation\n"
        "---\n"
        "Use /persistence in sandbox mode.\n",
        encoding="utf-8",
    )
    return SkillManager(skills_dir=tmp_path)


def test_skill_content_host_mode_rewrites_persistence_alias(tmp_path: Path):
    # /persistence is a legacy virtual alias for the per-chat project dir. On the
    # host there is no PERSISTENCE_PATH env var, so it must be rewritten to
    # ${PROJECT_PATH} for any custom skill that references the sandbox alias.
    manager = _manager_with_path_skill(tmp_path)

    content = manager.get_skill_content("path-guide", sandbox_enabled=False)

    assert content is not None
    assert "/persistence" not in content
    assert "PERSISTENCE_PATH" not in content
    assert "${PROJECT_PATH}" in content


def test_skill_content_sandbox_mode_keeps_persistence_alias(tmp_path: Path):
    manager = _manager_with_path_skill(tmp_path)

    content = manager.get_skill_content("path-guide", sandbox_enabled=True)

    assert content is not None
    assert "/persistence" in content


def test_prompt_assembly_host_mode_has_no_virtual_notebook_paths():
    memory_context = format_core_memory_section(_sample_blocks(), sandbox_enabled=False)
    skills_context = "- notebook: Notebook operations (Location: ${MOUNT_SKILLS}/official/notebook/SKILL.md)"

    prompt = "\n\n".join(
        [
            build_execution_mode_section(
                sandbox_enabled=False,
                workspace_root=str(Path(PROJECT_DIR)),
            ),
            memory_context,
            skills_context,
        ]
    )

    # Not "told not to use /mnt" — never shown /mnt at all. Naming a scheme is
    # how a model learns it exists, and the prohibition used to sit in the same
    # prompt as a Directory Mappings block listing /mnt paths as available.
    assert "/mnt" not in prompt
    assert "Do NOT use virtual" not in prompt
