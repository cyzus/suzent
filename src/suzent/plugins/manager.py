"""Discovery, enablement and loading of plugins."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import ValidationError

from suzent.logger import get_logger
from suzent.plugins import deps
from suzent.plugins.context import PluginContext
from suzent.plugins.manifest import (
    MANIFEST_FILENAME,
    PLUGIN_API_VERSION,
    PluginManifest,
)
from suzent.tools.base import Tool

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "suzent.plugins"
STATE_VERSION = 1
# Keys of a chat app's section in social.json that are not credentials.
_CHANNEL_SETTING_KEYS = {"enabled", "allowed_users"}

type PluginStatus = Literal["disabled", "enabled", "loaded", "error"]
type PluginSource = Literal["builtin", "directory", "package"]


@dataclass
class PluginRecord:
    manifest: PluginManifest
    source: PluginSource
    path: Path | None = None
    enabled: bool = False
    status: PluginStatus = "disabled"
    error: str | None = None
    tool_classes: list[type[Tool]] = field(default_factory=list)
    command_names: list[str] = field(default_factory=list)
    skill_dirs: list[Path] = field(default_factory=list)
    entry_point: EntryPoint | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def has_code(self) -> bool:
        """False for a plugin that only brings packages, such as ``telegram``."""
        if self.entry_point is not None:
            return True
        return self.path is not None and (self.path / "__init__.py").is_file()

    def names(self) -> set[str]:
        return {self.id, *self.manifest.aliases}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.manifest.display_name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "source": self.source,
            "aliases": self.manifest.aliases,
            "hasCode": self.has_code,
            "path": str(self.path) if self.path else None,
            "enabled": self.enabled,
            "status": self.status,
            "error": self.error,
            "tools": [cls.name for cls in self.tool_classes],
            "commands": self.command_names,
            "skillDirs": [str(path) for path in self.skill_dirs],
        }


class PluginManager:
    """Finds plugins, remembers which ones the user enabled, and loads those.

    Discovery only reads manifests and package metadata; a plugin's code runs
    when it is enabled and ``load()`` is called, once per process.
    """

    def __init__(
        self,
        plugin_dirs: list[Path],
        state_file: Path,
        *,
        builtin_dirs: list[Path] | None = None,
        deps_root: Path | None = None,
        entry_point_group: str | None = ENTRY_POINT_GROUP,
        social_config_file: Path | None = None,
    ) -> None:
        self.builtin_dirs = builtin_dirs or []
        self.social_config_file = social_config_file
        self.plugin_dirs = plugin_dirs
        self.state_file = state_file
        self.deps_root = deps_root
        self.entry_point_group = entry_point_group
        self._records: dict[str, PluginRecord] = {}
        self._loaded = False
        # Re-entrant: a plugin's register() may import modules that ask the
        # manager for its tools while loading is still under way.
        self._lock = threading.RLock()

    # -- enablement --------------------------------------------------------

    def _read_state(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning(f"Ignoring unreadable plugin state {self.state_file}: {exc}")
            return {}
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, dict):
            return {}
        return {str(k): v for k, v in plugins.items() if isinstance(v, dict)}

    def _write_state(self, plugins: dict[str, dict[str, Any]]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": STATE_VERSION, "plugins": plugins}
        self.state_file.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    def set_enabled(
        self, plugin_id: str, enabled: bool, *, requested_as: str | None = None
    ) -> None:
        """Record the user's choice. An explicit off is kept, so a built-in
        plugin that defaults to on stays off across upgrades."""
        plugins = self._read_state()
        entry = plugins.get(plugin_id, {})
        entry["enabled"] = enabled
        requested = [name for name in entry.get("requested_by", []) if enabled]
        if enabled and requested_as and requested_as not in requested:
            requested.append(requested_as)
        entry["requested_by"] = requested
        plugins[plugin_id] = entry
        self._write_state(plugins)
        record = self.discover().get(plugin_id)
        if record is not None and record.manifest.channel:
            self._set_channel_enabled(record.manifest.channel, enabled)

    def _set_channel_enabled(self, channel: str, enabled: bool) -> None:
        """Keep the chat app's own switch in social.json in step with its plugin,
        so Settings > Social never shows an app on whose plugin is removed."""
        config = self._read_social_config()
        section = config.get(channel)
        if not isinstance(section, dict) or section.get("enabled", True) == enabled:
            return
        section["enabled"] = enabled
        assert self.social_config_file is not None
        self.social_config_file.write_text(
            json.dumps(config, indent=4), encoding="utf-8"
        )

    def _read_social_config(self) -> dict[str, Any]:
        if self.social_config_file is None:
            return {}
        try:
            data = json.loads(self.social_config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning(f"Ignoring unreadable {self.social_config_file}: {exc}")
            return {}
        return data if isinstance(data, dict) else {}

    def _is_enabled(
        self,
        record: PluginRecord,
        state: dict[str, dict[str, Any]],
        social: dict[str, Any],
    ) -> bool:
        if record.id in state:
            return bool(state[record.id].get("enabled"))
        # Only plugins shipped with Suzent may switch themselves on.
        if record.source != "builtin":
            return False
        if record.manifest.channel:
            # A chat app the user already set up keeps working after the
            # upgrade that split it into its own plugin.
            return channel_configured(social.get(record.manifest.channel))
        return record.manifest.default_enabled

    # -- discovery ---------------------------------------------------------

    def discover(self) -> dict[str, PluginRecord]:
        """Every plugin on disk or installed as a package, without running any of them.

        Later sources replace earlier ones with the same id: built-in plugins,
        then packages, then plugin directories in configured order, so a
        plugin checked out for development replaces the installed one.
        """
        records: dict[str, PluginRecord] = {}
        found = [
            *self._discover_directories(self.builtin_dirs, "builtin"),
            *self._discover_packages(),
            *self._discover_directories(self.plugin_dirs, "directory"),
        ]
        for record in found:
            previous = records.get(record.id)
            if previous is not None:
                logger.info(
                    f"Plugin '{record.id}' at {record.path or record.source} "
                    f"overrides {previous.path or previous.source}"
                )
            records[record.id] = record
        state = self._read_state()
        social = self._read_social_config()
        for record in records.values():
            record.enabled = self._is_enabled(record, state, social)
            if record.enabled and record.status == "disabled":
                record.status = "enabled"
        return records

    def enabled_ids(self) -> set[str]:
        return {record.id for record in self.discover().values() if record.enabled}

    def resolve(self, name: str) -> PluginRecord | None:
        """The plugin called ``name``, by id or alias."""
        records = self.discover()
        if name in records:
            return records[name]
        return next((r for r in records.values() if name in r.manifest.aliases), None)

    def for_channel(self, channel: str) -> PluginRecord | None:
        """The plugin that provides the chat app ``channel``, if any."""
        return next(
            (r for r in self.discover().values() if r.manifest.channel == channel),
            None,
        )

    def deps_dir(self, record: PluginRecord) -> Path | None:
        if self.deps_root is None or not record.manifest.dependencies:
            return None
        return self.deps_root / record.id

    def missing_packages(self, record: PluginRecord) -> list[str]:
        return deps.missing_packages(
            record.manifest.extras, record.manifest.dependencies, self.deps_dir(record)
        )

    def enabled_extras(self) -> list[str]:
        """Suzent extras the enabled plugins need, for ``uv sync``."""
        extras: dict[str, None] = {}
        for record in self.discover().values():
            if record.enabled:
                extras.update(dict.fromkeys(record.manifest.extras))
        return list(extras)

    def install_dependencies(self, record: PluginRecord, project_dir: Path) -> None:
        """Install what ``record`` needs. Adds packages; never removes any."""
        if record.manifest.extras:
            # All enabled extras, not only this plugin's: uv resolves the set together.
            extras = list(
                dict.fromkeys([*self.enabled_extras(), *record.manifest.extras])
            )
            deps.sync_extras(project_dir, extras)
        target = self.deps_dir(record)
        if target is not None:
            deps.install_requirements(record.manifest.dependencies, target)

    def _discover_directories(
        self, roots: list[Path], source: PluginSource
    ) -> list[PluginRecord]:
        records: list[PluginRecord] = []
        for root in roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                manifest_path = child / MANIFEST_FILENAME
                if not manifest_path.is_file():
                    continue
                try:
                    manifest = PluginManifest.from_file(manifest_path)
                except (OSError, ValueError, ValidationError) as exc:
                    records.append(_broken_record(child.name, source, child, exc))
                    continue
                records.append(_checked_record(PluginRecord(manifest, source, child)))
        return records

    def _discover_packages(self) -> list[PluginRecord]:
        if not self.entry_point_group:
            return []
        records: list[PluginRecord] = []
        for entry_point in entry_points(group=self.entry_point_group):
            dist = entry_point.dist
            try:
                manifest = PluginManifest(
                    id=entry_point.name,
                    name=entry_point.name,
                    version=dist.version if dist else "0.0.0",
                    description=(dist.metadata.get("Summary") or "") if dist else "",
                )
            except ValidationError as exc:
                records.append(_broken_record(entry_point.name, "package", None, exc))
                continue
            records.append(PluginRecord(manifest, "package", entry_point=entry_point))
        return records

    # -- loading -----------------------------------------------------------

    def load(self) -> None:
        """Run ``register()`` for every enabled plugin. Safe to call repeatedly."""
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            self._records = self.discover()
            for record in self._records.values():
                if record.enabled and record.status != "error":
                    self._load_one(record)

    def activate(self, plugin_id: str) -> PluginRecord | None:
        """Load a plugin that was just enabled into the running process.

        Also retries one that failed to load. Tools, commands and skills it
        registers are usable from the next message on.
        """
        with self._lock:
            self.load()
            current = self._records.get(plugin_id)
            if current is not None and current.status == "loaded":
                return current
            record = self.discover().get(plugin_id)
            if record is None:
                return None
            if record.enabled and record.status != "error":
                self._load_one(record)
            self._records[plugin_id] = record
        _refresh_live_registries()
        return record

    def deactivate(self, plugin_id: str) -> None:
        """Take a disabled plugin's tools, commands and skills out of the running process."""
        with self._lock:
            self.load()
            record = self._records.get(plugin_id)
            if record is None:
                return
            self._unload_one(record)
        _refresh_live_registries()

    def _unload_one(self, record: PluginRecord) -> None:
        from suzent.core.commands.base import unregister_plugin_command

        for name in record.command_names:
            unregister_plugin_command(name)
        record.tool_classes, record.command_names, record.skill_dirs = [], [], []
        record.enabled, record.status, record.error = False, "disabled", None
        target = self.deps_dir(record)
        if target is not None and str(target) in sys.path:
            sys.path.remove(str(target))
        # A later activate() runs the plugin's current code, not a cached module.
        sys.modules.pop(_module_name(record), None)

    def _load_one(self, record: PluginRecord) -> None:
        target = self.deps_dir(record)
        if target is not None and target.is_dir() and str(target) not in sys.path:
            sys.path.append(str(target))
        if not record.has_code:
            record.status = "loaded"
            return
        ctx = PluginContext(record.manifest, record.path)
        try:
            register = self._resolve_register(record)
            register(ctx)
        except Exception as exc:
            record.status = "error"
            record.error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"Plugin '{record.id}' failed to load: {record.error}")
            return
        self._commit(record, ctx)
        record.status = "loaded"
        logger.info(
            f"Loaded plugin '{record.id}' {record.manifest.version}: "
            f"{len(record.tool_classes)} tool(s), "
            f"{len(record.command_names)} command(s), "
            f"{len(record.skill_dirs)} skill dir(s)"
        )

    def _resolve_register(self, record: PluginRecord) -> Callable[[PluginContext], Any]:
        if record.entry_point is not None:
            target = record.entry_point.load()
        else:
            target = _import_plugin_directory(record)
        register = target if callable(target) else getattr(target, "register", None)
        if not callable(register):
            raise AttributeError("plugin does not define register(ctx)")
        return register

    def _commit(self, record: PluginRecord, ctx: PluginContext) -> None:
        from suzent.core.commands.base import register_plugin_command

        record.tool_classes = list(ctx.tool_classes)
        record.skill_dirs = list(ctx.skill_dirs)
        for command in ctx.commands:
            if register_plugin_command(
                command.handler, command.aliases, command.options
            ):
                record.command_names.append(command.aliases[0])
            else:
                logger.warning(
                    f"Plugin '{record.id}' command {command.aliases[0]} "
                    "clashes with an existing command and was skipped"
                )

    # -- queries -----------------------------------------------------------

    def records(self) -> list[PluginRecord]:
        self.load()
        return list(self._records.values())

    def tool_classes(self) -> list[type[Tool]]:
        return [cls for record in self.records() for cls in record.tool_classes]

    def skill_dirs(self) -> list[tuple[str, Path]]:
        return [
            (record.id, path) for record in self.records() for path in record.skill_dirs
        ]


