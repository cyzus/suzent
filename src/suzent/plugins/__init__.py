"""Plugins: Python packages that add tools, slash commands and skills to Suzent.

A plugin is a directory holding ``plugin.yaml`` and an ``__init__.py`` that
defines ``register(ctx: PluginContext)``, or a pip package exposing that
callable under the ``suzent.plugins`` entry-point group. Plugins are disabled
until the user enables them.
"""

from suzent.plugins.context import PluginContext
from suzent.plugins.integrations import Integration
from suzent.plugins.manager import (
    ENTRY_POINT_GROUP,
    PluginManager,
    PluginRecord,
    get_plugin_manager,
)
from suzent.plugins.manifest import PluginManifest

__all__ = [
    "ENTRY_POINT_GROUP",
    "Integration",
    "PluginContext",
    "PluginManager",
    "PluginManifest",
    "PluginRecord",
    "get_plugin_manager",
]
