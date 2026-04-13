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
    assert "${MOUNT_SKILLS}/notebook/ingest.md" in text


def test_memory_context_sandbox_mode_keeps_virtual_paths():
    text = format_core_memory_section(_sample_blocks(), sandbox_enabled=True)

    assert "/mnt/notebook" in text
    assert "/shared/memory/MEMORY.md" in text
    assert "/mnt/skills/notebook/ingest.md" in text


def test_skills_xml_host_mode_uses_host_locations():
    manager = SkillManager(skills_dir=PROJECT_DIR / "skills")
    manager.enabled_skills = {"notebook"}

    xml = manager.get_skills_xml(sandbox_enabled=False)

    assert "/mnt/skills/notebook/SKILL.md" not in xml
    assert "<location>" in xml
    assert "SKILL.md" in xml


def test_skill_content_host_mode_rewrites_virtual_paths():
    manager = SkillManager(skills_dir=PROJECT_DIR / "skills")

    content = manager.get_skill_content("notebook", sandbox_enabled=False)

    assert content is not None
    assert "/mnt/notebook" not in content
    assert "${MOUNT_NOTEBOOK}" in content


def test_prompt_assembly_host_mode_has_no_virtual_notebook_paths():
    memory_context = format_core_memory_section(_sample_blocks(), sandbox_enabled=False)
    skills_context = "<available_skills><skill><location>${MOUNT_SKILLS}/notebook/SKILL.md</location></skill></available_skills>"

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

    assert "Do NOT use virtual `/mnt/...` paths." in prompt
    assert "/mnt/notebook" not in prompt
