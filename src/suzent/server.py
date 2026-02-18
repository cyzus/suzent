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

import os
import sys
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, WebSocketRoute

from suzent.logger import get_logger, setup_logging
from suzent.routes.chat_routes import (
    chat,
    create_chat,
    delete_chat,
    get_chat,
    get_chats,
    stop_chat,
    update_chat,
)
from suzent.routes.config_routes import (
    get_api_keys_status,
    get_config,
    get_embedding_models,
    save_api_keys,
    save_preferences,
    verify_provider,
    get_social_config,
    save_social_config,
)
from suzent.routes.plan_routes import get_plan, get_plans
from suzent.routes.mcp_routes import (
    list_mcp_servers,
    add_mcp_server,
    remove_mcp_server,
    set_mcp_server_enabled,
)
from suzent.routes.memory_routes import (
    get_core_memory,
    update_core_memory_block,
    search_archival_memory,
    delete_archival_memory,
    get_memory_stats,
)
from suzent.routes.sandbox_routes import (
    list_sandbox_files,
    read_sandbox_file,
    write_sandbox_file,
    delete_sandbox_file,
    serve_sandbox_file,
    serve_sandbox_file_wildcard,
    upload_files,
)
from suzent.routes.skill_routes import get_skills, reload_skills, toggle_skill
from suzent.routes.system_routes import list_host_files, open_in_explorer
from suzent.routes.session_routes import (
    get_session_transcript,
    get_session_state,
    get_memory_daily_log,
    list_memory_daily_logs,
    get_memory_file,
    reindex_memories,
)
from suzent.routes.browser_routes import browser_websocket_endpoint
from suzent.routes.node_routes import (
    node_websocket_endpoint,
    list_nodes,
    describe_node,
    invoke_node_command,
)
from suzent.channels.manager import ChannelManager
from suzent.nodes.manager import NodeManager

from suzent.core.social_brain import SocialBrain
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


async def startup():
    """Initialize services on application startup."""
    from suzent.memory.lifecycle import init_memory_system
    from suzent.database import get_database

    logger.info("Application startup - initializing services")

    import asyncio
    from suzent.tools.browsing_tool import BrowserSessionManager
    from suzent.config import CONFIG

    try:
        CONFIG.reload()
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")

    try:
        BrowserSessionManager.get_instance().set_main_loop(asyncio.get_running_loop())
    except Exception as e:
        logger.error(f"Failed to set browser session loop: {e}")

    db = get_database()
    try:
        api_keys = db.get_api_keys()
        loaded_count = 0
        for key, value in api_keys.items():
            if value:
                os.environ[key] = value
                loaded_count += 1
        if loaded_count > 0:
            logger.info(f"Loaded {loaded_count} API keys from database")
    except Exception as e:
        logger.error(f"Failed to load API keys on startup: {e}")

    async def init_background_services(cm, sb):
        """Run heavy initialization tasks (memory, channels, social) in background."""
        await init_memory_system()
        try:
            await cm.start_all()
            await sb.start()
            logger.info("Background services started successfully")
        except Exception as e:
            logger.error(f"Failed to start background services: {e}")

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

    logger.info("Node system initialized")

    global social_brain, channel_manager
    try:
        import json
        from suzent.config import PROJECT_DIR

        channel_manager = ChannelManager()

        config_path = PROJECT_DIR / "config/social.json"
        social_config = {}

        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    social_config = json.load(f)
                logger.info(f"Loaded social config from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load social config: {e}")

        social_model = social_config.get("model")

        channel_manager.load_drivers_from_config(social_config)

        allowed_users = set(social_config.get("allowed_users", []))

        env_allowed = os.environ.get("ALLOWED_SOCIAL_USERS", "")
        if env_allowed:
            allowed_users.update(
                [u.strip() for u in env_allowed.split(",") if u.strip()]
            )

        platform_allowlists = {}
        for platform, settings in social_config.items():
            if isinstance(settings, dict) and "allowed_users" in settings:
                platform_allowlists[platform] = settings.get("allowed_users", [])

        social_brain = SocialBrain(
            channel_manager,
            allowed_users=list(allowed_users),
            platform_allowlists=platform_allowlists,
            model=social_model,
            memory_enabled=social_config.get("memory_enabled", True),
            tools=social_config.get("tools"),
            mcp_enabled=social_config.get("mcp_enabled"),
        )

        app.state.social_brain = social_brain
        asyncio.create_task(init_background_services(channel_manager, social_brain))

    except Exception as e:
        logger.error(f"Failed to initialize Social Messaging: {e}")


