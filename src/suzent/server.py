"""
Starlette-based web server for the Suzent AI agent application.

This server provides a REST API with the following endpoints:
- /chat: Stream agent responses via SSE
- /chat/stop: Stop active streaming sessions
- /config: Get application configuration
- /plans: List plan versions for a chat
- /plan: Get current plan and history
- /chats: List, create, update, and delete chats

The application uses modular routing with separated concerns for maintainability.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.tools.browser.extension.routes import (
    extension_settings,
    extension_connect_page,
    extension_download,
    extension_websocket,
)
from suzent.logger import get_logger, setup_logging
from suzent.routes.chat_routes import (
    approve_tool,
    chat,
    chat_send,
    create_chat,
    deactivate_tool,
    delete_chat,
    get_chat,
    get_chat_file_changes,
    get_chats,
    get_permission_mode,
    live_stream,
    mark_chat_read,
    retry_chat,
    fork_chat_route,
    steer_chat,
    steer_chat_send,
    set_permission_mode,
    stop_chat,
    update_chat,
    undo_chat_files,
)
from suzent.routes.compact_routes import compact_chat
from suzent.routes.chatgpt_routes import (
    get_chatgpt_status,
    logout_chatgpt,
    start_chatgpt_login,
)
from suzent.routes.wechat_routes import poll_wechat_login, start_wechat_login
from suzent.routes.commands_routes import get_commands
from suzent.routes.project_routes import (
    create_project,
    delete_project,
    list_projects,
    move_all_chats,
    move_chat_to_project,
    update_project,
)
from suzent.routes.permission_routes import (
    create_permission_rule,
    delete_permission_rule,
    get_chat_permission_state,
    get_permissions,
)
from suzent.routes.config_routes import (
    get_api_keys_status,
    get_config,
    get_embedding_models,
    save_api_keys,
    save_default_permission_mode,
    save_preferences,
    save_global_sandbox_config,
    verify_provider,
    get_social_config,
    save_social_config,
    get_global_cost,
    get_chat_cost,
    get_daily_cost,
    get_hourly_cost,
    get_activity_grid,
    get_models_cost,
    get_activity_cost,
    get_role_models,
    save_role_models,
    get_role_suggestions,
    save_custom_provider,
    delete_custom_provider,
    sync_capabilities,
)
from suzent.routes.sync_routes import (
    create_sync_profile,
    discard_outgoing_sync,
    get_github_auth_status,
    get_sync_file_diff,
    get_sync_plan,
    get_sync_profiles,
    get_sync_quickstart_info,
    get_sync_status,
    logout_github_auth,
    poll_github_auth,
    pull_sync,
    push_sync,
    quickstart_sync,
    run_auto_sync,
    save_auto_config,
    start_github_auth,
    validate_sync_profile,
)
from suzent.routes.goal_task_routes import (
    get_project_goal,
    update_project_goal,
    get_project_tasks,
    get_project_kanban,
    create_project_task,
    update_project_task,
    delete_project_task,
)
from suzent.routes.mcp_routes import (
    list_mcp_servers,
    add_mcp_server,
    update_mcp_server,
    remove_mcp_server,
    set_mcp_server_enabled,
    test_mcp_server,
)
from suzent.routes.memory_routes import (
    get_core_memory,
    update_core_memory_block,
    list_project_contexts,
    get_repository_context,
    update_project_context,
    search_archival_memory,
    delete_archival_memory,
    get_memory_stats,
    consolidate_memory,
    lint_memory,
    get_dream_status,
)
from suzent.routes.sandbox_routes import (
    list_sandbox_files,
    search_file_mentions,
    read_sandbox_file,
    write_sandbox_file,
    delete_sandbox_file,
    serve_sandbox_file,
    serve_sandbox_file_wildcard,
    get_sandbox_volumes,
    upload_files,
)
from suzent.routes.skill_routes import get_skills, reload_skills, toggle_skill
from suzent.routes.system_routes import (
    get_system_version,
    list_host_files,
    open_in_explorer,
)
from suzent.routes.session_routes import (
    get_session_transcript,
    get_session_state,
    get_memory_daily_log,
    list_memory_daily_logs,
    get_memory_file,
    reindex_memories,
)
from suzent.routes.browser_routes import (
    browser_settings_endpoint,
    browser_websocket_endpoint,
)
from suzent.routes.node_routes import (
    browser_node_page,
    node_websocket_endpoint,
    list_nodes,
    describe_node,
    invoke_node_command,
    list_pending_nodes,
    approve_pending_node,
    deny_pending_node,
    list_approved_devices,
    list_unauthorized_triggers,
    revoke_device,
    set_device_status,
    create_host_token,
    get_node_config,
    save_node_config,
    discover_nodes,
    connect_node,
    list_connections,
    disconnect_node,
    grant_request,
    grant_status,
    list_grants,
    approve_grant,
    deny_grant,
    request_control,
    control_status,
    list_peers,
    set_peer_mode,
    set_peer_reverse,
    remove_peer,
    trigger_peer,
    peer_offer,
    peer_invoke,
    serve_peer_file,
    invoke_peer,
    proxy_peer_file,
    peer_capabilities,
)
from suzent.routes.cron_routes import (
    list_cron_jobs,
    create_cron_job,
    update_cron_job,
    delete_cron_job,
    trigger_cron_job,
    get_cron_status,
    get_cron_notifications,
    get_cron_job_runs,
    install_cron_presets,
)
from suzent.routes.heartbeat_routes import (
    get_heartbeat_status,
    enable_heartbeat,
    disable_heartbeat,
    trigger_heartbeat,
    get_heartbeat_md,
    save_heartbeat_md,
    set_heartbeat_interval,
    get_heartbeat_global_config,
    save_heartbeat_global_config,
)
from suzent.routes.a2ui_routes import a2ui_action, a2ui_answer
from suzent.routes.acp_routes import (
    create_acp_session,
    list_acp_agents,
    list_acp_permissions,
    list_acp_sessions,
    resolve_acp_permission,
    resume_acp_session,
    probe_acp_agent,
)
from suzent.routes.subagent_routes import (
    list_active_subagents,
    list_subagents,
    get_subagent,
    stop_subagent_route,
    steer_subagent_route,
    clear_stuck_subagents_route,
    stream_subagents,
)
from suzent.routes.event_bus_routes import event_bus_stream
from suzent.routes.suzent_channel_routes import (
    suzent_channel_inbox,
    suzent_channel_inbound,
    suzent_channel_session,
    suzent_channel_stop,
    suzent_channel_whoami,
    suzent_channel_grant_changed,
)
from suzent.routes.a2a_routes import (
    a2a_add_agent,
    a2a_agent_card,
    a2a_cancel_outbound_task,
    a2a_list_agents,
    a2a_list_tasks,
    a2a_outbound_tasks,
    a2a_refresh_agent,
    a2a_refresh_outbound_task,
    a2a_remove_agent,
    a2a_rpc,
    a2a_save_status,
    a2a_send_to_agent,
    a2a_status,
    a2a_update_agent,
)
from suzent.channels.manager import ChannelManager
from suzent.nodes.manager import NodeManager

from suzent.core.social_brain import SocialBrain
from suzent.core.scheduler import SchedulerBrain
from suzent.core.heartbeat import HeartbeatRunner
from suzent.sync.automation import SyncAutomationRunner
from suzent.sync.service import GitHubSyncService
from suzent.config import PROJECT_DIR as _project_dir

load_dotenv(_project_dir / ".env")

# Ensure stdout/stderr use UTF-8 on Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Setup logging
if "--debug" in sys.argv:
    os.environ["LOG_LEVEL"] = "DEBUG"

log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE")
setup_logging(level=log_level, log_file=log_file)

logger = get_logger(__name__)

social_brain: SocialBrain = None
channel_manager: ChannelManager = None
node_manager: NodeManager = None
node_advertiser = None
outbound_manager = None
scheduler_brain: SchedulerBrain = None
heartbeat_runner: HeartbeatRunner = None
sync_automation_runner: SyncAutomationRunner = None
agent_inbox_dispatcher = None


_social_reload_lock = asyncio.Lock()


async def health(_request: Request) -> JSONResponse:
    """Lightweight liveness probe used for process identity and supervision."""
    from suzent.routes.system_routes import get_backend_version

    return JSONResponse(
        {
            "app": "suzent",
            "status": "ok",
            "version": get_backend_version(),
            "run_mode": os.getenv("SUZENT_RUN_MODE", "standalone"),
            "pid": os.getpid(),
        }
    )


async def readiness(request: Request) -> JSONResponse:
    """Report whether background subsystems finished their startup sequence."""
    ready = bool(getattr(request.app.state, "background_services_ready", False))
    return JSONResponse(
        {"app": "suzent", "status": "ready" if ready else "starting"},
        status_code=200 if ready else 503,
    )


async def service_runtime_status(request: Request) -> JSONResponse:
    """Expose privacy-safe process health for the local desktop UI and CLI."""
    import time

    import psutil

    process = psutil.Process(os.getpid())
    return JSONResponse(
        {
            "app": "suzent",
            "run_mode": os.getenv("SUZENT_RUN_MODE", "standalone"),
            "pid": process.pid,
            "uptime_seconds": max(0.0, time.time() - process.create_time()),
            "rss_bytes": process.memory_info().rss,
            "threads": process.num_threads(),
            "ready": bool(
                getattr(request.app.state, "background_services_ready", False)
            ),
            "scheduler_running": bool(
                scheduler_brain and getattr(scheduler_brain, "_running", False)
            ),
            "heartbeat_running": bool(
                heartbeat_runner and getattr(heartbeat_runner, "_running", False)
            ),
            "channels_configured": len(channel_manager.channels)
            if channel_manager
            else 0,
        }
    )


async def stop_service(request: Request) -> JSONResponse:
    """Request graceful shutdown using the running backend's private token."""
    import hmac

    expected = os.getenv("SUZENT_SERVICE_CONTROL_TOKEN", "")
    provided = request.headers.get("X-Suzent-Service-Token", "")
    if not expected:
        return JSONResponse({"error": "shutdown_not_enabled"}, status_code=409)
    if not hmac.compare_digest(provided, expected):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    server = getattr(request.app.state, "uvicorn_server", None)
    if server is None:
        return JSONResponse({"error": "server_not_ready"}, status_code=503)
    server.should_exit = True
    return JSONResponse({"status": "stopping"}, status_code=202)


