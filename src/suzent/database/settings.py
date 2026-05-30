from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import select

from .models import (
    MCPServerModel,
    MemoryConfigModel,
    UserPreferencesModel,
    VolumeMetadataModel,
)


class SettingsOperationsMixin:
    def get_user_preferences(self) -> Optional[UserPreferencesModel]:
        """Get user preferences from the user config file."""
        from suzent.core.user_config import UserConfigStore

        prefs = UserConfigStore().get_user_preferences()
        if not prefs:
            return None
        return UserPreferencesModel(
            id=1,
            model=prefs.get("model"),
            agent=prefs.get("agent"),
            tools=prefs.get("tools"),
            memory_enabled=bool(prefs.get("memory_enabled", False)),
            sandbox_enabled=bool(prefs.get("sandbox_enabled", True)),
            sandbox_volumes=prefs.get("sandbox_volumes"),
            updated_at=self._parse_config_datetime(prefs.get("updated_at")),
        )

    def save_user_preferences(
        self,
        model: str = None,
        agent: str = None,
        tools: List[str] = None,
        memory_enabled: bool = None,
        sandbox_enabled: bool = None,
        sandbox_volumes: List[str] = None,
    ) -> bool:
        """Save user preferences to the user config file."""
        from suzent.core.user_config import UserConfigStore

        UserConfigStore().save_user_preferences(
            {
                "model": model,
                "agent": agent,
                "tools": tools,
                "memory_enabled": memory_enabled,
                "sandbox_enabled": sandbox_enabled,
                "sandbox_volumes": sandbox_volumes,
            }
        )
        return True

    # -------------------------------------------------------------------------
    # Volume Metadata Operations
    # -------------------------------------------------------------------------

    def get_volume_metadata(
        self, volumes: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Return cached metadata keyed by volume string."""
        with self._session() as session:
            statement = select(VolumeMetadataModel)
            if volumes is not None:
                if not volumes:
                    return {}
                statement = statement.where(VolumeMetadataModel.volume.in_(volumes))

            rows = session.exec(statement).all()
            return {
                row.volume: {
                    "volume": row.volume,
                    "host_path": row.host_path,
                    "mount_point": row.mount_point,
                    "kind": row.kind,
                    "exists": row.exists,
                    "is_git_repo": row.is_git_repo,
                    "git_root": row.git_root,
                    "status": row.status,
                    "error": row.error,
                    "checked_at": row.checked_at.isoformat()
                    if row.checked_at
                    else None,
                }
                for row in rows
            }

    def save_volume_metadata(self, items: List[Dict[str, Any]]) -> bool:
        """Upsert cached metadata for custom volumes."""
        now = datetime.now()

        def _apply_fields(row, item):
            row.host_path = item.get("host_path", "")
            row.mount_point = item.get("mount_point", "")
            row.kind = item.get("kind", "generic")
            row.exists = bool(item.get("exists", False))
            row.is_git_repo = item.get("is_git_repo")
            row.git_root = item.get("git_root")
            row.status = item.get("status", "unknown")
            row.error = item.get("error")
            row.checked_at = item.get("checked_at") or now

        with self._session() as session:
            for item in items:
                volume = item.get("volume")
                if not volume:
                    continue

                row = session.get(VolumeMetadataModel, volume)
                if row is None:
                    row = VolumeMetadataModel(volume=volume)
                _apply_fields(row, item)
                session.add(row)

            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Memory Configuration Operations
    # -------------------------------------------------------------------------

    def get_memory_config(self) -> Optional[MemoryConfigModel]:
        """Get memory system configuration from the user config file."""
        from suzent.core.user_config import UserConfigStore

        config = UserConfigStore().get_memory_config()
        if not config:
            return None
        return MemoryConfigModel(
            id=1,
            embedding_model=config.get("embedding_model"),
            extraction_model=config.get("extraction_model"),
            updated_at=self._parse_config_datetime(config.get("updated_at")),
        )

    def save_memory_config(
        self,
        embedding_model: str = None,
        extraction_model: str = None,
    ) -> bool:
        """Save memory system configuration to the user config file."""
        from suzent.core.user_config import UserConfigStore

        UserConfigStore().save_memory_config(
            {
                "embedding_model": embedding_model,
                "extraction_model": extraction_model,
            }
        )
        return True

    # -------------------------------------------------------------------------
    # MCP Server Operations
    # -------------------------------------------------------------------------

    def get_mcp_servers(self) -> List[MCPServerModel]:
        """Get all MCP servers from the database."""
        with self._session() as session:
            statement = select(MCPServerModel)
            servers = session.exec(statement).all()
            return servers

    def add_mcp_server(
        self,
        name: str,
        config: Dict[str, Any],
        enabled: bool = True,
    ) -> bool:
        """Add a new MCP server configuration."""
        now = datetime.now()
        with self._session() as session:
            if session.get(MCPServerModel, name):
                return False

            server = MCPServerModel(
                name=name,
                type=config.get("type", "stdio"),
                url=config.get("url"),
                headers=config.get("headers"),
                command=config.get("command"),
                args=config.get("args"),
                env=config.get("env"),
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(server)
            session.commit()
            return True

    def update_mcp_server(
        self, name: str, config: Dict[str, Any] = None, enabled: bool = None
    ) -> bool:
        """Update an existing MCP server configuration."""
        with self._session() as session:
            server = session.get(MCPServerModel, name)
            if not server:
                return False

            if config:
                if "type" in config:
                    server.type = config["type"]
                if "url" in config:
                    server.url = config["url"]
                if "headers" in config:
                    server.headers = config["headers"]
                if "command" in config:
                    server.command = config["command"]
                if "args" in config:
                    server.args = config["args"]
                if "env" in config:
                    server.env = config["env"]

            if enabled is not None:
                server.enabled = enabled

            server.updated_at = datetime.now()
            session.add(server)
            session.commit()
            return True

    def remove_mcp_server(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        with self._session() as session:
            server = session.get(MCPServerModel, name)
            if not server:
                return False
            session.delete(server)
            session.commit()
            return True

    def set_mcp_server_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable an MCP server."""
        return self.update_mcp_server(name, enabled=enabled)

    # -------------------------------------------------------------------------
    # Cron Job Operations
    # -------------------------------------------------------------------------

    def get_api_keys(self) -> Dict[str, str]:
        """Get non-secret config blobs formerly stored with API keys."""
        from suzent.core.user_config import UserConfigStore

        return UserConfigStore().get_config_blobs()

    def get_api_key(self, key: str) -> Optional[str]:
        """Get a config blob or secret by key name."""
        if key.startswith("_"):
            from suzent.core.user_config import UserConfigStore

            return UserConfigStore().get_config_blob(key)

        from suzent.core.secrets import get_secret_manager

        return get_secret_manager().get(key)

    def save_api_key(self, key: str, value: str) -> bool:
        """Save a config blob or secret outside the runtime database."""
        if key.startswith("_"):
            from suzent.core.user_config import UserConfigStore

            UserConfigStore().save_config_blob(key, value)
        else:
            from suzent.core.secrets import get_secret_manager

            get_secret_manager().set_backend_only(key, value)
        return True

    def delete_api_key(self, key: str) -> bool:
        """Delete a config blob or secret outside the runtime database."""
        if key.startswith("_"):
            from suzent.core.user_config import UserConfigStore

            UserConfigStore().delete_config_blob(key)
        else:
            from suzent.core.secrets import get_secret_manager

            get_secret_manager().delete(key)
        return True
