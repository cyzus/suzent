"""Shared pytest fixtures and configuration."""

import os
import tempfile
import uuid

import pytest
from cryptography.fernet import Fernet

# suzent.config resolves DATA_DIR once at import, and test modules import the app
# during collection, before any fixture runs. Without this, get_database() and
# config writes land in the real ~/.suzent (e.g. test volumes like C:/data showing
# up in the desktop app). The marker keeps the dir non-empty so the legacy
# repo-local .suzent migration does not copy into it.
if "SUZENT_DATA_DIR" not in os.environ:
    _session_data_dir = tempfile.mkdtemp(prefix="suzent_test_data_")
    open(os.path.join(_session_data_dir, ".pytest"), "w").close()
    os.environ["SUZENT_DATA_DIR"] = _session_data_dir

from suzent.database import ChatDatabase  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path_factory, monkeypatch):
    """Default every test's SUZENT_DATA_DIR to a temp dir so nothing can write
    into the real ~/.suzent (sync profiles, secrets, config). Tests that need a
    specific data dir still set SUZENT_DATA_DIR themselves, overriding this.

    Only applies when the test hasn't already set it (some fixtures set it in
    their own body, which runs after autouse — so we skip if already present).
    """
    if "SUZENT_DATA_DIR" not in os.environ:
        monkeypatch.setenv(
            "SUZENT_DATA_DIR", str(tmp_path_factory.mktemp("suzent_data"))
        )

    # Force a keyring-free secret backend for the whole suite. Otherwise tests
    # that touch secrets or sync profiles depend on an OS
    # keyring being installed, which fails on headless CI/Linux with
    # NoKeyringError. Reset the cached singleton so the choice takes effect.
    if "SUZENT_SECRET_BACKEND" not in os.environ:
        monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")
    from suzent.core import secrets

    secrets._instance = None
    yield
    secrets._instance = None


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    monkeypatch.setenv("SUZENT_USER_CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("SUZENT_SECRET_DB_PATH", str(tmp_path / "secrets.db"))
    monkeypatch.setenv("SUZENT_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")

    from suzent.core import secrets

    secrets._instance = None

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = ChatDatabase(db_path)
    yield database

    # Dispose engine to release file locks (Windows)
    database.engine.dispose()

    # Cleanup
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


@pytest.fixture
def unique_id():
    """Generate a unique test ID."""
    return f"test-{uuid.uuid4().hex[:12]}"
