"""
API routes for plugins.

GET  /plugins                 -> [{id, name, enabled, status, missing, restartRequired, ...}]
POST /plugins/{name}/install  -> enable a plugin (by id or alias), install its packages, load it
POST /plugins/{name}/remove   -> disable a plugin and unload it
POST /plugins/{name}/integrations/{id}/connect     -> start a sign-in, or save a token
POST /plugins/{name}/integrations/{id}/disconnect  -> sign out and forget the credential

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
    if live is not None and live.integrations:
        from suzent.plugins.integrations import describe

        data["integrations"] = [describe(live.id, i) for i in live.integrations]
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


def _integration_or_error(request: Request):
    from suzent.plugins import integrations

    manager = get_plugin_manager()
    record = manager.resolve(request.path_params["name"])
    if record is None:
        return None, None, JSONResponse({"error": "No such plugin"}, status_code=404)
    integration = integrations.find(record.id, request.path_params["integration"])
    if integration is None:
        return (
            None,
            None,
            JSONResponse(
                {"error": "Install the plugin to connect it"}, status_code=404
            ),
        )
    return record, integration, None


def _rebuild_agent() -> None:
    from suzent import agent_manager

    agent_manager.invalidate_agent()


async def connect_integration(request: Request) -> JSONResponse:
    """Start the browser sign-in (OAuth), or store a pasted token.

    For OAuth the reply carries ``authorizeUrl`` for the page to open in the
    user's browser; the sign-in then completes in the background and the
    page polls ``GET /plugins`` for ``connected``.
    """
    from suzent.core.mcp_oauth import start_sign_in
    from suzent.core.secrets import get_secret_manager
    from suzent.plugins import integrations

    record, integration, error = _integration_or_error(request)
    if error is not None:
        return error
    integrations.forget_error(record.id, integration)
    if integration.auth == "token":
        try:
            body = await request.json()
        except Exception:
            body = {}
        token = str((body or {}).get("token") or "").strip()
        if not token:
            return JSONResponse({"error": "Paste a token first"}, status_code=400)
        await asyncio.to_thread(
            get_secret_manager().set_backend_only,
            integrations.token_key(record.id, integration),
            token,
        )
        _rebuild_agent()
        return JSONResponse(integrations.describe(record.id, integration))

    sign_in = await start_sign_in(
        integrations.namespace(record.id, integration),
        integration.url,
        scopes=list(integration.scopes) or None,
        on_success=_rebuild_agent,
    )
    if sign_in.state == "failed":
        return JSONResponse(
            {"error": sign_in.error or "Sign-in failed"}, status_code=502
        )
    data = integrations.describe(record.id, integration)
    data["authorizeUrl"] = sign_in.authorize_url or None
    return JSONResponse(data)


async def disconnect_integration(request: Request) -> JSONResponse:
    from suzent.core.mcp_oauth import sign_out
    from suzent.core.secrets import get_secret_manager
    from suzent.plugins import integrations

    record, integration, error = _integration_or_error(request)
    if error is not None:
        return error
    integrations.forget_error(record.id, integration)
    if integration.auth == "token":
        await asyncio.to_thread(
            get_secret_manager().delete,
            integrations.token_key(record.id, integration),
        )
    else:
        # Runs on the event loop: it cancels a sign-in task still waiting.
        sign_out(integrations.namespace(record.id, integration))
    _rebuild_agent()
    return JSONResponse(integrations.describe(record.id, integration))
