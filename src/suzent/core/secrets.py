"""
Secure credential storage — dual-layer strategy.

Provides a unified ``SecretManager`` that abstracts away the underlying
secret backend.  Two backends are supported:

1. **KeyringBackend** (default on desktop) — uses the OS credential store
   (Windows Credential Locker, macOS Keychain, GNOME/KDE keyring).
2. **EncryptedDBBackend** — encrypts secrets with Fernet (AES-128-CBC)
   before storing in SQLite.  Suitable for headless / Docker environments.

Backend selection is driven by the ``SUZENT_SECRET_BACKEND`` env var:
  - ``"keyring"`` (default) — OS keyring
  - ``"encrypted_db"`` — Fernet-encrypted SQLite column

Environment variables (``os.environ``) are always checked as a final
fallback, so CI / Docker users can still inject secrets the traditional way.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_SERVICE_NAME = "suzent"


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------


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
        """Remove a secret. No-op if it doesn't exist."""

    @abstractmethod
    def list_keys(self) -> list[str]:
        """List all stored secret keys."""

    @property
    def backend_name(self) -> str:
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# Keyring backend (desktop)
# ---------------------------------------------------------------------------


class KeyringBackend(SecretBackend):
    """Stores secrets in the OS keyring (Windows Credential Locker, macOS Keychain, etc.)."""

    def __init__(self) -> None:
        try:
            import keyring as _kr

            self._kr = _kr
            # Quick sanity check — will raise if no suitable backend
            _kr.get_keyring()
            logger.info(
                "SecretBackend: using OS keyring ({})",
                _kr.get_keyring().__class__.__name__,
            )
        except Exception as exc:
            raise RuntimeError(
                f"OS keyring is not available: {exc}. "
                f"Set SUZENT_SECRET_BACKEND=encrypted_db to use encrypted DB instead."
            ) from exc

        # Track stored keys in a meta-entry so list_keys() works
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
        return [k for k in raw.split("\x00") if k]

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
        else:
            try:
                self._kr.delete_password(_SERVICE_NAME, self._meta_key)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Encrypted DB backend (headless / Docker)
# ---------------------------------------------------------------------------


class EncryptedDBBackend(SecretBackend):
    """Stores secrets in the existing SQLite DB, encrypted with Fernet.

    The encryption key is read from ``SUZENT_SECRET_KEY`` env var.
    If not set, a key is auto-generated and stored in the project's
    ``data/.secret_key`` file (chmod 600).
    """

    def __init__(self) -> None:
        from cryptography.fernet import Fernet

        secret_key = self._resolve_key()
        self._fernet = Fernet(secret_key)
        logger.info("SecretBackend: using encrypted DB (Fernet)")

    def _resolve_key(self) -> bytes:
        """Resolve or generate the Fernet encryption key."""
        from cryptography.fernet import Fernet

        env_key = os.environ.get("SUZENT_SECRET_KEY")
        if env_key:
            return env_key.encode()

        # Auto-generate and persist
        from suzent.config import PROJECT_DIR

        key_file = PROJECT_DIR / "data" / ".secret_key"
        key_file.parent.mkdir(parents=True, exist_ok=True)

        if key_file.exists():
            return key_file.read_bytes().strip()

        new_key = Fernet.generate_key()
        key_file.write_bytes(new_key)
        try:
            key_file.chmod(0o600)
        except OSError:
            pass  # Windows doesn't support chmod
        logger.info("Generated new secret key at {}", key_file)
        return new_key

    def _get_db(self):
        from suzent.database import get_database

        return get_database()

    def get(self, key: str) -> Optional[str]:
        db = self._get_db()
        encrypted = db.get_api_key(key)
        if not encrypted:
            return None
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            # Maybe it's a legacy unencrypted value
            logger.warning("Failed to decrypt key '{}', returning raw value", key)
            return encrypted

    def set(self, key: str, value: str) -> None:
        encrypted = self._fernet.encrypt(value.encode()).decode()
        db = self._get_db()
        db.save_api_key(key, encrypted)

    def delete(self, key: str) -> None:
        db = self._get_db()
        db.delete_api_key(key)

    def list_keys(self) -> list[str]:
        db = self._get_db()
        api_keys = db.get_api_keys() or {}
        return [k for k in api_keys if not k.startswith("_")]


# ---------------------------------------------------------------------------
# SecretManager — unified facade
# ---------------------------------------------------------------------------


class SecretManager:
    """Unified secret access with backend abstraction + env fallback.

    Resolution order for ``get()``:
        1. Backend (keyring or encrypted DB)
        2. ``os.environ``

    Usage::

        secrets = get_secret_manager()
        api_key = secrets.get("OPENAI_API_KEY")
        secrets.set("OPENAI_API_KEY", "sk-...")
    """

    def __init__(self, backend: SecretBackend) -> None:
        self._backend = backend

    @property
    def backend_name(self) -> str:
        return self._backend.backend_name

    def get(self, key: str) -> Optional[str]:
        """Get a secret, checking backend first then environment."""
        val = self._backend.get(key)
        if val:
            return val
        return os.environ.get(key)

    def set(self, key: str, value: str) -> None:
        """Store a secret in the backend and inject into runtime environment."""
        self._backend.set(key, value)
        os.environ[key] = value

    def delete(self, key: str) -> None:
        """Remove a secret from the backend and environment."""
        self._backend.delete(key)
        os.environ.pop(key, None)

    def list_keys(self) -> list[str]:
        """List all stored secret keys."""
        return self._backend.list_keys()

    def get_source(self, key: str) -> str:
        """Identify where a key is stored: 'backend', 'env', or 'unset'."""
        if self._backend.get(key):
            return self._backend.backend_name.lower()
        if os.environ.get(key):
            return "env"
        return "unset"

    def inject_all_to_env(self) -> int:
        """Load all stored secrets into os.environ. Returns count loaded."""
        count = 0
        for key in self.list_keys():
            val = self._backend.get(key)
            if val and key not in os.environ:
                os.environ[key] = val
                count += 1
        return count


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get or create the global SecretManager singleton."""
    global _instance
    if _instance is not None:
        return _instance

    backend_name = os.environ.get("SUZENT_SECRET_BACKEND", "keyring").lower()

    if backend_name == "encrypted_db":
        backend: SecretBackend = EncryptedDBBackend()
    else:
        try:
            backend = KeyringBackend()
        except RuntimeError:
            logger.warning(
                "OS keyring unavailable, falling back to encrypted DB backend"
            )
            backend = EncryptedDBBackend()

    _instance = SecretManager(backend)
    return _instance
