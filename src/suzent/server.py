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
from starlette.routing import Route

from suzent.logger import setup_logging, get_logger
from suzent.routes.chat_routes import (
    chat,
    stop_chat,
    get_chats,
    get_chat,
    create_chat,
    update_chat,
    delete_chat,
)
from suzent.routes.plan_routes import get_plans, get_plan

from suzent.routes.config_routes import get_config
from suzent.routes.mcp_routes import (
    list_mcp_servers, add_mcp_server, remove_mcp_server, set_mcp_server_enabled
)

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
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE")  # Optional: set LOG_FILE=/path/to/suzent.log
setup_logging(level=log_level, log_file=log_file)

logger = get_logger(__name__)


async def startup():
    """Initialize services on application startup."""
    from suzent.agent_manager import init_memory_system
    logger.info("Application startup - initializing services")
    await init_memory_system()


async def shutdown():
    """Cleanup services on application shutdown."""
    from suzent.agent_manager import shutdown_memory_system
    logger.info("Application shutdown - cleaning up services")
    await shutdown_memory_system()


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
        # Configuration endpoint
        Route("/config", get_config, methods=["GET"]),
        # MCP server management endpoints
        Route("/mcp_servers", list_mcp_servers, methods=["GET"]),
        Route("/mcp_servers", add_mcp_server, methods=["POST"]),
        Route("/mcp_servers/remove", remove_mcp_server, methods=["POST"]),
        Route("/mcp_servers/enabled", set_mcp_server_enabled, methods=["POST"]),
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

    logger.info("Starting Suzent server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)