def _build_social_from_config(
    social_config: dict,
) -> tuple["ChannelManager", "SocialBrain"]:
    cm = ChannelManager()
    cm.load_drivers_from_config(social_config)

    platform_allowlists = {}
    for platform, settings in social_config.items():
        if isinstance(settings, dict) and "allowed_users" in settings:
            platform_allowlists[platform] = set(settings.get("allowed_users") or [])

    # Migration: the top-level `allowed_users` key and ALLOWED_SOCIAL_USERS predate
    # per-platform allowlists and carry no platform of their own. Fan them out to
    # every configured platform — sender ids are namespaced, so an id only ever
    # matched its own platform anyway, and this drops the old display-name match
    # that let a sender on one platform inherit an approval from another.
    legacy_allowed = set(social_config.get("allowed_users") or [])
    env_allowed = os.environ.get("ALLOWED_SOCIAL_USERS", "")
    legacy_allowed.update(u.strip() for u in env_allowed.split(",") if u.strip())
    if legacy_allowed and platform_allowlists:
        logger.warning(
            "social: %d global allowed_users entr%s applied to every platform "
            "(%s). Global allowlists are deprecated — move each entry to the "
            "platform it belongs to and remove the top-level key.",
            len(legacy_allowed),
            "y" if len(legacy_allowed) == 1 else "ies",
            ", ".join(sorted(platform_allowlists)),
        )
        for entries in platform_allowlists.values():
            entries.update(legacy_allowed)

    handshake_cfg = social_config.get("handshake", {})
    sb = SocialBrain(
        cm,
        platform_allowlists={k: list(v) for k, v in platform_allowlists.items()},
        model=social_config.get("model"),
        memory_enabled=social_config.get("memory_enabled", True),
        tools=social_config.get("tools"),
        mcp_enabled=social_config.get("mcp_enabled"),
        handshake_enabled=handshake_cfg.get("enabled", False),
        handshake_greeting=handshake_cfg.get("greeting"),
    )
    return cm, sb


async def reload_social(starlette_app, social_config: dict) -> None:
    """Stop the current social stack and restart it from the given config."""
    global social_brain, channel_manager

    async with _social_reload_lock:
        if social_brain is not None:
            await _stop(social_brain.stop(), "SocialBrain")
        if channel_manager is not None:
            await _stop(channel_manager.stop_all(), "ChannelManager")

        new_cm, new_sb = _build_social_from_config(social_config)
        social_brain = new_sb
        channel_manager = new_cm
        starlette_app.state.social_brain = new_sb

    try:
        await new_cm.start_all()
        await new_sb.start()
        logger.info("Social stack reloaded successfully.")
    except Exception as e:
        logger.error(f"Error starting reloaded social stack: {e}")


# ---------------------------------------------------------------------------
# Pairing / handshake REST handlers
# ---------------------------------------------------------------------------


async def list_pairings(request: Request) -> JSONResponse:
    """GET /social/pairing — list pending pairing requests."""
    brain: SocialBrain = getattr(request.app.state, "social_brain", None)
    if brain is None:
        return JSONResponse({"pairings": []})
    return JSONResponse({"pairings": brain.list_pairings()})


async def _parse_pairing_request(request: Request):
    """Return (brain, token, None) on success, or (None, None, error_response) on failure."""
    brain: SocialBrain = getattr(request.app.state, "social_brain", None)
    if brain is None:
        return (
            None,
            None,
            JSONResponse({"error": "Social brain not running"}, status_code=503),
        )
    try:
        data = await request.json()
        token = str(data.get("token", "")).strip()
    except Exception:
        return None, None, JSONResponse({"error": "Invalid payload"}, status_code=400)
    if not token:
        return None, None, JSONResponse({"error": "token is required"}, status_code=400)
    return brain, token, None


