"""Tests for SecretManager and secret backends."""

import os
from unittest.mock import patch, MagicMock

from suzent.core.secrets import (
    EncryptedDBBackend,
    SecretManager,
    SecretBackend,
)


class InMemoryBackend(SecretBackend):
    """Simple in-memory backend for testing."""

    def __init__(self):
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def list_keys(self) -> list[str]:
        return list(self._store.keys())


class TestSecretManager:
    """Tests for the SecretManager facade."""

    def test_get_from_backend(self):
        backend = InMemoryBackend()
        backend.set("MY_KEY", "secret123")
        sm = SecretManager(backend)
        assert sm.get("MY_KEY") == "secret123"

    def test_get_falls_back_to_env(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)
        with patch.dict(os.environ, {"ENV_ONLY_KEY": "env_val"}):
            assert sm.get("ENV_ONLY_KEY") == "env_val"

    def test_backend_takes_priority_over_env(self):
        backend = InMemoryBackend()
        backend.set("DUAL_KEY", "backend_val")
        sm = SecretManager(backend)
        with patch.dict(os.environ, {"DUAL_KEY": "env_val"}):
            assert sm.get("DUAL_KEY") == "backend_val"

    def test_set_also_injects_env(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)
        # Clean env
        os.environ.pop("TEST_SET_KEY", None)

        sm.set("TEST_SET_KEY", "new_val")
        assert backend.get("TEST_SET_KEY") == "new_val"
        assert os.environ.get("TEST_SET_KEY") == "new_val"

        # Cleanup
        os.environ.pop("TEST_SET_KEY", None)

    def test_delete_removes_from_both(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)
        sm.set("DEL_KEY", "val")
        assert sm.get("DEL_KEY") == "val"

        sm.delete("DEL_KEY")
        assert backend.get("DEL_KEY") is None
        assert os.environ.get("DEL_KEY") is None

    def test_get_source_backend(self):
        backend = InMemoryBackend()
        backend.set("SRC_KEY", "val")
        sm = SecretManager(backend)
        assert sm.get_source("SRC_KEY") == "inmemorybackend"

    def test_get_source_env(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)
        with patch.dict(os.environ, {"ENV_SRC_KEY": "val"}):
            assert sm.get_source("ENV_SRC_KEY") == "env"

    def test_get_source_unset(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)
        assert sm.get_source("NONEXISTENT") == "unset"

    def test_list_keys(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)
        sm.set("K1", "v1")
        sm.set("K2", "v2")
        keys = sm.list_keys()
        assert "K1" in keys
        assert "K2" in keys

        # Cleanup
        os.environ.pop("K1", None)
        os.environ.pop("K2", None)

    def test_inject_all_to_env(self):
        backend = InMemoryBackend()
        backend.set("INJ1", "a")
        backend.set("INJ2", "b")
        sm = SecretManager(backend)

        # Ensure keys not in env
        os.environ.pop("INJ1", None)
        os.environ.pop("INJ2", None)

        count = sm.inject_all_to_env()
        assert count == 2
        assert os.environ.get("INJ1") == "a"
        assert os.environ.get("INJ2") == "b"

        # Cleanup
        os.environ.pop("INJ1", None)
        os.environ.pop("INJ2", None)

    def test_inject_skips_existing_env(self):
        backend = InMemoryBackend()
        backend.set("EXIST_KEY", "backend_val")
        sm = SecretManager(backend)

        with patch.dict(os.environ, {"EXIST_KEY": "original_env_val"}):
            count = sm.inject_all_to_env()
            assert count == 0  # Should skip because already in env
            assert os.environ["EXIST_KEY"] == "original_env_val"


class TestEncryptedDBBackend:
    """Tests for the Fernet-encrypted DB backend."""

    def test_roundtrip(self, tmp_path):
        key_file = tmp_path / "data" / ".secret_key"
        key_file.parent.mkdir(parents=True)

        with patch("suzent.core.secrets.os.environ", {"SUZENT_SECRET_KEY": ""}):
            with patch("suzent.config.PROJECT_DIR", tmp_path):
                # Mock the database
                mock_db = MagicMock()
                stored = {}

                def save_key(k, v):
                    stored[k] = v

                def get_key(k):
                    return stored.get(k)

                def del_key(k):
                    stored.pop(k, None)

                def get_all():
                    return dict(stored)

                mock_db.save_api_key = save_key
                mock_db.get_api_key = get_key
                mock_db.delete_api_key = del_key
                mock_db.get_api_keys = get_all

                with patch(
                    "suzent.core.secrets.EncryptedDBBackend._get_db",
                    return_value=mock_db,
                ):
                    backend = EncryptedDBBackend()

                    backend.set("TEST_KEY", "my_secret_value")
                    # Stored value should be encrypted (not plaintext)
                    raw = stored.get("TEST_KEY")
                    assert raw is not None
                    assert raw != "my_secret_value"

                    # Get should decrypt
                    assert backend.get("TEST_KEY") == "my_secret_value"

                    # Delete
                    backend.delete("TEST_KEY")
                    assert backend.get("TEST_KEY") is None
