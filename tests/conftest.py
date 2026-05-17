"""Shared pytest fixtures and configuration."""

import os
import tempfile
import uuid

import pytest

from suzent.database import ChatDatabase


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    monkeypatch.setenv("SUZENT_USER_CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("SUZENT_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setenv("SUZENT_SECRET_BACKEND", "dotenv")

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
