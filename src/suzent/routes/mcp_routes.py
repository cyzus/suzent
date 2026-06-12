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

    if not mcp_store.add(name, config):
        return JSONResponse({"error": "Server already exists"}, status_code=409)

    # Probe the new server so the user learns immediately if it is unreachable.
    # It is saved regardless; the probe result is advisory. Use a short timeout
    # here so adding stays responsive — a cold stdio package that needs to install
    # will report a timeout, and the user can re-run the explicit "test" (which
    # allows the full startup window) once it is cached.
    from suzent.agent_manager import probe_mcp_server

    probe = await probe_mcp_server(mcp_store.get(name) or config, timeout=15.0)
    return JSONResponse({"success": True, "probe": probe})


async def test_mcp_server(request: Request) -> JSONResponse:
    """Connect to a configured server and report reachability + tool count."""
    data = await request.json()
    name = data.get("name")
    if not name:
        return JSONResponse({"error": "Missing name"}, status_code=400)
    entry = mcp_store.get(name)
    if not entry:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    from suzent.agent_manager import probe_mcp_server

    result = await probe_mcp_server(entry)
    return JSONResponse(result)


async def remove_mcp_server(request: Request) -> JSONResponse:
    data = await request.json()
    name = data.get("name")
    if not name:
        return JSONResponse({"error": "Missing name"}, status_code=400)
    if mcp_store.remove(name):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


async def update_mcp_server(request: Request) -> JSONResponse:
    """Update an existing server's transport/config, preserving its enabled state."""
    data = await request.json()
    name = data.get("name")
    url = data.get("url")
    headers = data.get("headers")
    stdio = data.get("stdio")

    if not name:
        return JSONResponse({"error": "Missing name"}, status_code=400)
    if not url and not stdio:
        return JSONResponse({"error": "Missing url/stdio"}, status_code=400)

    # Include every transport field (nulling the unused one) so switching
    # transports doesn't leave stale command/url data behind.
    if url:
        config = {
            "type": "url",
            "url": url,
            "headers": headers,
            "command": None,
            "args": None,
            "env": None,
        }
    else:
        config = {
            "type": "stdio",
            "command": stdio.get("command"),
            "args": stdio.get("args"),
            "env": stdio.get("env"),
            "url": None,
            "headers": None,
        }

    if not mcp_store.update(name, config):
        return JSONResponse({"error": "Server not found"}, status_code=404)

    # Re-probe so the edited config's reachability is reported back immediately.
    from suzent.agent_manager import probe_mcp_server

    probe = await probe_mcp_server(mcp_store.get(name), timeout=15.0)
    return JSONResponse({"success": True, "probe": probe})


async def set_mcp_server_enabled(request: Request) -> JSONResponse:
    data = await request.json()
    name = data.get("name")
    enabled = data.get("enabled")
    if not name or not isinstance(enabled, bool):
        return JSONResponse({"error": "Invalid request"}, status_code=400)
    if mcp_store.set_enabled(name, enabled):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Server not found"}, status_code=404)
