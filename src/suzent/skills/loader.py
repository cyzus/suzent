import re
from pathlib import Path
from typing import Dict, Optional, List
from suzent.logger import get_logger
from .models import Skill, SkillMetadata

logger = get_logger(__name__)


class SkillLoader:
    def __init__(
        self,
        skills_dir: Path | List[Path],
        *,
        virtual_roots: dict[Path, str] | None = None,
        source_roots: dict[Path, str] | None = None,
    ):
        self.skills_dirs = [skills_dir] if isinstance(skills_dir, Path) else skills_dir
        self.skills_dir = self.skills_dirs[-1] if self.skills_dirs else Path("skills")
        self.virtual_roots = {
            root.resolve(): prefix.rstrip("/")
            for root, prefix in (virtual_roots or {}).items()
        }
        self.source_roots = {
            root.resolve(): source for root, source in (source_roots or {}).items()
        }
        self.skills: Dict[str, Skill] = {}
        # We load skills immediately upon initialization
        self.load_skills()

    def parse_skill_md(
        self,
        path: Path,
        *,
        source: str = "custom",
        virtual_path: str | None = None,
    ) -> Optional[Skill]:
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
                metadata=metadata,
                body=body.strip(),
                path=path,
                dir=path.parent,
                source=source,
                virtual_path=virtual_path,
            )
        except Exception as e:
            logger.error(f"Error parsing SKILL.md at {path}: {e}")
            return None

    def _get_virtual_path(self, skills_dir: Path, skill_dir: Path) -> str:
        root = skills_dir.resolve()
        prefix = self.virtual_roots.get(root)
        if prefix is None:
            return f"/mnt/skills/{skill_dir.name}/SKILL.md"
        return f"{prefix}/{skill_dir.name}/SKILL.md"

    def _get_source(self, skills_dir: Path) -> str:
        return self.source_roots.get(skills_dir.resolve(), "custom")

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

                skill = self.parse_skill_md(
                    skill_md,
                    source=self._get_source(skills_dir),
                    virtual_path=self._get_virtual_path(skills_dir, skill_dir),
                )
                if skill:
                    self.skills[skill.metadata.name] = skill
                    logger.debug(f"Loaded skill: {skill.metadata.name}")

    def get_skill(self, name: str) -> Optional[Skill]:
        return self.skills.get(name)

    def list_skills(self) -> List[Skill]:
        return list(self.skills.values())