def _import_plugin_directory(record: PluginRecord) -> Any:
    assert record.path is not None
    init_file = record.path / "__init__.py"
    if not init_file.is_file():
        raise FileNotFoundError(f"{init_file} not found")
    module_name = _module_name(record)
    spec = importlib.util.spec_from_file_location(
        module_name, init_file, submodule_search_locations=[str(record.path)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {init_file}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so the plugin's relative imports resolve.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def _module_name(record: PluginRecord) -> str:
    return f"suzent_plugin_{record.id.replace('-', '_')}"


def channel_configured(settings: Any) -> bool:
    """True when a chat app's section of social.json is on and has credentials."""
    if not isinstance(settings, dict) or not settings.get("enabled", True):
        return False
    return any(
        value for key, value in settings.items() if key not in _CHANNEL_SETTING_KEYS
    )


def _refresh_live_registries() -> None:
    """Make the tool registry, skills and agent reflect the plugins now loaded.

    Only modules this process already imported are touched, so the CLI never
    pulls in the agent stack just to flip a plugin.
    """
    registry = sys.modules.get("suzent.tools.registry")
    if registry is not None:
        registry.reset_tool_caches()
    skills = sys.modules.get("suzent.skills.manager")
    if skills is not None:
        skills.SkillManager.reset_instance()
    agent_manager = sys.modules.get("suzent.agent_manager")
    if agent_manager is not None:
        agent_manager.invalidate_agent()


def _checked_record(record: PluginRecord) -> PluginRecord:
    if record.manifest.api_version > PLUGIN_API_VERSION:
        record.status = "error"
        record.error = (
            f"needs plugin API {record.manifest.api_version}; "
            f"this Suzent supports {PLUGIN_API_VERSION}"
        )
    return record


def _broken_record(
    name: str,
    source: PluginSource,
    path: Path | None,
    exc: Exception,
) -> PluginRecord:
    manifest = PluginManifest.model_construct(id=name, name=name)
    return PluginRecord(
        manifest, source, path, status="error", error=f"invalid manifest: {exc}"
    )


_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        from suzent.config.paths import (
            BUILTIN_PLUGINS_DIR,
            PLUGINS_DIR,
            PROJECT_DIR,
            USER_CONFIG_DIR,
            get_external_plugin_dirs,
        )

        _manager = PluginManager(
            [PLUGINS_DIR, *get_external_plugin_dirs()],
            USER_CONFIG_DIR / "plugins.json",
            builtin_dirs=[BUILTIN_PLUGINS_DIR],
            deps_root=PLUGINS_DIR / ".deps",
            social_config_file=PROJECT_DIR / "config" / "social.json",
        )
    return _manager
