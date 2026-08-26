"""Configuration package.

Re-exports resolve on first attribute access. Around half the module-level
imports of this package want only a path or a port, and eager re-exports made
them import pydantic, the permissions schema and the config loader to get one
-- the cost every CLI invocation used to pay before printing a line.

New code should import from :mod:`suzent.config.paths` or
:mod:`suzent.config.model` directly; this shim keeps existing call sites working.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.config.model import CONFIG as CONFIG
    from suzent.config.model import ConfigModel as ConfigModel
    from suzent.config.model import get_effective_volumes as get_effective_volumes
    from suzent.config.model import get_tool_options as get_tool_options
    from suzent.config.paths import CACHE_DIR as CACHE_DIR
    from suzent.config.paths import DATA_DIR as DATA_DIR
    from suzent.config.paths import DEFAULT_HOST as DEFAULT_HOST
    from suzent.config.paths import DEFAULT_PORT as DEFAULT_PORT
    from suzent.config.paths import EXTERNAL_SKILLS_DIR as EXTERNAL_SKILLS_DIR
    from suzent.config.paths import MESH_PORT as MESH_PORT
    from suzent.config.paths import OFFICIAL_SKILLS_DIR as OFFICIAL_SKILLS_DIR
    from suzent.config.paths import PROJECT_DIR as PROJECT_DIR
    from suzent.config.paths import RUNTIME_DIR as RUNTIME_DIR
    from suzent.config.paths import SKILLS_ROOT_DIR as SKILLS_ROOT_DIR
    from suzent.config.paths import USER_CONFIG_DIR as USER_CONFIG_DIR
    from suzent.config.paths import USER_SKILLS_DIR as USER_SKILLS_DIR
    from suzent.config.paths import ensure_skills_synced as ensure_skills_synced
    from suzent.config.paths import get_data_dir as get_data_dir
    from suzent.config.paths import (
        get_external_skill_sources as get_external_skill_sources,
    )
    from suzent.config.paths import get_project_root as get_project_root
    from suzent.config.paths import (
        migrate_legacy_user_skills_dir as migrate_legacy_user_skills_dir,
    )
    from suzent.config.paths import (
        rebuild_merged_skills_dir as rebuild_merged_skills_dir,
    )
    from suzent.config.paths import sync_managed_skills_dirs as sync_managed_skills_dirs

_PATHS = (
    "DEFAULT_PORT",
    "MESH_PORT",
    "DEFAULT_HOST",
    "get_project_root",
    "get_data_dir",
    "PROJECT_DIR",
    "DATA_DIR",
    "RUNTIME_DIR",
    "CACHE_DIR",
    "USER_CONFIG_DIR",
    "SKILLS_ROOT_DIR",
    "OFFICIAL_SKILLS_DIR",
    "USER_SKILLS_DIR",
    "EXTERNAL_SKILLS_DIR",
    "get_external_skill_sources",
    "migrate_legacy_user_skills_dir",
    "sync_managed_skills_dirs",
    "rebuild_merged_skills_dir",
    "ensure_skills_synced",
)

_MODEL = ("get_tool_options", "get_effective_volumes", "ConfigModel", "CONFIG")

_EXPORTS = {name: "suzent.config.paths" for name in _PATHS}
_EXPORTS.update({name: "suzent.config.model" for name in _MODEL})

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