async def approve_pairing(request: Request) -> JSONResponse:
    """POST /social/pairing/approve  body: {"token": "..."}"""
    brain, token, err = await _parse_pairing_request(request)
    if err is not None:
        return err
    ok = await brain.approve_by_token(token)
    if not ok:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=404)
    return JSONResponse({"success": True})


async def deny_pairing(request: Request) -> JSONResponse:
    """POST /social/pairing/deny  body: {"token": "..."}"""
    brain, token, err = await _parse_pairing_request(request)
    if err is not None:
        return err
    ok = await brain.deny_by_token(token)
    if not ok:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=404)
    return JSONResponse({"success": True})


async def _refresh_provider_models() -> None:
    """Background task: discover available models for all configured providers."""
    await asyncio.sleep(3)  # let server finish starting up

    try:
        from suzent.core.providers import ProviderFactory, PROVIDER_REGISTRY
        from suzent.core.providers.helpers import resolve_api_key
        from suzent.core.model_registry import (
            save_discovered_models,
            prune_stale_models,
            get_model_registry,
        )

        refreshed = 0
        for spec in PROVIDER_REGISTRY:
            if not spec.api_key_optional:
                if not spec.env_keys or not resolve_api_key(spec.id):
                    continue
            try:
                provider = ProviderFactory.get_provider(spec.id, {})
                models = await provider.list_models()
                if models:
                    model_ids = [m.id for m in models]
                    save_discovered_models(spec.id, model_ids)
                    prune_stale_models(spec.id, model_ids)
                    refreshed += 1
            except Exception:
                pass  # credentials invalid or network unreachable — skip silently

        if refreshed:
            get_model_registry().reload()
            logger.info(
                "Background model refresh completed for {} provider(s)", refreshed
            )

        # Pull capability metadata from LiteLLM after model discovery
        try:
            from suzent.core.model_registry import sync_from_litellm

            await sync_from_litellm()
            get_model_registry().reload()
        except Exception as exc:
            logger.debug("LiteLLM capability sync skipped: {}", exc)
    except Exception as exc:
        logger.debug("Background model refresh failed: {}", exc)


async def _monitor_service_resources() -> None:
    """Gracefully recycle an unattended service after sustained memory growth."""
    import psutil

    from suzent.service.resource_guard import ResourceGuard

    try:
        max_rss_mb = max(256, int(os.getenv("SUZENT_SERVICE_MAX_RSS_MB", "1024")))
        interval = max(5, int(os.getenv("SUZENT_SERVICE_RSS_INTERVAL", "60")))
    except ValueError:
        max_rss_mb = 1024
        interval = 60
    guard = ResourceGuard(max_rss_bytes=max_rss_mb * 1024 * 1024)
    process = psutil.Process(os.getpid())
    while True:
        await asyncio.sleep(interval)
        rss_bytes = process.memory_info().rss
        if not guard.observe(rss_bytes):
            continue
        logger.error(
            "Service memory stayed above {} MiB for {} samples; restarting",
            max_rss_mb,
            guard.consecutive_limit,
        )
        server = getattr(app.state, "uvicorn_server", None)
        if server is not None:
            os.environ["SUZENT_SERVICE_RECYCLE"] = "1"
            server.should_exit = True
        return


