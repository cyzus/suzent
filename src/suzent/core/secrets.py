"""Secure credential storage outside the runtime SQLite database."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Protocol

from suzent.logger import get_logger

logger = get_logger(__name__)

_SERVICE_NAME = "suzent"

#: Secrets Suzent reads itself and never exports to the environment, where
#: commands the agent runs would inherit them: MCP OAuth tokens and the
#: tokens plugin integrations are connected with, and the relay's
#: registration key and channel tokens, and secrets plugins keep through
#: ``ctx.secrets``, such as mailbox passwords.
PRIVATE_KEY_PREFIXES = (
    "SUZENT_MCP_OAUTH::",
    "SUZENT_MCP_TOKEN::",
    "SUZENT_RELAY::",
    "SUZENT_PLUGIN::",
)


def is_private_key(key: str) -> bool:
    return key.startswith(PRIVATE_KEY_PREFIXES)


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
        # macOS asks before each read of an item another program stored (an
        # older install's Python, say) unless the user picks Always Allow, and
        # settings pages read every key on each refresh: read each item once.
        self._cache: dict[str, Optional[str]] = {}

    def get(self, key: str) -> Optional[str]:
        if key in self._cache:
            return self._cache[key]
        try:
            value = self._kr.get_password(_SERVICE_NAME, key)
        except self._kr.errors.KeyringError as exc:
            logger.warning("Could not read '{}' from the OS keyring: {}", key, exc)
            value = None
        self._cache[key] = value
        return value

    def set(self, key: str, value: str) -> None:
        self._kr.set_password(_SERVICE_NAME, key, value)
        self._cache[key] = value
        self._track_key(key)

    def delete(self, key: str) -> None:
        try:
            self._kr.delete_password(_SERVICE_NAME, key)
        except self._kr.errors.PasswordDeleteError:
            pass
        self._cache[key] = None
        self._untrack_key(key)

    def list_keys(self) -> list[str]:
        raw = self.get(self._meta_key)
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
            joined = "\x00".join(sorted(keys))
            self._kr.set_password(_SERVICE_NAME, self._meta_key, joined)
            self._cache[self._meta_key] = joined
            return

        try:
            self._kr.delete_password(_SERVICE_NAME, self._meta_key)
        except Exception:
            pass
        self._cache[self._meta_key] = None


class KeychainVaultBackend(KeyringBackend):
    """All secrets in one macOS keychain item.

    macOS asks for the login password before a program reads an item that a
    different program stored, once per item. Keeping every secret in a single
    item means at most one prompt when the app's identity changes (a new
    unsigned build, or the move from a source install's Python), instead of
    one per key. The first run copies the per-key items older versions wrote,
    and leaves them in place for those versions.
    """

    _VAULT_KEY = "__suzent_vault__"

    def __init__(self) -> None:
        super().__init__()
        self._vault: dict[str, str] | None = None
        self._refused = False

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key)

    def set(self, key: str, value: str) -> None:
        self._fresh()[key] = value
        self._save()

    def delete(self, key: str) -> None:
        if self._fresh().pop(key, None) is not None:
            self._save()

    def _fresh(self) -> dict[str, str]:
        """The vault as stored now, so a write keeps other processes' changes."""
        self._vault = None
        self._refused = False
        return self._load()

    def list_keys(self) -> list[str]:
        return sorted(self._load())

    def _load(self) -> dict[str, str]:
        if self._vault is not None:
            return self._vault
        raw = self._read(self._VAULT_KEY)
        if self._refused:
            # The user said no; asking for every older item would only add prompts.
            self._vault = {}
            return self._vault
        if raw is not None:
            try:
                self._vault = {str(k): str(v) for k, v in json.loads(raw).items()}
                return self._vault
            except (ValueError, AttributeError):
                logger.warning("The Suzent keychain item is unreadable; rebuilding it")
        self._vault, complete = self._read_per_key_items()
        # A refused read would drop that key for good once the vault exists;
        # keep it in memory and copy again next run instead.
        if self._vault and complete:
            self._save()
        return self._vault

    def _read_per_key_items(self) -> tuple[dict[str, str], bool]:
        names = self._read(self._meta_key)
        if names is None:
            return {}, not self._refused
        vault: dict[str, str] = {}
        for name in filter(None, names.split("\x00")):
            value = self._read(name)
            if value:
                vault[name] = value
        if vault:
            logger.info("Moved {} secrets into one keychain item", len(vault))
        return vault, not self._refused

    def _read(self, key: str) -> Optional[str]:
        try:
            return self._kr.get_password(_SERVICE_NAME, key)
        except self._kr.errors.KeyringError as exc:
            logger.warning("Could not read '{}' from the keychain: {}", key, exc)
            self._refused = True
            return None

    def _save(self) -> None:
        payload = json.dumps(self._vault or {}, sort_keys=True)
        self._kr.set_password(_SERVICE_NAME, self._VAULT_KEY, payload)


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

    def get_backend_only(self, key: str) -> Optional[str]:
        """The stored value, never one from the environment."""
        return self._backend.get(key)

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
            if is_private_key(key):
                continue
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
            backend = (
                KeychainVaultBackend() if sys.platform == "darwin" else KeyringBackend()
            )
        except RuntimeError:
            logger.warning(
                "OS keyring unavailable, falling back to encrypted SQLite secret backend"
            )
            backend = EncryptedSQLiteBackend()

    _instance = SecretManager(backend)
    return _instance
