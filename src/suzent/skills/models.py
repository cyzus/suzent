from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

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
    """
    metadata: SkillMetadata
    body: str
    path: Path
    dir: Path
    
    class Config:
        arbitrary_types_allowed = True