async def startup():
    """Initialize services on application startup."""
    from suzent.memory.lifecycle import init_memory_system, _memory_rag_hook
    from suzent.core.system_reminder import register_global_hook, register_per_turn_hook
    from suzent.skills.hooks import skills_reminder_hook
    from suzent.core.repository_context import repository_agents_reminder_hook
    from suzent.tools.overflow import (
        sweep_overflow_in_background,
        sweep_overflow_periodically,
    )
    from suzent.tools.plan_hooks import plan_reminder_hook
    from suzent.database import get_database

    logger.info("Application startup - initializing services")
    app.state.background_services_ready = False
    if os.getenv("SUZENT_RUN_MODE") == "service":
        app.state.service_resource_guard = asyncio.create_task(
            _monitor_service_resources(), name="service_resource_guard"
        )

    try:
        from genai_prices import UpdatePrices

        UpdatePrices().start()
        logger.info("genai-prices background updater started")
    except Exception as e:
        logger.warning(f"Failed to start genai-prices updater: {e}")

    # Registration order is priority order under the reminder budget, so the
    # goal objective goes first: a large skill catalog crowding it out leaves
    # the agent working on a goal it can no longer see.
    register_global_hook(plan_reminder_hook)
    register_global_hook(skills_reminder_hook)
    register_global_hook(repository_agents_reminder_hook)
    register_per_turn_hook(_memory_rag_hook)

    from suzent.tools.browser.tool import BrowserSessionManager
    from suzent.config import CONFIG

    try:
        CONFIG.reload()
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")

    try:
        BrowserSessionManager.get_instance().set_main_loop(asyncio.get_running_loop())
    except Exception as e:
        logger.error(f"Failed to set browser session loop: {e}")

    try:
        from suzent.core.mcp_store import migrate_from_db

        migrated = migrate_from_db()
        if migrated:
            logger.info(
                f"Migrated {migrated} MCP servers from database to mcp_servers.json"
            )
    except Exception as e:
        logger.warning(f"MCP store migration failed: {e}")

    db = get_database()
    try:
        # Load all stored secrets into os.environ via SecretManager
        from suzent.core.secrets import get_secret_manager

        sm = get_secret_manager()
        loaded_count = sm.inject_all_to_env()

        # Also load non-secret config blobs (e.g. _PROVIDER_CONFIG_)
        api_keys = db.get_api_keys() or {}
        for key, value in api_keys.items():
            if key.startswith("_") and value and key not in os.environ:
                os.environ[key] = value

        if loaded_count > 0:
            logger.info(f"Loaded {loaded_count} secrets via {sm.backend_name}")
    except Exception as e:
        logger.error(f"Failed to load secrets on startup: {e}")
        # Fallback: load non-secret config blobs only.
        try:
            api_keys = db.get_api_keys() or {}
            for key, value in api_keys.items():
                if key.startswith("_") and value:
                    os.environ[key] = value
        except Exception:
            pass

    async def init_background_services(cm, sb):
        """Run heavy initialization tasks (memory, channels, social, scheduler) in background.

        Each subsystem is isolated: memory init must not be skipped or blocked by a
        social-messaging failure (and vice versa). cm/sb may be None when social
        config failed to build — that's fine, memory and the rest still start.
        """
        if os.getenv("SUZENT_RUN_MODE") == "service":
            logger.info("Service memory initialization deferred until first use")
        else:
            try:
                await init_memory_system()
            except Exception as e:
                logger.error(f"Failed to initialize memory system: {e}")
        try:
            if cm is not None:
                await cm.start_all()
            if sb is not None:
                await sb.start()
            logger.info("Background services started successfully")
        except Exception as e:
            logger.error(f"Failed to start background services: {e}")

        global agent_inbox_dispatcher
        try:
            from suzent.core.agent_inbox import get_agent_inbox_dispatcher

            agent_inbox_dispatcher = get_agent_inbox_dispatcher()
            app.state.agent_inbox_dispatcher = agent_inbox_dispatcher
            await agent_inbox_dispatcher.start()
        except Exception as e:
            logger.error(f"Failed to start AgentInboxDispatcher: {e}")

        # Start scheduler
        global scheduler_brain
        try:
            scheduler_brain = SchedulerBrain(tick_interval=30.0)
            app.state.scheduler_brain = scheduler_brain
            await scheduler_brain.start()
            logger.info("SchedulerBrain started successfully")
        except Exception as e:
            logger.error(f"Failed to start SchedulerBrain: {e}")

        # Start heartbeat
        global heartbeat_runner
        try:
            heartbeat_runner = HeartbeatRunner(interval_minutes=1)
            app.state.heartbeat_runner = heartbeat_runner
            await heartbeat_runner.start()
        except Exception as e:
            logger.error(f"Failed to start HeartbeatRunner: {e}")

        global sync_automation_runner
        try:
            app.state.github_sync_service = GitHubSyncService()
            sync_automation_runner = SyncAutomationRunner(app.state.github_sync_service)
            app.state.sync_automation_runner = sync_automation_runner
            await sync_automation_runner.start()
        except Exception as e:
            logger.error(f"Failed to start SyncAutomationRunner: {e}")

        app.state.background_services_ready = True
        logger.info("Application background services are ready")

    global node_manager
    node_manager = NodeManager()
    app.state.node_manager = node_manager

    try:
        from suzent.nodes.local_node import LocalNode

        local_node = LocalNode(display_name="Local PC")
        node_manager.register_node(local_node)
        cap_names = ", ".join(c.name for c in local_node.capabilities)
        logger.info(f"Local node registered: {cap_names}")
    except Exception as e:
        logger.warning(f"Failed to register local node: {e}")

    # Manager for outbound (click-to-pair) connections this device initiates.
    global outbound_manager, node_advertiser
    try:
        from suzent.nodes.outbound import OutboundConnectionManager

        outbound_manager = OutboundConnectionManager()
        app.state.outbound_manager = outbound_manager
    except Exception as e:
        logger.warning(f"Failed to init outbound manager: {e}")

    # Controller-side store of peers this device may drive (control-grant).
    try:
        from suzent.nodes.peer_store import get_peer_grant_store

        app.state.peer_store = get_peer_grant_store()
    except Exception as e:
        logger.warning(f"Failed to init peer store: {e}")

    # Advertise this server over mDNS so LAN peers can discover it.
    if getattr(CONFIG, "node_discovery_enabled", True):
        try:
            import socket as _socket

            from suzent.config import DEFAULT_PORT
            from suzent.nodes.discovery import SuzentAdvertiser

            node_advertiser = SuzentAdvertiser(
                port=int(getattr(app.state, "server_port", DEFAULT_PORT)),
                display_name=_socket.gethostname(),
            )
            app.state.node_advertiser = node_advertiser

            def _start_node_advertiser() -> None:
                try:
                    node_advertiser.start()
                except Exception as e:
                    logger.warning(f"Failed to start mDNS advertiser: {e}")

            asyncio.create_task(asyncio.to_thread(_start_node_advertiser))
        except Exception as e:
            logger.warning(f"Failed to start mDNS advertiser: {e}")

    logger.info("Node system initialized")

    # Before the duplicate-social guard below, which returns early. shutdown()
    # cancels the sweeper but leaves social_brain set, so on an in-process
    # restart that return would skip both the startup sweep and the periodic
    # one — leaving retention and the root quota unenforced until the process
    # itself restarts.
    #
    # Spilled output is otherwise pruned only when the next spill is written,
    # which is to say not at all once output stops overflowing.
    sweep_overflow_in_background()
    existing_sweeper = getattr(app.state, "overflow_sweeper", None)
    if existing_sweeper is None or existing_sweeper.done():
        app.state.overflow_sweeper = asyncio.create_task(
            sweep_overflow_periodically(), name="overflow_sweeper"
        )

    global social_brain, channel_manager
    if social_brain is not None:
        logger.warning("Social brain already initialized, skipping duplicate startup.")
        return

    # Build social objects best-effort. A failure here must NOT prevent the
    # background services (memory, scheduler, heartbeat, sync) from starting —
    # so the launch below is unconditional and outside this try.
    try:
        import json
        from suzent.config import PROJECT_DIR

        config_path = PROJECT_DIR / "config/social.json"
        social_config = {}

        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    social_config = json.load(f)
                logger.info(f"Loaded social config from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load social config: {e}")

        channel_manager, social_brain = _build_social_from_config(social_config)
        app.state.social_brain = social_brain

    except Exception as e:
        logger.error(f"Failed to initialize Social Messaging: {e}")

    # Launch heavy background init regardless of social outcome. cm/sb may be
    # None — init_background_services tolerates that.
    asyncio.create_task(init_background_services(channel_manager, social_brain))

    # Silently refresh model lists for all configured providers in the background.
    asyncio.create_task(_refresh_provider_models())


def ensure_app_data():
    """Ensure required user data directories exist."""
    from suzent.config import (
        CACHE_DIR,
        DATA_DIR,
        RUNTIME_DIR,
        SKILLS_ROOT_DIR,
        USER_CONFIG_DIR,
    )

    # Redirect LiteLLM's ChatGPT token storage into Suzent's own config dir.
    chatgpt_token_dir = USER_CONFIG_DIR / "chatgpt"
    os.environ.setdefault("CHATGPT_TOKEN_DIR", str(chatgpt_token_dir))

    print("INFO: Starting App Data Verification...", flush=True)

    for target in [
        DATA_DIR,
        RUNTIME_DIR,
        CACHE_DIR,
        USER_CONFIG_DIR,
        SKILLS_ROOT_DIR,
    ]:
        if target.exists():
            logger.debug(f"Directory exists: {target}")
        else:
            logger.warning(f"Expected directory missing: {target}")
            # Attempt to create it so the app doesn't crash
            try:
                target.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created empty directory: {target}")
            except Exception as e:
                logger.error(f"Failed to create directory {target}: {e}")

    print("INFO: App Data Verification Complete.", flush=True)


async def _stop(coro, name: str, timeout: float = 5.0):
    try:
        await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"{name} did not stop within {timeout}s, continuing shutdown")
    except Exception as e:
        logger.error(f"Error stopping {name}: {e}")


