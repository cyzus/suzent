"""MCP server management API routes."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core import mcp_store


async def list_mcp_servers(request: Request) -> JSONResponse:
    cfg = mcp_store.as_agent_config()
    return JSONResponse(
        {
            "urls": cfg["mcp_urls"],
            "stdio": cfg["mcp_stdio_params"],
            "headers": cfg["mcp_headers"],
            "enabled": cfg["mcp_enabled"],
        }
    )


async def add_mcp_server(request: Request) -> JSONResponse:
    data = await request.json()
    name = data.get("name")
    url = data.get("url")
    headers = data.get("headers")
    stdio = data.get("stdio")

    if not name or (not url and not stdio):
        return JSONResponse({"error": "Missing name and url/stdio"}, status_code=400)

    config: dict = {}
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

    if mcp_store.add(name, config):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Server already exists"}, status_code=409)


async def remove_mcp_server(request: Request) -> JSONResponse:
    data = await request.json()
    name = data.get("name")
    if not name:
        return JSONResponse({"error": "Missing name"}, status_code=400)
    if mcp_store.remove(name):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


async def set_mcp_server_enabled(request: Request) -> JSONResponse:
    data = await request.json()
    name = data.get("name")
    enabled = data.get("enabled")
    if not name or not isinstance(enabled, bool):
        return JSONResponse({"error": "Invalid request"}, status_code=400)
    if mcp_store.set_enabled(name, enabled):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Server not found"}, status_code=404)
