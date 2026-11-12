"""The API a plugin's ``register(ctx)`` receives."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket

from suzent.logger import get_logger
from suzent.plugins.binaries import PluginBinary
from suzent.plugins.integrations import Integration
from suzent.plugins.manifest import PluginManifest
from suzent.tools.base import Tool


@dataclass
class PluginRoute:
    path: str
    endpoint: Callable[[Request], Awaitable[Response]]
    methods: tuple[str, ...]


@dataclass
class PluginWebSocket:
    path: str
    endpoint: Callable[[WebSocket], Awaitable[None]]


def _route_path(path: str) -> str:
    path = path.strip("/")
    if not path or any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError(f"invalid route path {path!r}")
    return path


class PluginSecrets:
    """Secrets one plugin keeps in Suzent's secret store.

    They never reach ``os.environ``, so commands the agent runs cannot read
    them, and each plugin sees only its own keys.
    """

    def __init__(self, plugin_id: str) -> None:
        self._prefix = f"SUZENT_PLUGIN::{plugin_id}::"

    def _key(self, name: str) -> str:
        if not name or "::" in name:
            raise ValueError(f"invalid secret name {name!r}")
        return self._prefix + name

    def get(self, name: str) -> str | None:
        from suzent.core.secrets import get_secret_manager

        return get_secret_manager().get_backend_only(self._key(name))

    def set(self, name: str, value: str) -> None:
        from suzent.core.secrets import get_secret_manager

        get_secret_manager().set_backend_only(self._key(name), value)

    def delete(self, name: str) -> None:
        from suzent.core.secrets import get_secret_manager

        get_secret_manager().delete(self._key(name))


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
        self.routes: list[PluginRoute] = []
        self.websockets: list[PluginWebSocket] = []
        self.secrets = PluginSecrets(manifest.id)

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

    def binary(self, name: str) -> PluginBinary:
        """A handle on a program declared under ``binaries`` in ``plugin.yaml``.

        Tools call ``locate()`` on it; installing is left to the user, from
        the plugins page or ``suzent plugin install``.
        """
        for spec in self.manifest.binaries:
            if spec.name == name:
                return PluginBinary(self.id, spec)
        raise KeyError(f"plugin.yaml declares no binary named {name!r}")

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

    def register_route(
        self,
        path: str,
        endpoint: Callable[[Request], Awaitable[Response]],
        methods: tuple[str, ...] = ("GET",),
    ) -> None:
        """Serve ``endpoint`` at ``/plugins/<id>/api/<path>`` for the settings page.

        The route goes away when the plugin is turned off.
        """
        path = _route_path(path)
        methods = tuple(m.upper() for m in methods)
        for route in self.routes:
            if route.path == path and set(route.methods) & set(methods):
                raise ValueError(f"route {path!r} registered twice")
        self.routes.append(PluginRoute(path, endpoint, methods))

    def register_websocket(
        self, path: str, endpoint: Callable[[WebSocket], Awaitable[None]]
    ) -> None:
        """Serve ``endpoint`` at ``/plugins/<id>/ws/<path>``.

        Only the local app and full-access devices reach it, and only from an
        origin the app uses. The socket goes away when the plugin is turned off.
        """
        path = _route_path(path)
        if any(socket.path == path for socket in self.websockets):
            raise ValueError(f"websocket {path!r} registered twice")
        self.websockets.append(PluginWebSocket(path, endpoint))

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
