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
    # Other names `suzent plugin install` accepts, e.g. "telegram" for social.
    aliases: list[str] = Field(default_factory=list)
    # Optional-dependency groups of Suzent itself (pyproject extras) this
    # plugin needs. Only built-in plugins can name them meaningfully.
    extras: list[str] = Field(default_factory=list)
    # pip requirements of a third-party plugin, installed into its own
    # directory so a `uv sync` of Suzent's environment never removes them.
    dependencies: list[str] = Field(default_factory=list)
    # Built-in plugins only: on until the user removes it.
    default_enabled: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.id

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a mapping")
        return cls.model_validate(data)
