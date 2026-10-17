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
from suzent.plugins.context import PluginContext
from suzent.plugins.manifest import (
    MANIFEST_FILENAME,
    PLUGIN_API_VERSION,
    PluginManifest,
)
from suzent.tools.base import Tool

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "suzent.plugins"

type PluginStatus = Literal["disabled", "loaded", "error"]


@dataclass
class PluginRecord:
    manifest: PluginManifest
    source: Literal["directory", "package"]
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.manifest.display_name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "source": self.source,
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
        entry_point_group: str | None = ENTRY_POINT_GROUP,
    ) -> None:
        self.plugin_dirs = plugin_dirs
        self.state_file = state_file
        self.entry_point_group = entry_point_group
        self._records: dict[str, PluginRecord] = {}
        self._loaded = False
        # Re-entrant: a plugin's register() may import modules that ask the
        # manager for its tools while loading is still under way.
        self._lock = threading.RLock()

    # -- enablement --------------------------------------------------------

    def enabled_ids(self) -> set[str]:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return set()
        except (OSError, ValueError) as exc:
            logger.warning(f"Ignoring unreadable plugin state {self.state_file}: {exc}")
            return set()
        enabled = data.get("enabled", []) if isinstance(data, dict) else []
        return {str(plugin_id) for plugin_id in enabled}

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        """Persist the choice; it takes effect the next time Suzent starts."""
        ids = self.enabled_ids()
        if enabled:
            ids.add(plugin_id)
        else:
            ids.discard(plugin_id)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps({"enabled": sorted(ids)}, indent=2) + "\n", encoding="utf-8"
        )

    # -- discovery ---------------------------------------------------------

    def discover(self) -> dict[str, PluginRecord]:
        """Every plugin on disk or installed as a package, without running any of them.

        Packages come first and plugin directories after, in configured order,
        so a plugin checked out for development replaces the installed one.
        """
        records: dict[str, PluginRecord] = {}
        for record in [*self._discover_packages(), *self._discover_directories()]:
            previous = records.get(record.id)
            if previous is not None:
                logger.info(
                    f"Plugin '{record.id}' at {record.path or record.source} "
                    f"overrides {previous.path or previous.source}"
                )
            records[record.id] = record
        enabled = self.enabled_ids()
        for record in records.values():
            record.enabled = record.id in enabled
        return records

    def _discover_directories(self) -> list[PluginRecord]:
        records: list[PluginRecord] = []
        for root in self.plugin_dirs:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                manifest_path = child / MANIFEST_FILENAME
                if not manifest_path.is_file():
                    continue
                try:
                    manifest = PluginManifest.from_file(manifest_path)
                except (OSError, ValueError, ValidationError) as exc:
                    records.append(_broken_record(child.name, "directory", child, exc))
                    continue
                records.append(
                    _checked_record(PluginRecord(manifest, "directory", child))
                )
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

    def _load_one(self, record: PluginRecord) -> None:
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
    module_name = f"suzent_plugin_{record.id.replace('-', '_')}"
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
    source: Literal["directory", "package"],
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
            PLUGINS_DIR,
            USER_CONFIG_DIR,
            get_external_plugin_dirs,
        )

        _manager = PluginManager(
            [PLUGINS_DIR, *get_external_plugin_dirs()],
            USER_CONFIG_DIR / "plugins.json",
        )
    return _manager
