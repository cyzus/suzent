"""The ``plugin.yaml`` manifest."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

MANIFEST_FILENAME = "plugin.yaml"
PLUGIN_API_VERSION = 1


class PluginManifest(BaseModel):
    """What a plugin declares about itself before any of its code runs."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    api_version: int = PLUGIN_API_VERSION

    @property
    def display_name(self) -> str:
        return self.name or self.id

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a mapping")
        return cls.model_validate(data)
