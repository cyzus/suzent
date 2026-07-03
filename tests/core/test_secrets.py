import os
from unittest.mock import patch

from cryptography.fernet import Fernet

from suzent.core.secrets import (
    EncryptedSQLiteBackend,
    SecretManager,
    SecretBackend,
)


class InMemoryBackend(SecretBackend):
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
        os.environ.pop("TEST_SET_KEY", None)

        sm.set("TEST_SET_KEY", "new_val")
        assert backend.get("TEST_SET_KEY") == "new_val"
        assert os.environ.get("TEST_SET_KEY") == "new_val"

        os.environ.pop("TEST_SET_KEY", None)

    def test_set_backend_only_does_not_override_env(self):
        backend = InMemoryBackend()
        sm = SecretManager(backend)

        with patch.dict(os.environ, {"TEST_BACKEND_ONLY": "env_val"}):
            sm.set_backend_only("TEST_BACKEND_ONLY", "backend_val")

            assert backend.get("TEST_BACKEND_ONLY") == "backend_val"
            assert os.environ["TEST_BACKEND_ONLY"] == "env_val"
            assert sm.has_backend_value("TEST_BACKEND_ONLY") is True

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

        os.environ.pop("K1", None)
        os.environ.pop("K2", None)

    def test_inject_all_to_env(self):
        backend = InMemoryBackend()
        backend.set("INJ1", "a")
        backend.set("INJ2", "b")
        sm = SecretManager(backend)

        os.environ.pop("INJ1", None)
        os.environ.pop("INJ2", None)

        count = sm.inject_all_to_env()
        assert count == 2
        assert os.environ.get("INJ1") == "a"
        assert os.environ.get("INJ2") == "b"

        os.environ.pop("INJ1", None)
        os.environ.pop("INJ2", None)

    def test_inject_overwrites_existing_env_by_default(self):
        # The stored backend value is authoritative: it overwrites a stale
        # ambient env var (which previously shadowed a freshly-saved key and
        # caused auth failures).
        backend = InMemoryBackend()
        backend.set("EXIST_KEY", "backend_val")
        sm = SecretManager(backend)

        with patch.dict(os.environ, {"EXIST_KEY": "original_env_val"}):
            count = sm.inject_all_to_env()
            assert count == 1
            assert os.environ["EXIST_KEY"] == "backend_val"

    def test_inject_can_preserve_existing_env(self):
        backend = InMemoryBackend()
        backend.set("EXIST_KEY", "backend_val")
        sm = SecretManager(backend)

        with patch.dict(os.environ, {"EXIST_KEY": "original_env_val"}):
            count = sm.inject_all_to_env(overwrite=False)
            assert count == 0
            assert os.environ["EXIST_KEY"] == "original_env_val"


class TestEncryptedSQLiteBackend:
    def test_roundtrip(self, tmp_path, monkeypatch):
        db_path = tmp_path / "secrets.db"
        monkeypatch.setenv("SUZENT_SECRET_KEY", Fernet.generate_key().decode())
        backend = EncryptedSQLiteBackend(db_path)

        backend.set("TEST_KEY", "my_secret_value")

        assert backend.get("TEST_KEY") == "my_secret_value"
        assert "TEST_KEY" in backend.list_keys()
        assert b"my_secret_value" not in db_path.read_bytes()

        backend.delete("TEST_KEY")

        assert backend.get("TEST_KEY") is None
        assert "TEST_KEY" not in backend.list_keys()
