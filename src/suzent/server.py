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

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route

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

# Load environment variables
load_dotenv()



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
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)