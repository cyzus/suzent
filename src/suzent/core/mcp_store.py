"""JSON-backed store for MCP server configurations.

Single source of truth at USER_CONFIG_DIR/mcp_servers.json.
Schema per entry:
  {
    "name": str,
    "type": "url" | "stdio",
    "url": str | null,
    "headers": dict | null,
    "command": str | null,
    "args": list | null,
    "env": dict | null,
    "enabled": bool
  }
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from suzent.config import USER_CONFIG_DIR

_MCP_FILE = USER_CONFIG_DIR / "mcp_servers.json"


def _path() -> Path:
    return _MCP_FILE


def _load() -> dict[str, dict[str, Any]]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save(servers: dict[str, dict[str, Any]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=p.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        json.dump(servers, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(p)


def get_all() -> list[dict[str, Any]]:
    return list(_load().values())


def get(name: str) -> dict[str, Any] | None:
    return _load().get(name)


def upsert(name: str, config: dict[str, Any], *, enabled: bool = True) -> None:
    servers = _load()
    existing = servers.get(name, {})
    entry: dict[str, Any] = {
        "name": name,
        "type": config.get("type", existing.get("type", "stdio")),
        "url": config.get("url", existing.get("url")),
        "headers": config.get("headers", existing.get("headers")),
        "command": config.get("command", existing.get("command")),
        "args": config.get("args", existing.get("args")),
        "env": config.get("env", existing.get("env")),
        "enabled": config.get(
            "enabled", enabled if "enabled" not in existing else existing["enabled"]
        ),
    }
    servers[name] = entry
    _save(servers)


def add(name: str, config: dict[str, Any], *, enabled: bool = True) -> bool:
    servers = _load()
    if name in servers:
        return False
    upsert(name, config, enabled=enabled)
    return True


def update(
    name: str, config: dict[str, Any] | None = None, enabled: bool | None = None
) -> bool:
    servers = _load()
    if name not in servers:
        return False
    entry = servers[name]
    if config:
        for key in ("type", "url", "headers", "command", "args", "env"):
            if key in config:
                entry[key] = config[key]
    if enabled is not None:
        entry["enabled"] = enabled
    servers[name] = entry
    _save(servers)
    return True


def remove(name: str) -> bool:
    servers = _load()
    if name not in servers:
        return False
    del servers[name]
    _save(servers)
    return True


def set_enabled(name: str, enabled: bool) -> bool:
    return update(name, enabled=enabled)


def as_agent_config() -> dict[str, Any]:
    """Return mcp_urls, mcp_stdio_params, mcp_headers, mcp_enabled dicts for agent_manager."""
    urls: dict[str, str] = {}
    stdio: dict[str, Any] = {}
    headers: dict[str, Any] = {}
    enabled: dict[str, bool] = {}

    for entry in get_all():
        name = entry["name"]
        enabled[name] = entry.get("enabled", False)
        if entry.get("type") == "url" and entry.get("url"):
            urls[name] = entry["url"]
            if entry.get("headers"):
                headers[name] = entry["headers"]
        elif entry.get("type") == "stdio" and entry.get("command"):
            stdio_entry: dict[str, Any] = {"command": entry["command"]}
            if entry.get("args"):
                stdio_entry["args"] = entry["args"]
            if entry.get("env"):
                stdio_entry["env"] = entry["env"]
            stdio[name] = stdio_entry

    return {
        "mcp_urls": urls,
        "mcp_stdio_params": stdio,
        "mcp_headers": headers,
        "mcp_enabled": enabled,
    }


def migrate_from_db() -> int:
    """One-time migration: import records from chats.db into mcp_servers.json.

    Only runs if the JSON file does not yet exist. Returns count migrated.
    """
    if _path().exists():
        return 0
    try:
        from suzent.database import get_database

        db = get_database()
        db_servers = db.get_mcp_servers()
        if not db_servers:
            return 0
        servers: dict[str, dict[str, Any]] = {}
        for s in db_servers:
            servers[s.name] = {
                "name": s.name,
                "type": s.type,
                "url": s.url,
                "headers": s.headers,
                "command": s.command,
                "args": s.args,
                "env": s.env,
                "enabled": s.enabled,
            }
        _save(servers)
        return len(servers)
    except Exception:
        return 0