async def shutdown():
    """Cleanup services on application shutdown."""
    from suzent.memory.lifecycle import shutdown_memory_system
    from suzent.a2ui import pending as pending_questions

    logger.info("Application shutdown - cleaning up services")

    global \
        social_brain, \
        channel_manager, \
        node_manager, \
        node_advertiser, \
        outbound_manager, \
        scheduler_brain, \
        heartbeat_runner, \
        sync_automation_runner, \
        agent_inbox_dispatcher

    # Cancel any pending ask_question futures so their tasks can exit cleanly
    pending_questions.cancel_all()

    for task_name in ("service_resource_guard", "overflow_sweeper"):
        task = getattr(app.state, task_name, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    if agent_inbox_dispatcher:
        await _stop(agent_inbox_dispatcher.stop(), "AgentInboxDispatcher")

    if node_advertiser:
        try:
            node_advertiser.stop()
        except Exception:
            pass

    if outbound_manager:
        await _stop(outbound_manager.stop_all(), "OutboundConnectionManager")

    if heartbeat_runner:
        await _stop(heartbeat_runner.stop(), "HeartbeatRunner")

    if sync_automation_runner:
        await _stop(sync_automation_runner.stop(), "SyncAutomationRunner")

    if scheduler_brain:
        await _stop(scheduler_brain.stop(), "SchedulerBrain")

    if social_brain:
        await _stop(social_brain.stop(), "SocialBrain")

    if channel_manager:
        await _stop(channel_manager.stop_all(), "ChannelManager")

    if node_manager:
        for node in list(node_manager.nodes.values()):
            if hasattr(node, "close"):
                try:
                    await node.close()
                except Exception:
                    pass
            node_manager.unregister_node(node.node_id)
        logger.info("Node system shut down")

    try:
        from suzent.core.task_registry import get_task_registry

        await get_task_registry().shutdown(timeout=3.0)
    except Exception as e:
        logger.error(f"Error shutting down task registry: {e}")

    try:
        from suzent.acp import get_acp_manager

        await _stop(get_acp_manager().shutdown(), "ACPManager")
    except Exception as e:
        logger.error(f"Error shutting down ACP manager: {e}")

    try:
        from suzent.tools.shell.host_process_registry import HostProcessRegistry

        HostProcessRegistry().shutdown()
    except Exception as e:
        logger.error(f"Error shutting down host background processes: {e}")

    await shutdown_memory_system()

    try:
        from suzent.tools.browser.tool import BrowserSessionManager

        from suzent.tools.browser.extension.session import session as extension_session

        await _stop(extension_session.close(), "BrowserExtension")
        await _stop(
            BrowserSessionManager.get_instance().close_session(), "BrowserSession"
        )
    except Exception as e:
        logger.error(f"Error shutting down browser session: {e}")

    # Gracefully shut down litellm's logging worker to avoid "Event loop is closed" noise
    try:
        from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

        task = GLOBAL_LOGGING_WORKER._worker_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app):
    await startup()
    yield
    await shutdown()


