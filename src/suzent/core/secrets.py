"""Secure credential storage outside the runtime SQLite database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional, Protocol

from suzent.logger import get_logger

logger = get_logger(__name__)

_SERVICE_NAME = "suzent"


class SecretBackend(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def list_keys(self) -> list[str]: ...


class KeyringBackend:
    def __init__(self) -> None:
        try:
            import keyring as _kr
            from keyring.backends import fail as _kr_fail

            self._kr = _kr
            active = _kr.get_keyring()

            # ``get_keyring()`` succeeds even when no real backend is installed:
            # it returns a fail/chainer backend (priority <= 0) that only raises
            # ``NoKeyringError`` later, at get/set time. Reject those up front so
            # the factory can fall back to encrypted SQLite instead of blowing up
            # on the first credential operation (e.g. on headless CI/Linux).
            if (
                isinstance(active, _kr_fail.Keyring)
                or getattr(active, "priority", 0) <= 0
            ):
                raise RuntimeError(
                    f"no usable keyring backend (resolved {active.__class__.__name__})"
                )

            logger.info(
                "SecretBackend: using OS keyring ({})",
                active.__class__.__name__,
            )
        except Exception as exc:
            raise RuntimeError(
                f"OS keyring is not available: {exc}. "
                "Set SUZENT_SECRET_BACKEND=encrypted_sqlite to use encrypted local storage."
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
        self._write_keys(keys)

    def _untrack_key(self, key: str) -> None:
        keys = set(self.list_keys())
        keys.discard(key)
        self._write_keys(keys)

    def _write_keys(self, keys: set[str]) -> None:
        if keys:
            self._kr.set_password(
                _SERVICE_NAME, self._meta_key, "\x00".join(sorted(keys))
            )
            return

        try:
            self._kr.delete_password(_SERVICE_NAME, self._meta_key)
        except Exception:
            pass


class EncryptedSQLiteBackend:
    def __init__(self, path: Path | None = None) -> None:
        from cryptography.fernet import Fernet
        from suzent.config import DATA_DIR

        override = os.environ.get("SUZENT_SECRET_DB_PATH")
        self.path = path or (
            Path(override).expanduser().resolve()
            if override
            else DATA_DIR / "secrets.db"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._resolve_key())
        self._init_db()
        logger.info("SecretBackend: using encrypted SQLite ({})", self.path)

    def get(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT value FROM secrets WHERE key = ?", (key,)
            ).fetchone()
        try:
            return self._fernet.decrypt(row[0].encode()).decode() if row else None
        except Exception:
            logger.warning("Failed to decrypt secret '{}'", key)
            return None

    def set(self, key: str, value: str) -> None:
        encrypted = self._fernet.encrypt(value.encode()).decode()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO secrets(key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, encrypted),
            )
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def delete(self, key: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM secrets WHERE key = ?", (key,))

    def list_keys(self) -> list[str]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("SELECT key FROM secrets ORDER BY key").fetchall()
        return [row[0] for row in rows]

    def _resolve_key(self) -> bytes:
        from cryptography.fernet import Fernet
        from suzent.config import DATA_DIR

        if env_key := os.environ.get("SUZENT_SECRET_KEY"):
            return env_key.encode()

        key_file = DATA_DIR / ".secret_key"
        key_file.parent.mkdir(parents=True, exist_ok=True)
        if key_file.exists():
            return key_file.read_bytes().strip()

        key = Fernet.generate_key()
        key_file.write_bytes(key)
        try:
            key_file.chmod(0o600)
        except OSError:
            pass
        return key

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS secrets (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )


class SecretManager:
    def __init__(self, backend: SecretBackend) -> None:
        self._backend = backend

    @property
    def backend_name(self) -> str:
        return self._backend.__class__.__name__

    def get(self, key: str) -> Optional[str]:
        return self._backend.get(key) or os.environ.get(key)

    def set(self, key: str, value: str) -> None:
        self._backend.set(key, value)
        os.environ[key] = value

    def set_backend_only(self, key: str, value: str) -> None:
        self._backend.set(key, value)

    def delete(self, key: str) -> None:
        self._backend.delete(key)
        os.environ.pop(key, None)

    def list_keys(self) -> list[str]:
        return self._backend.list_keys()

    def has_backend_value(self, key: str) -> bool:
        return bool(self._backend.get(key))

    def get_source(self, key: str) -> str:
        if self.has_backend_value(key):
            return self.backend_name.lower()
        if os.environ.get(key):
            return "env"
        return "unset"

    def inject_all_to_env(self, *, overwrite: bool = True) -> int:
        """Load stored secrets into os.environ.

        By default the durable backend (keyring / encrypted DB — what the UI
        writes) is **authoritative** and overwrites any pre-existing env value:
        a stale ambient ``GEMINI_API_KEY`` (from a login-shell export, an old
        value, etc.) would otherwise shadow the key the user just saved and cause
        auth failures. Pass ``overwrite=False`` to keep existing env values.
        """
        count = 0
        for key in self.list_keys():
            val = self._backend.get(key)
            if not val:
                continue
            if overwrite or key not in os.environ:
                if os.environ.get(key) != val:
                    os.environ[key] = val
                    count += 1
        return count


_instance: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    global _instance
    if _instance is not None:
        return _instance

    backend_name = os.environ.get("SUZENT_SECRET_BACKEND", "keyring").lower()

    if backend_name in {"encrypted_sqlite", "encrypted_db", "sqlite"}:
        backend: SecretBackend = EncryptedSQLiteBackend()
    elif backend_name in {"dotenv", "env"}:
        logger.warning(
            "Dotenv secret storage is no longer used; using encrypted SQLite instead"
        )
        backend = EncryptedSQLiteBackend()
    else:
        try:
            backend = KeyringBackend()
        except RuntimeError:
            logger.warning(
                "OS keyring unavailable, falling back to encrypted SQLite secret backend"
            )
            backend = EncryptedSQLiteBackend()

    _instance = SecretManager(backend)
    return _instance
