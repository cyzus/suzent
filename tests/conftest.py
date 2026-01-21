"""Shared pytest fixtures and configuration."""

import os
import tempfile
import uuid

import pytest

from suzent.database import ChatDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
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
