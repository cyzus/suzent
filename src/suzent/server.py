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
from suzent.routes.browser_routes import browser_websocket_endpoint
from suzent.channels.manager import ChannelManager

# from suzent.channels.telegram import TelegramChannel # Loaded dynamically now
from suzent.core.social_brain import SocialBrain

# Load environment variables
load_dotenv()

# Ensure stdout/stderr use UTF-8 when possible to avoid encoding errors on Windows consoles
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # Best-effort only; if reconfigure is unavailable, fall back to environment-level solutions
    pass

# Setup logging
if "--debug" in sys.argv:
    os.environ["LOG_LEVEL"] = "DEBUG"

log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE")  # Optional: set LOG_FILE=/path/to/suzent.log
setup_logging(level=log_level, log_file=log_file)

logger = get_logger(__name__)

# --- Social Messaging State ---
social_brain: SocialBrain = None
channel_manager: ChannelManager = None


async def startup():
    """Initialize services on application startup."""
    from suzent.memory.lifecycle import init_memory_system
    from suzent.database import get_database

    logger.info("Application startup - initializing services")

    # Initialize Browser Session Manager with Main Loop for thread safety
    import asyncio
    from suzent.tools.browsing_tool import BrowserSessionManager

    try:
        BrowserSessionManager.get_instance().set_main_loop(asyncio.get_running_loop())
    except Exception as e:
        logger.error(f"Failed to set browser session loop: {e}")

    # Load API keys from database into environment
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

    await init_memory_system()

    # Initialize Social Messaging System
    global social_brain, channel_manager
    try:
        import json
        from pathlib import Path

        channel_manager = ChannelManager()

        # Load social config
        # Try finding it in config dir relative to cwd or source?
        # Assuming run from root, config/social.json
        config_path = Path("config/social.json")
        social_config = {}

        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    social_config = json.load(f)
                logger.info(f"Loaded social config from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load social config: {e}")

        social_model = social_config.get("model")

        # Load Channels Dynamically
        channel_manager.load_drivers_from_config(social_config)

        # Start Manager
        await channel_manager.start_all()

        # Start Brain
        # Allowlist: Env overrides/merges with Config?
        # Global Allowlist
        allowed_users = set(social_config.get("allowed_users", []))

        env_allowed = os.environ.get("ALLOWED_SOCIAL_USERS", "")
        if env_allowed:
            allowed_users.update(
                [u.strip() for u in env_allowed.split(",") if u.strip()]
            )

        # Per-Platform Allowlists
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
        # Expose social_brain to app state for dynamic updates
        # We need to access 'app' here. But 'app' is defined below.
        # Startup functions in Starlette unfortunately don't receive 'app' as arg usually?
        # Actually startup is just a coroutine.
        # But 'app' is global in this file.
        app.state.social_brain = social_brain

        await social_brain.start()

    except Exception as e:
        logger.error(f"Failed to initialize Social Messaging: {e}")


async def shutdown():
    """Cleanup services on application shutdown."""
    from suzent.memory.lifecycle import shutdown_memory_system

    logger.info("Application shutdown - cleaning up services")

    global social_brain, channel_manager

    if social_brain:
        await social_brain.stop()

    if channel_manager:
        await channel_manager.stop_all()

    await shutdown_memory_system()

    # Clean up browser session
    try:
        from suzent.tools.browsing_tool import BrowserSessionManager

        await BrowserSessionManager.get_instance().close_session()
    except Exception as e:
        logger.error(f"Error shutting down browser session: {e}")


# --- Application Setup ---
app = Starlette(
    debug=True,
    routes=[
        # Chat endpoints
        Route("/chat", chat, methods=["POST"]),
        Route("/chat/stop", stop_chat, methods=["POST"]),
        Route("/chats", get_chats, methods=["GET"]),
        Route("/chats", create_chat, methods=["POST"]),
        Route("/chats/{chat_id}", get_chat, methods=["GET"]),
        Route("/chats/{chat_id}", update_chat, methods=["PUT"]),
        Route("/chats/{chat_id}", delete_chat, methods=["DELETE"]),
        # Plan endpoints
        Route("/plans", get_plans, methods=["GET"]),
        Route("/plan", get_plan, methods=["GET"]),
        # Configuration endpoints
        Route("/config", get_config, methods=["GET"]),
        Route("/preferences", save_preferences, methods=["POST"]),
        Route("/config/api-keys", get_api_keys_status, methods=["GET"]),
        Route("/config/api-keys", save_api_keys, methods=["POST"]),
        Route(
            "/config/providers/{provider_id}/verify", verify_provider, methods=["POST"]
        ),
        Route("/config/embedding-models", get_embedding_models, methods=["GET"]),
        Route("/config/embedding-models", get_embedding_models, methods=["GET"]),
        Route("/config/social", get_social_config, methods=["GET"]),
        Route("/config/social", save_social_config, methods=["POST"]),
        # MCP server management endpoints
        Route("/mcp_servers", list_mcp_servers, methods=["GET"]),
        Route("/mcp_servers", add_mcp_server, methods=["POST"]),
        Route("/mcp_servers/remove", remove_mcp_server, methods=["POST"]),
        Route("/mcp_servers/enabled", set_mcp_server_enabled, methods=["POST"]),
        # Sandbox endpoints
        Route("/sandbox/files", list_sandbox_files, methods=["GET"]),
        Route("/sandbox/read_file", read_sandbox_file, methods=["GET"]),
        Route(
            "/sandbox/file", write_sandbox_file, methods=["POST", "PUT"]
        ),  # Support both for convenience
        Route("/sandbox/file", delete_sandbox_file, methods=["DELETE"]),
        Route("/sandbox/serve", serve_sandbox_file, methods=["GET"]),
        Route(
            "/sandbox/serve/{chat_id}/{file_path:path}",
            serve_sandbox_file_wildcard,
            methods=["GET"],
        ),
        Route("/sandbox/upload", upload_files, methods=["POST"]),
        # System endpoints
        Route("/system/files", list_host_files, methods=["GET"]),
        Route("/system/open_explorer", open_in_explorer, methods=["POST"]),
        # Memory endpoints
        Route("/memory/core", get_core_memory, methods=["GET"]),
        Route("/memory/core", update_core_memory_block, methods=["PUT"]),
        Route("/memory/archival", search_archival_memory, methods=["GET"]),
        Route(
            "/memory/archival/{memory_id}", delete_archival_memory, methods=["DELETE"]
        ),
        Route("/memory/stats", get_memory_stats, methods=["GET"]),
        # Skill endpoints
        Route("/skills", get_skills, methods=["GET"]),
        Route("/skills/reload", reload_skills, methods=["POST"]),
        Route("/skills/{skill_name}/toggle", toggle_skill, methods=["POST"]),
        # Browser WebSocket
        WebSocketRoute("/ws/browser", browser_websocket_endpoint),
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
    import uvicorn
    import os

    # Support dynamic port from environment (for Tauri)
    port = int(os.getenv("SUZENT_PORT", "8000"))
    host = os.getenv("SUZENT_HOST", "0.0.0.0")  # localhost only in bundled mode

    logger.info(f"Starting Suzent server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
