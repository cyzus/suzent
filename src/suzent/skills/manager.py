from pathlib import Path
from typing import Optional
from suzent.config import (
    OFFICIAL_SKILLS_DIR,
    USER_CONFIG_DIR,
    USER_SKILLS_DIR,
    get_external_skill_sources,
    sync_managed_skills_dirs,
)
from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver
from .loader import SkillLoader

logger = get_logger(__name__)


class SkillManager:
    _instance = None

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dirs: list[Path]
        if skills_dir is None:
            sync_managed_skills_dirs()
            external_dirs = [target for _, target in get_external_skill_sources()]
            self.skills_dirs = [OFFICIAL_SKILLS_DIR, *external_dirs, USER_SKILLS_DIR]
            virtual_roots = {
                OFFICIAL_SKILLS_DIR: "/mnt/skills/official",
                USER_SKILLS_DIR: "/mnt/skills/user",
            }
            source_roots = {
                OFFICIAL_SKILLS_DIR: "official",
                USER_SKILLS_DIR: "user",
            }
            for external_dir in external_dirs:
                virtual_roots[external_dir] = (
                    f"/mnt/skills/external/{external_dir.name}"
                )
                source_roots[external_dir] = "external"
        else:
            self.skills_dirs = [skills_dir]
            virtual_roots = {}
            source_roots = {}

        self.skills_dir = self.skills_dirs[-1]
        self.loader = SkillLoader(
            self.skills_dirs,
            virtual_roots=virtual_roots,
            source_roots=source_roots,
        )
        self.persistence_file = USER_CONFIG_DIR / "skills.json"

        # Initialize enabled state
        self.enabled_skills = set()
        self._load_enabled_state()

        logger.info(f"SkillManager initialized with directories: {self.skills_dirs}")

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
        if self.skills_dirs and self.skills_dirs[0] == OFFICIAL_SKILLS_DIR:
            sync_managed_skills_dirs()
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

    def get_skills_listing(self, sandbox_enabled: bool = True) -> str:
        """
        Generate a markdown list of available skills for context injection.
        """
        skills = self.loader.list_skills()
        if not skills:
            return "(no skills available)"

        lines = []
        for skill in skills:
            if not self.is_skill_enabled(skill.metadata.name):
                continue
            if sandbox_enabled:
                location = skill.virtual_path or PathResolver.get_skill_virtual_path(
                    skill.metadata.name
                )
            else:
                location = str(skill.path.resolve())

            lines.append(
                f"- {skill.metadata.name}: {skill.metadata.description} (Location: {location})"
            )

        if not lines:
            return "(no enabled skills available)"

        return "\n".join(lines)

    def get_skill_content(
        self, name: str, sandbox_enabled: bool = True
    ) -> Optional[str]:
        """
        Get full skill content for injection (Layer 2 + 3).
        """
        skill = self.loader.get_skill(name)
        if not skill:
            return None

        content = f"# Skill: {skill.metadata.name}\n\n{skill.body}"
        if not sandbox_enabled:
            content = self._adapt_skill_content_for_host(content)

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
            resource_dir = (
                skill.virtual_path.rsplit("/", 1)[0]
                if sandbox_enabled and skill.virtual_path
                else str(skill.dir)
            )
            content += f"\n\n**Available resources in {resource_dir}:**\n"
            content += "\n".join(f"- {r}" for r in resources)

        return content

    @staticmethod
    def _adapt_skill_content_for_host(content: str) -> str:
        """Rewrite sandbox-only path literals to host-friendly env var paths."""
        replacements = [
            ("/mnt/notebook", "${MOUNT_NOTEBOOK}"),
            ("/mnt/skills", "${MOUNT_SKILLS}"),
            ("/shared/memory", "${SHARED_PATH}/memory"),
            ("/shared", "${SHARED_PATH}"),
            ("/workspace", "${PROJECT_PATH}"),
        ]

        adapted = content
        for old, new in replacements:
            adapted = adapted.replace(old, new)
        return adapted


def get_skill_manager():
    return SkillManager.get_instance()
