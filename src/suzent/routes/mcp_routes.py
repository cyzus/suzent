"""
MCP server management API routes.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse
from suzent.config import CONFIG
from suzent.database import get_database


def get_mcp_servers_merged() -> dict:
    """
    Get MCP servers merged from database and config file defaults.
    Database servers take precedence.
    Config supports both simple format: {"name": "url"} and nested: {"name": {"url": "...", "headers": {...}}}
    """
    db = get_database()
    db_servers = db.get_mcp_servers()

    # Start with config defaults (servers default to DISABLED until user explicitly enables them)
    all_config_names = set(CONFIG.mcp_urls.keys()) | set(CONFIG.mcp_stdio_params.keys())

    # Parse config mcp_urls - supports both simple and nested formats
    config_urls = {}
    config_headers = {}
    for name, value in CONFIG.mcp_urls.items():
        if isinstance(value, str):
            # Simple format: "name": "url"
            config_urls[name] = value
        elif isinstance(value, dict):
            # Nested format: "name": {"url": "...", "headers": {...}}
            config_urls[name] = value.get("url", "")
            if value.get("headers"):
                config_headers[name] = value["headers"]

    merged = {
        "urls": config_urls,
        "stdio": dict(CONFIG.mcp_stdio_params),
        "headers": config_headers,
        "enabled": {name: False for name in all_config_names},
    }

    # Merge in database servers (overrides config)
    for server in db_servers:
        merged["enabled"][server.name] = server.enabled

        if server.type == "url" and server.url:
            merged["urls"][server.name] = server.url
            if server.headers:
                merged["headers"][server.name] = server.headers
        elif server.type == "stdio" and server.command:
            stdio_config = {"command": server.command}
            if server.args:
                stdio_config["args"] = server.args
            if server.env:
                stdio_config["env"] = server.env
            merged["stdio"][server.name] = stdio_config

    return merged


async def list_mcp_servers(request: Request) -> JSONResponse:
    """
    List all MCP servers (URLs and stdio params).
    """
    servers = get_mcp_servers_merged()
    return JSONResponse(
        {
            "urls": servers["urls"],
            "stdio": servers["stdio"],
            "headers": servers.get("headers", {}),
            "enabled": servers["enabled"],
        }
    )


async def add_mcp_server(request: Request) -> JSONResponse:
    """
    Add a new MCP server (URL or stdio).
    Body: {"name": str, "url": str, "headers": dict} or {"name": str, "stdio": dict}
    """
    data = await request.json()
    name = data.get("name")
    url = data.get("url")
    headers = data.get("headers")
    stdio = data.get("stdio")

    if not name or (not url and not stdio):
        return JSONResponse({"error": "Missing name and url/stdio"}, status_code=400)

    config = {}
    if url:
        config = {"type": "url", "url": url}
        if headers:
            config["headers"] = headers
    elif stdio:
        config = {
            "type": "stdio",
            "command": stdio.get("command"),
            "args": stdio.get("args"),
            "env": stdio.get("env"),
        }

    db = get_database()
    success = db.add_mcp_server(name, config=config)

    if success:
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Failed to add server"}, status_code=500)


async def remove_mcp_server(request: Request) -> JSONResponse:
    """
    Remove an MCP server by name (URL or stdio).
    Body: {"name": str}
    """
    data = await request.json()
    name = data.get("name")

    if not name:
        return JSONResponse({"error": "Missing name"}, status_code=400)

    db = get_database()
    success = db.remove_mcp_server(name)

    if success:
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


async def set_mcp_server_enabled(request: Request) -> JSONResponse:
    """
    Enable or disable an MCP server (URL or stdio).
    Body: {"name": str, "enabled": bool}
    """
    data = await request.json()
    name = data.get("name")
    enabled = data.get("enabled")

    if not name or not isinstance(enabled, bool):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    db = get_database()
    success = db.set_mcp_server_enabled(name, enabled)

    # If server not found in database, check if it's in config and add it first
    if not success:
        config = {}
        # Check if server exists in config
        if name in CONFIG.mcp_urls:
            config = {"type": "url", "url": CONFIG.mcp_urls[name]}
        elif name in CONFIG.mcp_stdio_params:
            stdio_params = CONFIG.mcp_stdio_params[name]
            config = {
                "type": "stdio",
                "command": stdio_params.get("command"),
                "args": stdio_params.get("args"),
                "env": stdio_params.get("env"),
            }

        if config:
            # Add config server to database, then set enabled state
            db.add_mcp_server(name, config=config)
            success = db.set_mcp_server_enabled(name, enabled)

    if success:
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Server not found"}, status_code=404)
