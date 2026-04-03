from pathlib import Path
from typing import Optional
from suzent.config import PROJECT_DIR
from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver
from .loader import SkillLoader

logger = get_logger(__name__)


class SkillManager:
    _instance = None

    def __init__(self, skills_dir: Optional[Path] = None):
        if skills_dir is None:
            # Default to 'skills' directory in project root
            # Check environment variable first
            import os

            env_path = os.getenv("SKILLS_DIR")
            if env_path:
                skills_dir = Path(env_path)
            else:
                skills_dir = PROJECT_DIR / "skills"

        self.skills_dir = skills_dir
        self.loader = SkillLoader(skills_dir)
        self.persistence_file = PROJECT_DIR / "config" / "skills.json"

        # Initialize enabled state
        self.enabled_skills = set()
        self._load_enabled_state()

        logger.info(f"SkillManager initialized with directory: {skills_dir}")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SkillManager()
        return cls._instance

    def _load_enabled_state(self):
        """Load enabled skills from persistence file."""
        if self.persistence_file.exists():
            try:
                import json

                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.enabled_skills = set(data.get("enabled", []))
            except Exception as e:
                logger.error(f"Failed to load skills state: {e}")
        else:
            # Default to all enabled if no state exists?
            # Or default to disabled? Protocol says "toggle which skills to be enabled".
            # Let's default to disabled (empty set) to match "only equipped when enabled" philosophy,
            # OR default to all enabled for backward compat?
            # User said "it will only be equipped when there are skills enabled".
            # Let's start with EMPTY (disabled) so user explicitly enables them, as implied by "toggle...enabled".
            pass

    def _save_enabled_state(self):
        """Save enabled skills to persistence file."""
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            import json

            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump({"enabled": list(self.enabled_skills)}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save skills state: {e}")

    def is_skill_enabled(self, name: str) -> bool:
        return name in self.enabled_skills

    def enable_skill(self, name: str):
        self.enabled_skills.add(name)
        self._save_enabled_state()

    def disable_skill(self, name: str):
        self.enabled_skills.discard(name)
        self._save_enabled_state()

    def toggle_skill(self, name: str) -> bool:
        """Toggle skill state and return new state (True=Enabled)."""
        if name in self.enabled_skills:
            self.disable_skill(name)
            return False
        else:
            self.enable_skill(name)
            return True

    def reload(self):
        """Reload all skills from disk."""
        self.loader.load_skills()
        # Re-verify enabled skills exist?
        available = {s.metadata.name for s in self.loader.list_skills()}
        self.enabled_skills = self.enabled_skills.intersection(available)
        self._save_enabled_state()

    def get_skill_descriptions(self) -> str:
        """
        Generate skill descriptions for tool/system prompt (Layer 1).
        """
        skills = self.loader.list_skills()
        if not skills:
            return "(no skills available)"

        return "\n".join(
            f"- {skill.metadata.name}: {skill.metadata.description}"
            for skill in skills
            if self.is_skill_enabled(skill.metadata.name)
        )

    def get_skills_xml(self) -> str:
        """
        Generate skills XML for context injection (Layer 1).
        Adheres to agentskills.io standard.
        """
        skills = self.loader.list_skills()
        if not skills:
            return "<available_skills></available_skills>"

        xml_lines = ["<available_skills>"]
        for skill in skills:
            if not self.is_skill_enabled(skill.metadata.name):
                continue
            xml_lines.append("  <skill>")
            xml_lines.append(f"    <name>{skill.metadata.name}</name>")
            xml_lines.append(
                f"    <description>{skill.metadata.description}</description>"
            )

            # Virtual path in sandbox
            virtual_path = PathResolver.get_skill_virtual_path(skill.metadata.name)
            xml_lines.append(f"    <location>{virtual_path}</location>")
            xml_lines.append("  </skill>")
        xml_lines.append("</available_skills>")
        return "\n".join(xml_lines)

    def get_skill_content(self, name: str) -> Optional[str]:
        """
        Get full skill content for injection (Layer 2 + 3).
        """
        skill = self.loader.get_skill(name)
        if not skill:
            return None

        content = f"# Skill: {skill.metadata.name}\n\n{skill.body}"

        # List available resources (Layer 3 hints)
        resources = []
        for folder, label in [
            ("scripts", "Scripts"),
            ("references", "References"),
            ("assets", "Assets"),
        ]:
            folder_path = skill.dir / folder
            if folder_path.exists():
                files = list(folder_path.glob("*"))
                if files:
                    file_list = ", ".join(f.name for f in files)
                    resources.append(f"{label}: {file_list}")

        if resources:
            content += f"\n\n**Available resources in {skill.dir}:**\n"
            content += "\n".join(f"- {r}" for r in resources)

        return content


def get_skill_manager():
    return SkillManager.get_instance()