app = Starlette(
    debug=True,
    lifespan=lifespan,
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/ready", readiness, methods=["GET"]),
        Route("/service/status", service_runtime_status, methods=["GET"]),
        Route("/service/stop", stop_service, methods=["POST"]),
        Route("/acp/agents", list_acp_agents, methods=["GET"]),
        Route("/acp/agents/{agent_id}/probe", probe_acp_agent, methods=["POST"]),
        Route("/acp/sessions", list_acp_sessions, methods=["GET"]),
        Route("/acp/sessions", create_acp_session, methods=["POST"]),
        Route("/acp/sessions/resume", resume_acp_session, methods=["POST"]),
        Route("/acp/permissions", list_acp_permissions, methods=["GET"]),
        Route(
            "/acp/permissions/{request_id}",
            resolve_acp_permission,
            methods=["POST"],
        ),
        Route("/chat", chat, methods=["POST"]),
        Route("/chat/send", chat_send, methods=["POST"]),
        Route("/chat/live", live_stream, methods=["POST"]),
        Route("/chat/stop", stop_chat, methods=["POST"]),
        Route("/chat/steer", steer_chat, methods=["POST"]),
        Route("/chat/steer-send", steer_chat_send, methods=["POST"]),
        Route("/chat/approve-tool", approve_tool, methods=["POST"]),
        Route("/chat/deactivate-tool", deactivate_tool, methods=["POST"]),
        Route("/chat/compact", compact_chat, methods=["POST"]),
        Route("/chat/retry", retry_chat, methods=["POST"]),
        Route(
            "/api/chats/{chat_id}/file-changes",
            get_chat_file_changes,
            methods=["GET"],
        ),
        Route("/api/chats/{chat_id}/undo", undo_chat_files, methods=["POST"]),
        Route("/api/chats/{chat_id}/fork", fork_chat_route, methods=["POST"]),
        Route("/commands", get_commands, methods=["GET"]),
        Route("/chats", get_chats, methods=["GET"]),
        Route("/chats", create_chat, methods=["POST"]),
        Route("/chats/{chat_id}/mark-read", mark_chat_read, methods=["POST"]),
        Route(
            "/chats/{chat_id}/permission-mode",
            get_permission_mode,
            methods=["GET"],
        ),
        Route(
            "/chats/{chat_id}/permission-mode",
            set_permission_mode,
            methods=["PUT"],
        ),
        Route(
            "/chats/{chat_id}/permission-state",
            get_chat_permission_state,
            methods=["GET"],
        ),
        Route("/chats/{chat_id}/project", move_chat_to_project, methods=["POST"]),
        Route("/chats/{chat_id}", get_chat, methods=["GET"]),
        Route("/chats/{chat_id}", update_chat, methods=["PUT"]),
        Route("/chats/{chat_id}", delete_chat, methods=["DELETE"]),
        Route("/permissions", get_permissions, methods=["GET"]),
        Route("/permissions/rules", create_permission_rule, methods=["POST"]),
        Route(
            "/permissions/rules/{rule_id}",
            delete_permission_rule,
            methods=["DELETE"],
        ),
        Route("/projects", list_projects, methods=["GET"]),
        Route("/projects", create_project, methods=["POST"]),
        Route("/projects/{project_id}", update_project, methods=["PATCH"]),
        Route("/projects/{project_id}", delete_project, methods=["DELETE"]),
        Route("/projects/{project_id}/move-chats", move_all_chats, methods=["POST"]),
        Route("/project/goal", get_project_goal, methods=["GET"]),
        Route("/project/goal/action", update_project_goal, methods=["POST"]),
        Route("/project/tasks", get_project_tasks, methods=["GET"]),
        Route("/project/kanban", get_project_kanban, methods=["GET"]),
        Route("/project/tasks", create_project_task, methods=["POST"]),
        Route("/project/tasks/{task_id:int}", update_project_task, methods=["PATCH"]),
        Route("/project/tasks/{task_id:int}", delete_project_task, methods=["DELETE"]),
        Route("/config", get_config, methods=["GET"]),
        Route("/chatgpt/status", get_chatgpt_status, methods=["GET"]),
        Route("/chatgpt/login", start_chatgpt_login, methods=["POST"]),
        Route("/chatgpt/logout", logout_chatgpt, methods=["POST"]),
        Route("/preferences", save_preferences, methods=["POST"]),
        Route(
            "/config/default-permission-mode",
            save_default_permission_mode,
            methods=["PUT"],
        ),
        Route("/config/sandbox-global", save_global_sandbox_config, methods=["POST"]),
        Route("/config/api-keys", get_api_keys_status, methods=["GET"]),
        Route("/config/api-keys", save_api_keys, methods=["POST"]),
        Route(
            "/config/providers/{provider_id}/verify", verify_provider, methods=["POST"]
        ),
        Route("/config/embedding-models", get_embedding_models, methods=["GET"]),
        Route("/config/cost/global", get_global_cost, methods=["GET"]),
        Route("/config/cost/daily", get_daily_cost, methods=["GET"]),
        Route("/config/cost/hourly", get_hourly_cost, methods=["GET"]),
        Route("/config/cost/activity-grid", get_activity_grid, methods=["GET"]),
        Route("/config/cost/models", get_models_cost, methods=["GET"]),
        Route("/config/cost/activity", get_activity_cost, methods=["GET"]),
        Route("/config/cost/chat/{chat_id}", get_chat_cost, methods=["GET"]),
        Route("/config/role-models", get_role_models, methods=["GET"]),
        Route("/config/role-models", save_role_models, methods=["POST"]),
        Route("/config/role-suggestions", get_role_suggestions, methods=["GET"]),
        Route("/config/providers/custom", save_custom_provider, methods=["POST"]),
        Route(
            "/config/providers/custom/{provider_id}",
            delete_custom_provider,
            methods=["DELETE"],
        ),
        Route("/config/capabilities/sync", sync_capabilities, methods=["POST"]),
        Route("/config/social", get_social_config, methods=["GET"]),
        Route("/config/social", save_social_config, methods=["POST"]),
        Route("/sync/status", get_sync_status, methods=["GET"]),
        Route("/sync/quickstart/info", get_sync_quickstart_info, methods=["GET"]),
        Route("/sync/quickstart", quickstart_sync, methods=["POST"]),
        Route("/sync/profiles", get_sync_profiles, methods=["GET"]),
        Route("/sync/profiles", create_sync_profile, methods=["POST"]),
        Route("/sync/validate", validate_sync_profile, methods=["POST"]),
        Route("/sync/plan", get_sync_plan, methods=["POST"]),
        Route("/sync/diff", get_sync_file_diff, methods=["POST"]),
        Route("/sync/discard-outgoing", discard_outgoing_sync, methods=["POST"]),
        Route("/sync/pull", pull_sync, methods=["POST"]),
        Route("/sync/push", push_sync, methods=["POST"]),
        Route("/sync/auto", save_auto_config, methods=["POST"]),
        Route("/sync/auto/run", run_auto_sync, methods=["POST"]),
        Route("/sync/auth/start", start_github_auth, methods=["POST"]),
        Route("/sync/auth/poll", poll_github_auth, methods=["POST"]),
        Route("/sync/auth/status", get_github_auth_status, methods=["GET"]),
        Route("/sync/auth/logout", logout_github_auth, methods=["POST"]),
        Route("/social/pairing", list_pairings, methods=["GET"]),
        Route("/social/pairing/approve", approve_pairing, methods=["POST"]),
        Route("/social/pairing/deny", deny_pairing, methods=["POST"]),
        Route("/social/wechat/login", start_wechat_login, methods=["POST"]),
        Route("/social/wechat/login/{session_id}", poll_wechat_login, methods=["GET"]),
        Route("/mcp_servers", list_mcp_servers, methods=["GET"]),
        Route("/mcp_servers", add_mcp_server, methods=["POST"]),
        Route("/mcp_servers/update", update_mcp_server, methods=["POST"]),
        Route("/mcp_servers/remove", remove_mcp_server, methods=["POST"]),
        Route("/mcp_servers/enabled", set_mcp_server_enabled, methods=["POST"]),
        Route("/mcp_servers/test", test_mcp_server, methods=["POST"]),
        Route("/sandbox/files", list_sandbox_files, methods=["GET"]),
        Route("/sandbox/mentions", search_file_mentions, methods=["GET"]),
        Route("/sandbox/read_file", read_sandbox_file, methods=["GET"]),
        Route("/sandbox/file", write_sandbox_file, methods=["POST", "PUT"]),
        Route("/sandbox/file", delete_sandbox_file, methods=["DELETE"]),
        Route("/sandbox/volumes", get_sandbox_volumes, methods=["GET"]),
        Route("/sandbox/serve", serve_sandbox_file, methods=["GET"]),
        Route(
            "/sandbox/serve/{chat_id}/{file_path:path}",
            serve_sandbox_file_wildcard,
            methods=["GET"],
        ),
        Route("/sandbox/upload", upload_files, methods=["POST"]),
        Route("/system/version", get_system_version, methods=["GET"]),
        Route("/system/files", list_host_files, methods=["GET"]),
        Route("/system/open_explorer", open_in_explorer, methods=["POST"]),
        Route("/memory/core", get_core_memory, methods=["GET"]),
        Route("/memory/core", update_core_memory_block, methods=["PUT"]),
        Route("/memory/project-contexts", list_project_contexts, methods=["GET"]),
        Route("/memory/repository-context", get_repository_context, methods=["GET"]),
        Route(
            "/memory/project-contexts/{project_id}",
            update_project_context,
            methods=["PUT"],
        ),
        Route("/memory/archival", search_archival_memory, methods=["GET"]),
        Route(
            "/memory/archival/{memory_id}", delete_archival_memory, methods=["DELETE"]
        ),
        Route("/memory/stats", get_memory_stats, methods=["GET"]),
        Route("/memory/daily", list_memory_daily_logs, methods=["GET"]),
        Route("/memory/daily/{date}", get_memory_daily_log, methods=["GET"]),
        Route("/memory/file", get_memory_file, methods=["GET"]),
        Route("/memory/reindex", reindex_memories, methods=["POST"]),
        Route("/memory/dream/status", get_dream_status, methods=["GET"]),
        Route("/memory/consolidate", consolidate_memory, methods=["POST"]),
        Route("/memory/lint", lint_memory, methods=["POST"]),
        Route(
            "/session/{session_id}/transcript",
            get_session_transcript,
            methods=["GET"],
        ),
        Route(
            "/session/{session_id}/state",
            get_session_state,
            methods=["GET"],
        ),
        Route("/skills", get_skills, methods=["GET"]),
        Route("/skills/reload", reload_skills, methods=["POST"]),
        Route("/skills/toggle", toggle_skill, methods=["POST"]),
        Route("/skills/{skill_name}/toggle", toggle_skill, methods=["POST"]),
        Route(
            "/browser/extension", extension_settings, methods=["GET", "POST", "DELETE"]
        ),
        Route("/browser/extension/connect", extension_connect_page),
        Route("/browser/extension/download", extension_download),
        WebSocketRoute("/ws/browser-extension", extension_websocket),
        Route("/browser/settings", browser_settings_endpoint, methods=["GET", "POST"]),
        WebSocketRoute("/ws/browser", browser_websocket_endpoint),
        WebSocketRoute("/ws/node", node_websocket_endpoint),
        Route("/nodes", list_nodes, methods=["GET"]),
        # Specific paths must precede /nodes/{node_id} so they aren't captured
        # as a node_id by the parametrized describe route.
        Route("/nodes/config", get_node_config, methods=["GET"]),
        Route("/nodes/config", save_node_config, methods=["POST"]),
        Route("/nodes/discover", discover_nodes, methods=["GET"]),
        Route("/nodes/connect", connect_node, methods=["POST"]),
        Route("/nodes/connect/stop", disconnect_node, methods=["POST"]),
        Route("/nodes/connections", list_connections, methods=["GET"]),
        # Control-grant: target-side bootstrap (auth-exempt) + operator approval
        Route("/nodes/grant-request", grant_request, methods=["POST"]),
        Route("/nodes/grant-status/{request_id}", grant_status, methods=["GET"]),
        Route("/nodes/grants", list_grants, methods=["GET"]),
        Route("/nodes/grants/{request_id}/approve", approve_grant, methods=["POST"]),
        Route("/nodes/grants/{request_id}/deny", deny_grant, methods=["POST"]),
        # Control-grant: controller side
        Route("/nodes/control", request_control, methods=["POST"]),
        Route("/nodes/control-status", control_status, methods=["GET"]),
        Route("/nodes/peer-offer", peer_offer, methods=["POST"]),
        Route("/nodes/peer-invoke", peer_invoke, methods=["POST"]),
        Route("/nodes/peer-files/{file_id}", serve_peer_file, methods=["GET"]),
        Route("/channels/suzent/inbound", suzent_channel_inbound, methods=["POST"]),
        Route("/channels/suzent/inbox", suzent_channel_inbox, methods=["POST"]),
        Route("/channels/suzent/session", suzent_channel_session, methods=["GET"]),
        Route("/channels/suzent/stop", suzent_channel_stop, methods=["POST"]),
        Route("/channels/suzent/whoami", suzent_channel_whoami, methods=["GET"]),
        # A2A (Agent2Agent) — open federation alongside the Suzent-native mesh.
        Route("/.well-known/agent-card.json", a2a_agent_card, methods=["GET"]),
        Route("/a2a/v1", a2a_rpc, methods=["POST"]),
        Route("/a2a/status", a2a_status, methods=["GET"]),
        Route("/a2a/status", a2a_save_status, methods=["POST"]),
        Route("/a2a/tasks", a2a_list_tasks, methods=["GET"]),
        Route("/a2a/agents", a2a_list_agents, methods=["GET"]),
        Route("/a2a/agents", a2a_add_agent, methods=["POST"]),
        Route("/a2a/agents/{agent_id}", a2a_update_agent, methods=["PATCH"]),
        Route("/a2a/agents/{agent_id}", a2a_remove_agent, methods=["DELETE"]),
        Route("/a2a/agents/{agent_id}/refresh", a2a_refresh_agent, methods=["POST"]),
        Route("/a2a/agents/{agent_id}/send", a2a_send_to_agent, methods=["POST"]),
        Route("/a2a/outbound", a2a_outbound_tasks, methods=["GET"]),
        Route(
            "/a2a/outbound/{agent_id}/{task_id}/refresh",
            a2a_refresh_outbound_task,
            methods=["POST"],
        ),
        Route(
            "/a2a/outbound/{agent_id}/{task_id}/cancel",
            a2a_cancel_outbound_task,
            methods=["POST"],
        ),
        Route(
            "/channels/suzent/grant-changed",
            suzent_channel_grant_changed,
            methods=["POST"],
        ),
        Route("/nodes/peers", list_peers, methods=["GET"]),
        Route("/nodes/peers/{peer_id}/invoke", invoke_peer, methods=["POST"]),
        Route(
            "/nodes/peers/{peer_id}/files/{file_id}",
            proxy_peer_file,
            methods=["GET"],
        ),
        Route(
            "/nodes/peers/{peer_id}/capabilities",
            peer_capabilities,
            methods=["GET"],
        ),
        Route("/nodes/peers/{peer_id}/mode", set_peer_mode, methods=["POST"]),
        Route("/nodes/peers/{peer_id}/reverse", set_peer_reverse, methods=["POST"]),
        Route("/nodes/peers/{peer_id}/remove", remove_peer, methods=["POST"]),
        Route("/nodes/peers/{peer_id}/trigger", trigger_peer, methods=["POST"]),
        # Zero-install browser node: open this URL on a phone or TV.
        Route("/node", browser_node_page, methods=["GET"]),
        Route("/nodes/pending", list_pending_nodes, methods=["GET"]),
        Route(
            "/nodes/pending/{pairing_code}/approve",
            approve_pending_node,
            methods=["POST"],
        ),
        Route(
            "/nodes/pending/{pairing_code}/deny", deny_pending_node, methods=["POST"]
        ),
        Route("/nodes/devices", list_approved_devices, methods=["GET"]),
        Route("/nodes/unauthorized", list_unauthorized_triggers, methods=["GET"]),
        Route("/nodes/host-token", create_host_token, methods=["POST"]),
        Route("/nodes/devices/{device_id}/revoke", revoke_device, methods=["POST"]),
        Route("/nodes/devices/{device_id}/status", set_device_status, methods=["POST"]),
        Route("/nodes/{node_id}", describe_node, methods=["GET"]),
        Route("/nodes/{node_id}/invoke", invoke_node_command, methods=["POST"]),
        Route("/cron/jobs", list_cron_jobs, methods=["GET"]),
        Route("/cron/jobs", create_cron_job, methods=["POST"]),
        Route("/cron/jobs/{job_id:int}", update_cron_job, methods=["PUT"]),
        Route("/cron/jobs/{job_id:int}", delete_cron_job, methods=["DELETE"]),
        Route("/cron/jobs/{job_id:int}/trigger", trigger_cron_job, methods=["POST"]),
        Route("/cron/presets/install", install_cron_presets, methods=["POST"]),
        Route("/cron/status", get_cron_status, methods=["GET"]),
        Route("/cron/notifications", get_cron_notifications, methods=["GET"]),
        Route("/cron/jobs/{job_id:int}/runs", get_cron_job_runs, methods=["GET"]),
        Route("/heartbeat/status", get_heartbeat_status, methods=["GET"]),
        Route("/heartbeat/enable", enable_heartbeat, methods=["POST"]),
        Route("/heartbeat/disable", disable_heartbeat, methods=["POST"]),
        Route("/heartbeat/trigger", trigger_heartbeat, methods=["POST"]),
        Route("/heartbeat/md", get_heartbeat_md, methods=["GET"]),
        Route("/heartbeat/md", save_heartbeat_md, methods=["PUT"]),
        Route("/heartbeat/interval", set_heartbeat_interval, methods=["PUT", "POST"]),
        Route("/heartbeat/config", get_heartbeat_global_config, methods=["GET"]),
        Route("/heartbeat/config", save_heartbeat_global_config, methods=["POST"]),
        Route("/canvas/{chat_id}/action", a2ui_action, methods=["POST"]),
        Route("/canvas/{chat_id}/answer", a2ui_answer, methods=["POST"]),
        Route("/events/stream", event_bus_stream, methods=["GET"]),
        Route("/subagents/active", list_active_subagents, methods=["GET"]),
        Route("/subagents/stream", stream_subagents, methods=["GET"]),
        Route("/subagents/clear-stuck", clear_stuck_subagents_route, methods=["POST"]),
        Route("/subagents/{task_id}/steer", steer_subagent_route, methods=["POST"]),
        Route("/subagents", list_subagents, methods=["GET"]),
        Route("/subagents/{task_id}", get_subagent, methods=["GET"]),
        Route("/subagents/{task_id}/stop", stop_subagent_route, methods=["POST"]),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        # Loopback is trusted (local app); remote callers need a valid node
        # token. Keeps the API safe when node_lan_bind exposes it on the network.
        Middleware(AuthBoundaryMiddleware),
    ],
)


