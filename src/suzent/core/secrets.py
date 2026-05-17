"""Secure credential storage outside the runtime SQLite database."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_SERVICE_NAME = "suzent"


class SecretBackend(ABC):
    """Protocol for pluggable secret storage."""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Retrieve a secret by key. Returns None if not stored."""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Store or overwrite a secret."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a secret. No-op if it does not exist."""

    @abstractmethod
    def list_keys(self) -> list[str]:
        """List all stored secret keys."""

    @property
    def backend_name(self) -> str:
        return self.__class__.__name__


class KeyringBackend(SecretBackend):
    """Stores secrets in the OS keyring."""

    def __init__(self) -> None:
        try:
            import keyring as _kr

            self._kr = _kr
            _kr.get_keyring()
            logger.info(
                "SecretBackend: using OS keyring ({})",
                _kr.get_keyring().__class__.__name__,
            )
        except Exception as exc:
            raise RuntimeError(
                f"OS keyring is not available: {exc}. "
                "Set SUZENT_SECRET_BACKEND=dotenv to use a .env file instead."
            ) from exc

        self._meta_key = "__suzent_keys__"

    def get(self, key: str) -> Optional[str]:
        return self._kr.get_password(_SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        self._kr.set_password(_SERVICE_NAME, key, value)
        self._track_key(key)

    def delete(self, key: str) -> None:
        try:
            self._kr.delete_password(_SERVICE_NAME, key)
        except self._kr.errors.PasswordDeleteError:
            pass
        self._untrack_key(key)

    def list_keys(self) -> list[str]:
        raw = self._kr.get_password(_SERVICE_NAME, self._meta_key)
        if not raw:
            return []
        return [key for key in raw.split("\x00") if key]

    def _track_key(self, key: str) -> None:
        keys = set(self.list_keys())
        keys.add(key)
        self._kr.set_password(_SERVICE_NAME, self._meta_key, "\x00".join(sorted(keys)))

    def _untrack_key(self, key: str) -> None:
        keys = set(self.list_keys())
        keys.discard(key)
        if keys:
            self._kr.set_password(
                _SERVICE_NAME, self._meta_key, "\x00".join(sorted(keys))
            )
            return

        try:
            self._kr.delete_password(_SERVICE_NAME, self._meta_key)
        except Exception:
            pass


class DotEnvBackend(SecretBackend):
    """Stores secrets in Suzent's user-scoped .env file."""

    def __init__(self, path: Path | None = None) -> None:
        from suzent.config import DATA_DIR

        override = os.environ.get("SUZENT_ENV_FILE")
        self.path = path or (
            Path(override).expanduser().resolve() if override else DATA_DIR / ".env"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._meta_key = "SUZENT_SECRET_KEYS"
        logger.info("SecretBackend: using dotenv file ({})", self.path)

    def get(self, key: str) -> Optional[str]:
        from dotenv import dotenv_values

        value = dotenv_values(self.path).get(key)
        return str(value) if value else None

    def set(self, key: str, value: str) -> None:
        from dotenv import set_key

        self.path.touch(exist_ok=True)
        set_key(self.path, key, value)
        self._track_key(key)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def delete(self, key: str) -> None:
        from dotenv import unset_key

        if self.path.exists():
            unset_key(self.path, key)
        self._untrack_key(key)

    def list_keys(self) -> list[str]:
        from dotenv import dotenv_values

        values = dotenv_values(self.path)
        tracked = values.get(self._meta_key)
        if tracked:
            return [key for key in str(tracked).split(",") if key]
        return [key for key in values if key and key != self._meta_key]

    def _track_key(self, key: str) -> None:
        keys = set(self.list_keys())
        keys.add(key)
        self._write_tracked_keys(keys)

    def _untrack_key(self, key: str) -> None:
        keys = set(self.list_keys())
        keys.discard(key)
        self._write_tracked_keys(keys)

    def _write_tracked_keys(self, keys: set[str]) -> None:
        from dotenv import set_key, unset_key

        if keys:
            set_key(self.path, self._meta_key, ",".join(sorted(keys)))
        elif self.path.exists():
            unset_key(self.path, self._meta_key)


class SecretManager:
    """Unified secret access with backend storage plus env fallback."""

    def __init__(self, backend: SecretBackend) -> None:
        self._backend = backend

    @property
    def backend_name(self) -> str:
        return self._backend.backend_name

    def get(self, key: str) -> Optional[str]:
        val = self._backend.get(key)
        if val:
            return val
        return os.environ.get(key)

    def set(self, key: str, value: str) -> None:
        self._backend.set(key, value)
        os.environ[key] = value

    def delete(self, key: str) -> None:
        self._backend.delete(key)
        os.environ.pop(key, None)

    def list_keys(self) -> list[str]:
        return self._backend.list_keys()

    def get_source(self, key: str) -> str:
        if self._backend.get(key):
            return self._backend.backend_name.lower()
        if os.environ.get(key):
            return "env"
        return "unset"

    def inject_all_to_env(self) -> int:
        count = 0
        for key in self.list_keys():
            val = self._backend.get(key)
            if val and key not in os.environ:
                os.environ[key] = val
                count += 1
        return count


_instance: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get or create the global SecretManager singleton."""
    global _instance
    if _instance is not None:
        return _instance

    backend_name = os.environ.get("SUZENT_SECRET_BACKEND", "keyring").lower()

    if backend_name in {"dotenv", "env"}:
        backend: SecretBackend = DotEnvBackend()
    else:
        try:
            backend = KeyringBackend()
        except RuntimeError:
            logger.warning(
                "OS keyring unavailable, falling back to dotenv secret backend"
            )
            backend = DotEnvBackend()

    _instance = SecretManager(backend)
    return _instance
