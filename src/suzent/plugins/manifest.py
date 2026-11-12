"""The ``plugin.yaml`` manifest."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from suzent.plugins.binaries import BinarySpec

MANIFEST_FILENAME = "plugin.yaml"
PLUGIN_API_VERSION = 4


class PluginManifest(BaseModel):
    """What a plugin declares about itself before any of its code runs."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    api_version: int = PLUGIN_API_VERSION
    # Other names `suzent plugin install` accepts, e.g. "lark" for feishu.
    aliases: list[str] = Field(default_factory=list)
    # The chat app this plugin provides, as named in config/social.json.
    # Built-in chat-app plugins are on whenever that app is configured.
    channel: str | None = None
    # Optional-dependency groups of Suzent itself (pyproject extras) this
    # plugin needs. Only built-in plugins can name them meaningfully.
    extras: list[str] = Field(default_factory=list)
    # pip requirements of a third-party plugin, installed into its own
    # directory so a `uv sync` of Suzent's environment never removes them.
    dependencies: list[str] = Field(default_factory=list)
    # Built-in plugins only: on until the user removes it.
    default_enabled: bool = False
    # An SVG or PNG file in the plugin's directory, shown on the plugins page.
    icon: str | None = None
    # "service" puts a plugin that connects a hosted service (Notion, GitHub)
    # on the Services page instead of the Plugins page.
    category: Literal["service"] | None = None
    # Programs the plugin runs on the host, installed after the user agrees.
    binaries: list[BinarySpec] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or self.id

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a mapping")
        return cls.model_validate(data)
