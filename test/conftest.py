"""
Pytest configuration and fixtures for Suzent tests.
"""
import os
import sys
import pytest
import sqlite3
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def temp_db():
    """Provide a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def chat_db(temp_db):
    """Provide a ChatDatabase instance with temporary storage."""
    from suzent.database import ChatDatabase
    
    db = ChatDatabase(db_path=temp_db)
    yield db
    
    # Cleanup is handled by temp_db fixture


@pytest.fixture
def sample_chat():
    """Provide sample chat data for testing."""
    return {
        "id": "test-chat-123",
        "title": "Test Chat",
        "config": {
            "model": "openai/gpt-4",
            "agent": "ToolCallingAgent",
            "tools": ["WebSearchTool"],
        },
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
    }


@pytest.fixture
def sample_plan():
    """Provide sample plan data for testing."""
    return {
        "chat_id": "test-chat-123",
        "objective": "Complete the test",
        "tasks": [
            {"number": 1, "description": "Task 1", "status": "pending"},
            {"number": 2, "description": "Task 2", "status": "in_progress"},
        ],
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")  # Reduce noise in tests
