"""The API a plugin's ``register(ctx)`` receives."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from suzent.logger import get_logger
from suzent.plugins.integrations import Integration
from suzent.plugins.manifest import PluginManifest
from suzent.tools.base import Tool


@dataclass
class PendingCommand:
    handler: Callable[..., Any]
    aliases: list[str]
    options: dict[str, Any] = field(default_factory=dict)


class PluginContext:
    """Collects what one plugin registers.

    Nothing reaches the live registries until ``register()`` returns, so a
    plugin that raises halfway through leaves no partial tools or commands
    behind.
    """

    def __init__(self, manifest: PluginManifest, path: Path | None) -> None:
        self.manifest = manifest
        self.path = path
        self.logger = get_logger(f"suzent.plugins.{manifest.id}")
        self.tool_classes: list[type[Tool]] = []
        self.skill_dirs: list[Path] = []
        self.commands: list[PendingCommand] = []
        self.integrations: list[Integration] = []

    @property
    def id(self) -> str:
        return self.manifest.id

    def register_tool(self, tool_cls: type[Tool]) -> None:
        """Add a ``suzent.tools.Tool`` subclass to the agent's tool registry."""
        if not (isinstance(tool_cls, type) and issubclass(tool_cls, Tool)):
            raise TypeError(f"{tool_cls!r} is not a suzent Tool subclass")
        if not tool_cls.name or not tool_cls.tool_name:
            raise ValueError(f"{tool_cls.__name__} must set name and tool_name")
        self.tool_classes.append(tool_cls)

    def register_skills(self, path: str | Path) -> None:
        """Add a directory of skill folders (each holding a SKILL.md).

        A relative path is resolved against the plugin's own directory.
        """
        skills_dir = Path(path)
        if not skills_dir.is_absolute():
            if self.path is None:
                raise ValueError("relative skill paths need a plugin directory")
            skills_dir = self.path / skills_dir
        if not skills_dir.is_dir():
            raise FileNotFoundError(f"skills directory not found: {skills_dir}")
        self.skill_dirs.append(skills_dir.resolve())

    def register_integration(self, integration: Integration) -> None:
        """Connect the agent to a hosted service once the user signs in.

        The plugins page shows the sign-in; the agent gets the toolset that
        ``integration.build`` returns from the next message after it.
        """
        if not isinstance(integration, Integration):
            raise TypeError(f"{integration!r} is not an Integration")
        if any(i.id == integration.id for i in self.integrations):
            raise ValueError(f"integration '{integration.id}' registered twice")
        if not integration.url.startswith("https://"):
            raise ValueError("integration url must be https://")
        self.integrations.append(integration)

    def register_command(
        self, aliases: list[str], **options: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator with the signature of ``suzent.core.commands.base.register_command``."""
        if not aliases or not all(alias.startswith("/") for alias in aliases):
            raise ValueError("command aliases must start with '/'")

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.commands.append(PendingCommand(handler, list(aliases), options))
            return handler

        return decorator
