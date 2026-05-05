import re
from pathlib import Path
from typing import Dict, Optional, List
from suzent.logger import get_logger
from .models import Skill, SkillMetadata

logger = get_logger(__name__)


class SkillLoader:
    def __init__(self, skills_dir: Path | List[Path]):
        self.skills_dirs = [skills_dir] if isinstance(skills_dir, Path) else skills_dir
        self.skills_dir = self.skills_dirs[-1] if self.skills_dirs else Path("skills")
        self.skills: Dict[str, Skill] = {}
        # We load skills immediately upon initialization
        self.load_skills()

    def parse_skill_md(self, path: Path) -> Optional[Skill]:
        """Parse a SKILL.md file into a Skill object."""
        try:
            content = path.read_text(encoding="utf-8")

            # Match YAML frontmatter
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
            if not match:
                logger.warning(
                    f"Invalid SKILL.md format in {path}: Missing frontmatter"
                )
                return None

            frontmatter, body = match.groups()

            # Parse simple YAML (key: value)
            metadata_dict = {}
            for line in frontmatter.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata_dict[key.strip()] = value.strip().strip("\"'")

            if "name" not in metadata_dict or "description" not in metadata_dict:
                logger.warning(
                    f"Invalid SKILL.md in {path}: Missing name or description"
                )
                return None

            metadata = SkillMetadata(
                name=metadata_dict["name"], description=metadata_dict["description"]
            )

            return Skill(
                metadata=metadata, body=body.strip(), path=path, dir=path.parent
            )
        except Exception as e:
            logger.error(f"Error parsing SKILL.md at {path}: {e}")
            return None

    def load_skills(self):
        """Scan skills directories and load all valid SKILL.md files."""
        self.skills.clear()
        for skills_dir in self.skills_dirs:
            if not skills_dir.exists():
                logger.debug(
                    f"Skills directory {skills_dir} does not exist. No skills loaded from it."
                )
                continue

            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue

                skill = self.parse_skill_md(skill_md)
                if skill:
                    self.skills[skill.metadata.name] = skill
                    logger.debug(f"Loaded skill: {skill.metadata.name}")

    def get_skill(self, name: str) -> Optional[Skill]:
        return self.skills.get(name)

    def list_skills(self) -> List[Skill]:
        return list(self.skills.values())
