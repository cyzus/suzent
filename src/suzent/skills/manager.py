from pathlib import Path
from typing import Optional
from suzent.config import PROJECT_DIR
from suzent.logger import get_logger
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
        logger.info(f"SkillManager initialized with directory: {skills_dir}")
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SkillManager()
        return cls._instance

    def reload(self):
        """Reload all skills from disk."""
        self.loader.load_skills()

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
        )

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
            ("assets", "Assets")
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
