"""The API a plugin's ``register(ctx)`` receives."""

from __future__ import annotations

import json
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


# Watchers poll outside services, so they never run more often than this.
MIN_WATCHER_SECONDS = 60


@dataclass
class PluginWatcher:
    """A check Suzent runs every ``every_seconds`` while the plugin is on."""

    name: str
    check: Callable[[], Awaitable[None]]
    every_seconds: float


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


class PluginState:
    """Small JSON values one plugin keeps between checks and restarts.

    For bookkeeping such as which messages a watcher has already reported;
    secrets belong in ``ctx.secrets``.
    """

    def __init__(self, plugin_id: str) -> None:
        self._plugin_id = plugin_id

    def _path(self) -> Path:
        from suzent.config.paths import get_data_dir

        return get_data_dir() / "plugins" / self._plugin_id / "state.json"

    def _load(self) -> dict[str, Any]:
        path = self._path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self._load()
        data[key] = value
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


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
        self.watchers: list[PluginWatcher] = []
        self.secrets = PluginSecrets(manifest.id)
        self.state = PluginState(manifest.id)

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

    def register_watcher(
        self,
        name: str,
        check: Callable[[], Awaitable[None]],
        *,
        every_seconds: float = 300,
    ) -> None:
        """Run ``check`` every ``every_seconds`` (at least a minute) while the plugin is on.

        A watcher looks for something new, such as unread mail, and reports it
        with ``emit_event``. A check that raises is logged and tried again on
        the next round; one still running is not started again.
        """
        if not name or any(w.name == name for w in self.watchers):
            raise ValueError(f"watcher {name!r} is empty or registered twice")
        if every_seconds < MIN_WATCHER_SECONDS:
            raise ValueError(f"watchers run at most every {MIN_WATCHER_SECONDS}s")
        self.watchers.append(PluginWatcher(name, check, float(every_seconds)))

    async def emit_event(
        self,
        *,
        event_type: str,
        summary: str,
        payload: Any = None,
        source_name: str | None = None,
        rule_key: str | None = None,
    ) -> Any:
        """Send an event to the Mailbox, where its rule decides where it goes.

        Events with the same ``rule_key`` (default: ``event_type``) share a
        rule. ``payload`` is shown to the agent as outside data, never as
        instructions. Returns the Mailbox item.
        """
        from suzent.core.mailbox import DEST_USER, InboundEnvelope, route_inbound
        from suzent.core.webhooks import format_webhook_payload

        body = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False, default=str)
        )
        source = source_name or self.manifest.name
        envelope = InboundEnvelope(
            source_kind=self.id,
            source_name=source,
            event_type=event_type,
            signature=f"{self.id}:{rule_key or event_type}",
            summary=" ".join(summary.split())[:240],
            rule_name=f"{self.manifest.name} · {rule_key or event_type}",
            payload=format_webhook_payload((body or "").encode("utf-8"), {}),
            # Anyone can cause a plugin event (anyone can send mail), so an
            # event the router can't place only notifies the user.
            fallback=DEST_USER,
        )
        return await route_inbound(envelope)

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
