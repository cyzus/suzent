from pathlib import Path
from pydantic import BaseModel, ConfigDict


class SkillMetadata(BaseModel):
    """Metadata for a skill, parsed from frontmatter."""

    name: str
    description: str


class Skill(BaseModel):
    """
    Represents a loaded skill.

    Attributes:
        metadata: The skill's metadata (name, description).
        body: The main instruction content of the skill (markdown).
        path: Absolute path to the SKILL.md file.
        dir: Absolute path to the skill directory containing SKILL.md and resources.
        source: Source bucket for the skill (official, user, external, or custom).
        virtual_path: Path to SKILL.md under the /mnt/skills mount.
    """

    metadata: SkillMetadata
    body: str
    path: Path
    dir: Path
    source: str = "custom"
    virtual_path: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
