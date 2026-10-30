"""
API routes for plugins.

GET  /plugins                 -> [{id, name, enabled, status, missing, restartRequired, ...}]
POST /plugins/{name}/install  -> enable a plugin (by id or alias), install its packages, load it
POST /plugins/{name}/remove   -> disable a plugin and unload it

Both take effect in the running server: tools, commands and skills from the
next message on, chat apps once the social stack has been rebuilt.
"""

import asyncio
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.plugins import PluginRecord, get_plugin_manager
from suzent.plugins.deps import DependencyError

logger = get_logger(__name__)


def _describe(record: PluginRecord) -> dict[str, Any]:
    """The plugin as configured now, with what this process actually loaded."""
    manager = get_plugin_manager()
    live = next((r for r in manager.records() if r.id == record.id), None)
    data = record.to_dict()
    running = live is not None and live.status == "loaded" and live.has_code
    if live is not None and live.status == "error":
        data["status"], data["error"] = "error", live.error
    elif running:
        data.update(status="loaded", tools=[c.name for c in live.tool_classes])
        data["commands"] = live.command_names
    data["missing"] = manager.missing_packages(record) if record.enabled else []
    # Install and remove apply in-process, so this only stays true after an
    # out-of-band change, e.g. plugins.json edited by hand.
    data["restartRequired"] = record.has_code and record.enabled != running
    return data


def _has_packages(record: PluginRecord) -> bool:
    return bool(record.manifest.extras or record.manifest.dependencies)


async def _reload_social(request: Request) -> None:
    from suzent.config import PROJECT_DIR
    from suzent.server import reload_social

    config_path = PROJECT_DIR / "config" / "social.json"
    social_config = {}
    if config_path.exists():
        social_config = json.loads(config_path.read_text(encoding="utf-8"))
    await reload_social(request.app, social_config)


async def list_plugins(request: Request) -> JSONResponse:
    records = get_plugin_manager().discover().values()
    return JSONResponse(
        [_describe(record) for record in sorted(records, key=lambda r: r.id)]
    )


async def install_plugin(request: Request) -> JSONResponse:
    from suzent.config import PROJECT_DIR

    name = request.path_params["name"]
    manager = get_plugin_manager()
    record = manager.resolve(name)
    if record is None:
        return JSONResponse({"error": f"No plugin named '{name}'"}, status_code=404)
    if record.status == "error":
        return JSONResponse({"error": record.error}, status_code=400)
    manager.set_enabled(record.id, True, requested_as=name)
    try:
        await asyncio.to_thread(manager.install_dependencies, record, PROJECT_DIR)
    except DependencyError as exc:
        logger.warning(f"Installing packages for plugin '{record.id}' failed: {exc}")
        return JSONResponse(
            {"error": str(exc), "plugin": _describe(manager.resolve(record.id))},
            status_code=502,
        )
    manager.activate(record.id)
    if _has_packages(record):
        # Chat apps import their SDKs when the social stack starts; rebuilding
        # it lets a channel whose packages just arrived connect without a restart.
        await _reload_social(request)
    return JSONResponse(_describe(manager.resolve(record.id)))


async def remove_plugin(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    manager = get_plugin_manager()
    record = manager.resolve(name)
    if record is None:
        return JSONResponse({"error": f"No plugin named '{name}'"}, status_code=404)
    manager.set_enabled(record.id, False)
    manager.deactivate(record.id)
    if _has_packages(record):
        # Stops the chat apps this plugin provided (see ChannelManager).
        await _reload_social(request)
    return JSONResponse(_describe(manager.resolve(record.id)))
