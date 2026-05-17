"""User-scoped configuration stored outside the runtime SQLite database."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from suzent.config import DATA_DIR


def get_user_config_path() -> Path:
    """Return the path for user preferences and provider capability config."""
    override = os.getenv("SUZENT_USER_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return DATA_DIR / "config.yaml"


class UserConfigStore:
    """Plain-text YAML store for static user configuration."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_user_config_path()

    def get_user_preferences(self) -> dict[str, Any] | None:
        return self._get_section("user_preferences")

    def save_user_preferences(self, updates: dict[str, Any]) -> None:
        self._update_section("user_preferences", updates)

    def get_memory_config(self) -> dict[str, Any] | None:
        return self._get_section("memory_config")

    def save_memory_config(self, updates: dict[str, Any]) -> None:
        self._update_section("memory_config", updates)

    def get_config_blobs(self) -> dict[str, str]:
        blobs = self._get_section("config_blobs")
        if not isinstance(blobs, dict):
            return {}
        return {str(key): str(value) for key, value in blobs.items()}

    def get_config_blob(self, key: str) -> str | None:
        return self.get_config_blobs().get(key)

    def save_config_blob(self, key: str, value: str) -> None:
        data = self._load()
        blobs = data.setdefault("config_blobs", {})
        if not isinstance(blobs, dict):
            blobs = {}
            data["config_blobs"] = blobs
        blobs[key] = value
        self._save(data)

    def delete_config_blob(self, key: str) -> None:
        data = self._load()
        blobs = data.get("config_blobs")
        if isinstance(blobs, dict) and key in blobs:
            blobs.pop(key)
            self._save(data)

    def _get_section(self, section: str) -> dict[str, Any] | None:
        value = self._load().get(section)
        return value if isinstance(value, dict) else None

    def _update_section(self, section: str, updates: dict[str, Any]) -> None:
        data = self._load()
        current = data.setdefault(section, {})
        if not isinstance(current, dict):
            current = {}
            data[section] = current

        for key, value in updates.items():
            if value is not None:
                current[key] = value
        current["updated_at"] = datetime.now().isoformat()
        self._save(data)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}

        with self.path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                yaml.safe_dump(data, file, sort_keys=False, allow_unicode=False)
            tmp_path.replace(self.path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