def ensure_app_data():
    """Ensure required data directories (config, skills) exist in PROJECT_DIR."""
    from suzent.config import PROJECT_DIR

    print("INFO: Starting App Data Verification...", flush=True)

    for dir_name in ["config", "skills"]:
        target = PROJECT_DIR / dir_name
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


async def shutdown():
    """Cleanup services on application shutdown."""
    from suzent.memory.lifecycle import shutdown_memory_system

    logger.info("Application shutdown - cleaning up services")

    global social_brain, channel_manager, node_manager

    if social_brain:
        await social_brain.stop()

    if channel_manager:
        await channel_manager.stop_all()

    if node_manager:
        for node in list(node_manager.nodes.values()):
            if hasattr(node, "close"):
                try:
                    await node.close()
                except Exception:
                    pass
            node_manager.unregister_node(node.node_id)
        logger.info("Node system shut down")

    await shutdown_memory_system()

    try:
        from suzent.tools.browsing_tool import BrowserSessionManager

        await BrowserSessionManager.get_instance().close_session()
    except Exception as e:
        logger.error(f"Error shutting down browser session: {e}")


app = Starlette(
    debug=True,
    routes=[
        Route("/chat", chat, methods=["POST"]),
        Route("/chat/stop", stop_chat, methods=["POST"]),
        Route("/chats", get_chats, methods=["GET"]),
        Route("/chats", create_chat, methods=["POST"]),
        Route("/chats/{chat_id}", get_chat, methods=["GET"]),
        Route("/chats/{chat_id}", update_chat, methods=["PUT"]),
        Route("/chats/{chat_id}", delete_chat, methods=["DELETE"]),
        Route("/plans", get_plans, methods=["GET"]),
        Route("/plan", get_plan, methods=["GET"]),
        Route("/config", get_config, methods=["GET"]),
        Route("/preferences", save_preferences, methods=["POST"]),
        Route("/config/api-keys", get_api_keys_status, methods=["GET"]),
        Route("/config/api-keys", save_api_keys, methods=["POST"]),
        Route(
            "/config/providers/{provider_id}/verify", verify_provider, methods=["POST"]
        ),
        Route("/config/embedding-models", get_embedding_models, methods=["GET"]),
        Route("/config/social", get_social_config, methods=["GET"]),
        Route("/config/social", save_social_config, methods=["POST"]),
        Route("/mcp_servers", list_mcp_servers, methods=["GET"]),
        Route("/mcp_servers", add_mcp_server, methods=["POST"]),
        Route("/mcp_servers/remove", remove_mcp_server, methods=["POST"]),
        Route("/mcp_servers/enabled", set_mcp_server_enabled, methods=["POST"]),
        Route("/sandbox/files", list_sandbox_files, methods=["GET"]),
        Route("/sandbox/read_file", read_sandbox_file, methods=["GET"]),
        Route("/sandbox/file", write_sandbox_file, methods=["POST", "PUT"]),
        Route("/sandbox/file", delete_sandbox_file, methods=["DELETE"]),
        Route("/sandbox/serve", serve_sandbox_file, methods=["GET"]),
        Route(
            "/sandbox/serve/{chat_id}/{file_path:path}",
            serve_sandbox_file_wildcard,
            methods=["GET"],
        ),
        Route("/sandbox/upload", upload_files, methods=["POST"]),
        Route("/system/files", list_host_files, methods=["GET"]),
        Route("/system/open_explorer", open_in_explorer, methods=["POST"]),
        Route("/memory/core", get_core_memory, methods=["GET"]),
        Route("/memory/core", update_core_memory_block, methods=["PUT"]),
        Route("/memory/archival", search_archival_memory, methods=["GET"]),
        Route(
            "/memory/archival/{memory_id}", delete_archival_memory, methods=["DELETE"]
        ),
        Route("/memory/stats", get_memory_stats, methods=["GET"]),
        Route("/memory/daily", list_memory_daily_logs, methods=["GET"]),
        Route("/memory/daily/{date}", get_memory_daily_log, methods=["GET"]),
        Route("/memory/file", get_memory_file, methods=["GET"]),
        Route("/memory/reindex", reindex_memories, methods=["POST"]),
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
        Route("/skills/{skill_name}/toggle", toggle_skill, methods=["POST"]),
        WebSocketRoute("/ws/browser", browser_websocket_endpoint),
        WebSocketRoute("/ws/node", node_websocket_endpoint),
        Route("/nodes", list_nodes, methods=["GET"]),
        Route("/nodes/{node_id}", describe_node, methods=["GET"]),
        Route("/nodes/{node_id}/invoke", invoke_node_command, methods=["POST"]),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
    on_startup=[startup],
    on_shutdown=[shutdown],
)


if __name__ == "__main__":
    import asyncio
    import datetime
    from pathlib import Path

    import uvicorn

    # File logging in bundled mode (stdout must stay clean for Tauri port detection)
    if os.getenv("SUZENT_APP_DATA"):
        try:
            debug_log = Path.home() / "suzent_startup.log"
            from loguru import logger as _debug_logger

            _debug_logger.add(
                str(debug_log), rotation="10 MB", retention=2, level="DEBUG"
            )
            _debug_logger.info(
                f"--- SERVER PROCESS STARTING AT {datetime.datetime.now()} ---"
            )
        except Exception:
            pass

    ensure_app_data()

    port = int(os.getenv("SUZENT_PORT", "8000"))
    host = os.getenv("SUZENT_HOST", "0.0.0.0")

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

    async def main():
        config = uvicorn.Config(
            app, host=host, port=port, log_level=log_level.lower(), ws="wsproto"
        )
        server = uvicorn.Server(config)

        startup_task = asyncio.create_task(server.serve())

        while not server.started:
            await asyncio.sleep(0.1)

        if port == 0:
            import threading
            import time

            def monitor_stdin():
                try:
                    if not sys.stdin.read(1):
                        os._exit(0)
                except Exception:
                    os._exit(0)

            def monitor_parent(pid):
                try:
                    import psutil

                    logger.info(f"Starting parent monitor for PID {pid}")
                    while True:
                        if not psutil.pid_exists(pid):
                            logger.critical(
                                f"Parent process {pid} died. Shutting down."
                            )
                            os._exit(0)
                        time.sleep(1)
                except ImportError:
                    logger.warning(
                        "psutil not found, parent monitoring disabled (rely on stdin)."
                    )
                except Exception as e:
                    logger.error(f"Parent monitor failed: {e}")

            parent_pid = os.getppid()
            threading.Thread(target=monitor_stdin, daemon=True).start()
            threading.Thread(
                target=monitor_parent, args=(parent_pid,), daemon=True
            ).start()

            try:
                for _ in range(50):
                    if server.servers and server.servers[0].sockets:
                        break
                    await asyncio.sleep(0.1)

                if server.servers and server.servers[0].sockets:
                    effective_port = server.servers[0].sockets[0].getsockname()[1]
                    report_port(effective_port)
                    logger.info(f"Dynamic port assigned: {effective_port}")
            except Exception as e:
                logger.error(f"Failed to retrieve dynamic port: {e}")
        else:
            report_port(port)

        await startup_task

    if port == 0:
        logger.info("Starting Suzent server with dynamic port assignment...")
    else:
        logger.info(f"Starting Suzent server on http://{host}:{port}")

    asyncio.run(main())