if __name__ == "__main__":
    import datetime

    import uvicorn

    # File logging in runtime dir (stdout must stay clean for Tauri port detection)
    try:
        from suzent.config import RUNTIME_DIR

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        debug_log = RUNTIME_DIR / "suzent_startup.log"
        from loguru import logger as _debug_logger

        _debug_logger.add(str(debug_log), rotation="10 MB", retention=2, level="DEBUG")
        _debug_logger.info(
            f"--- SERVER PROCESS STARTING AT {datetime.datetime.now()} ---"
        )
    except Exception:
        pass

    ensure_app_data()

    from suzent.config import DEFAULT_PORT, MESH_PORT

    _port_str = os.getenv("SUZENT_PORT", "").strip()
    port = int(_port_str) if _port_str else DEFAULT_PORT
    host = os.getenv("SUZENT_HOST", "0.0.0.0")
    # The desktop app pins SUZENT_HOST=127.0.0.1 (loopback only). When the user
    # opts into the node mesh, bind all interfaces so peer devices can reach the
    # node WebSocket (still reachable on loopback for the local app).
    from suzent.config import CONFIG as _CFG
    from suzent.nodes.discovery import resolve_mesh_bind

    mesh_enabled = bool(getattr(_CFG, "node_lan_bind", False))
    original_host, original_port = host, port
    host, port = resolve_mesh_bind(
        host, port, enabled=mesh_enabled, default_port=MESH_PORT
    )
    if mesh_enabled:
        if host != original_host:
            logger.info(
                f"node_lan_bind enabled: binding {host} instead of {original_host} "
                f"so peer devices can reach this server"
            )
        if port != original_port:
            logger.info(f"node_lan_bind enabled: using stable mesh port {MESH_PORT}")

    def write_port_file(effective_port: int) -> None:
        """Write the effective port to a file for CLI discovery."""
        from suzent.config import RUNTIME_DIR

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        port_file = RUNTIME_DIR / "server.port"
        try:
            port_file.write_text(str(effective_port), encoding="utf-8")
        except Exception:
            pass

    def remove_port_file() -> None:
        """Remove the port file on shutdown."""
        from suzent.config import RUNTIME_DIR

        port_file = RUNTIME_DIR / "server.port"
        try:
            if port_file.exists():
                port_file.unlink()
        except Exception:
            pass

    def report_port(effective_port: int) -> None:
        """Report the server port via multiple channels for reliability."""
        port_msg = f"SERVER_PORT:{effective_port}"
        logger.critical(port_msg)
        print(port_msg, flush=True)
        try:
            sys.stdout.buffer.write(f"{port_msg}\n".encode("utf-8"))
            sys.stdout.buffer.flush()
        except Exception:
            pass

        # Write to file for CLI discovery
        write_port_file(effective_port)

    import socket as _socket
    import threading

    # Pre-bind a socket before entering the asyncio event loop.
    # For port=0, this lets the OS choose a port dynamically so we can report it early.
    # For explicit ports (e.g., 8000), this verifies the port is available immediately,
    # and if it fails (e.g., Windows Hyper-V reserved ports), we can forceful exit
    # before uvicorn/tokio start up, avoiding PyO3 panics during graceful shutdown.
    _sock = None
    try:
        _sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        _sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        try:
            _sock.bind((host, port))
        except OSError as e:
            raise e
        _sock.listen()
        _sock.set_inheritable(True)
        effective_port = _sock.getsockname()[1]
        report_port(effective_port)
        app.state.server_host = host
        app.state.server_port = effective_port
        if port == 0:
            logger.info(f"Dynamic port assigned: {effective_port}")
    except OSError as e:
        logger.critical(f"Failed to bind to {host}:{port}: {e}")
        logger.critical(
            "Please set the SUZENT_PORT environment variable to a different port (e.g. set SUZENT_PORT=8001)"
        )
        if _sock is not None:
            try:
                _sock.close()
            except Exception:
                pass
        # Exit forcefully to prevent PyO3 panics during graceful shutdown if we haven't fully initialized
        os._exit(1)
    except Exception:
        if _sock is not None:
            try:
                _sock.close()
            except Exception:
                pass
        raise

    async def main():
        if port == 0:
            # Start process-lifetime monitors only when launched by Tauri (port=0 mode).
            # These threads must be started inside the async loop so os._exit() doesn't
            # fire before the event loop is running.
            def monitor_stdin():
                try:
                    if not sys.stdin.read(1):
                        if sys.platform == "win32":
                            logger.info(
                                "Backend stdin closed on Windows; keeping server alive."
                            )
                            return
                        os._exit(0)
                except Exception:
                    if sys.platform == "win32":
                        logger.info(
                            "Backend stdin monitor failed on Windows; keeping server alive."
                        )
                        return
                    os._exit(0)

            def monitor_parent(pid):
                import subprocess
                import time

                logger.info(f"Starting parent monitor for PID {pid}")

                while True:
                    try:
                        if sys.platform == "win32":
                            result = subprocess.run(
                                [
                                    "tasklist",
                                    "/FI",
                                    f"PID eq {pid}",
                                    "/FO",
                                    "CSV",
                                    "/NH",
                                ],
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            exists = str(pid) in result.stdout
                        else:
                            os.kill(pid, 0)
                            exists = True
                    except OSError:
                        exists = False
                    except Exception as e:
                        logger.error(f"Parent monitor failed: {e}")
                        return

                    if not exists:
                        logger.critical(f"Parent process {pid} died. Shutting down.")
                        os._exit(0)
                    time.sleep(1)

            threading.Thread(target=monitor_stdin, daemon=True).start()

            parent_pid_raw = os.getenv("SUZENT_PARENT_PID", "").strip()
            parent_pid = int(parent_pid_raw) if parent_pid_raw.isdigit() else None
            if parent_pid is None and sys.platform != "win32":
                parent_pid = os.getppid()

            if parent_pid is not None:
                threading.Thread(
                    target=monitor_parent, args=(parent_pid,), daemon=True
                ).start()
            else:
                logger.info(
                    "Parent PID monitor disabled on Windows; relying on stdin pipe."
                )

        # Use port=0 in config so uvicorn doesn't try to bind (we pass the socket).
        # _sock is closed in the finally block if uvicorn never takes ownership.
        bind_port = 0 if _sock else effective_port
        config = uvicorn.Config(
            app,
            host=host,
            port=bind_port,
            log_level=log_level.lower(),
            ws="wsproto",
            timeout_graceful_shutdown=5,  # force-close lingering SSE connections after 5s
        )
        server = uvicorn.Server(config)
        app.state.uvicorn_server = server
        sockets = [_sock] if _sock else None
        try:
            await server.serve(sockets=sockets)
        finally:
            if _sock is not None:
                try:
                    _sock.close()
                except OSError:
                    # Expected: uvicorn already closed the socket on normal shutdown
                    pass
                except Exception as e:
                    logger.debug(f"Error closing pre-bound socket: {e}")

            # Clean up port file
            remove_port_file()

    if port == 0:
        logger.info(
            f"Starting Suzent server with dynamic port assignment (port={effective_port})..."
        )
    else:
        logger.info(f"Starting Suzent server on http://{host}:{effective_port}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful shutdown timed out or was interrupted a second time — force exit.
        os._exit(0)
