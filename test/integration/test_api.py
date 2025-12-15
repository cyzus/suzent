"""
Integration tests for API endpoints.

These tests verify the API endpoints work correctly end-to-end.
"""
import pytest
from starlette.testclient import TestClient
from suzent.server import app
from suzent.database import ChatDatabase


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_chat(client):
    """Create a test chat and return its ID."""
    response = client.post(
        "/chats",
        json={
            "title": "Test Chat",
            "config": {"model": "openai/gpt-4"},
            "messages": [],
        }
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "uptime_seconds" in data


def test_readiness_endpoint(client):
    """Test readiness check endpoint."""
    response = client.get("/ready")
    
    # Should be 200 (ready) or 503 (not ready)
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]


def test_system_info_endpoint(client):
    """Test system info endpoint."""
    response = client.get("/info")
    
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "python_version" in data
    assert "database" in data


def test_metrics_endpoint(client):
    """Test metrics endpoint."""
    response = client.get("/metrics")
    
    assert response.status_code == 200
    # Should return text/plain for Prometheus
    assert "text/plain" in response.headers.get("content-type", "")


def test_create_chat(client):
    """Test creating a chat."""
    response = client.post(
        "/chats",
        json={
            "title": "Integration Test Chat",
            "config": {
                "model": "openai/gpt-4",
                "agent": "ToolCallingAgent",
                "tools": ["WebSearchTool"],
            },
            "messages": [],
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert len(data["id"]) > 0


def test_get_chat(client, test_chat):
    """Test retrieving a chat."""
    response = client.get(f"/chats/{test_chat}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_chat
    assert "title" in data
    assert "messages" in data
    assert "config" in data


def test_update_chat(client, test_chat):
    """Test updating a chat."""
    response = client.put(
        f"/chats/{test_chat}",
        json={
            "title": "Updated Title",
            "config": {"model": "openai/gpt-4"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        }
    )
    
    assert response.status_code == 200
    
    # Verify update
    response = client.get(f"/chats/{test_chat}")
    data = response.json()
    assert data["title"] == "Updated Title"
    assert len(data["messages"]) == 2


def test_list_chats(client, test_chat):
    """Test listing chats."""
    response = client.get("/chats")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Find our test chat
    chat_ids = [chat["id"] for chat in data]
    assert test_chat in chat_ids


def test_delete_chat(client, test_chat):
    """Test deleting a chat."""
    response = client.delete(f"/chats/{test_chat}")
    
    assert response.status_code == 200
    
    # Verify deletion
    response = client.get(f"/chats/{test_chat}")
    assert response.status_code == 404


def test_get_config(client):
    """Test getting configuration."""
    response = client.get("/config")
    
    assert response.status_code == 200
    data = response.json()
    assert "model_options" in data
    assert "tool_options" in data
    assert isinstance(data["model_options"], list)
    assert isinstance(data["tool_options"], list)


def test_stats_endpoint(client):
    """Test database stats endpoint."""
    response = client.get("/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert "total_chats" in data
    assert "total_messages" in data
    assert "database_size_bytes" in data
    assert isinstance(data["total_chats"], int)


def test_export_chat_json(client, test_chat):
    """Test exporting a chat as JSON."""
    response = client.get(f"/export/chat?chat_id={test_chat}&format=json")
    
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
    
    data = response.json()
    assert data["id"] == test_chat
    assert "messages" in data
    assert "exported_at" in data


def test_export_chat_markdown(client, test_chat):
    """Test exporting a chat as Markdown."""
    # Add some messages first
    client.put(
        f"/chats/{test_chat}",
        json={
            "title": "Test Chat",
            "config": {"model": "openai/gpt-4"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ],
        }
    )
    
    response = client.get(f"/export/chat?chat_id={test_chat}&format=markdown")
    
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
    
    content = response.text
    assert "# Test Chat" in content
    assert "Hello" in content
    assert "Hi!" in content


def test_import_chat(client):
    """Test importing a chat."""
    chat_data = {
        "id": "imported-chat-123",
        "title": "Imported Chat",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T01:00:00",
        "config": {"model": "openai/gpt-4"},
        "messages": [
            {"role": "user", "content": "Test message"}
        ],
        "plans": [],
        "exported_at": "2024-01-01T02:00:00",
        "version": "1.0",
    }
    
    response = client.post("/import/chat", json=chat_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "chat_id" in data
    
    # Cleanup
    if "chat_id" in data:
        client.delete(f"/chats/{data['chat_id']}")


def test_backup_endpoint(client):
    """Test database backup endpoint."""
    response = client.get("/backup")
    
    assert response.status_code == 200
    assert "application/x-sqlite3" in response.headers.get("content-type", "")
    assert len(response.content) > 0


def test_cors_headers(client):
    """Test that CORS headers are present."""
    response = client.options("/chats")
    
    # CORS headers should be present
    assert "access-control-allow-origin" in response.headers


def test_invalid_chat_id(client):
    """Test handling of invalid chat ID."""
    response = client.get("/chats/nonexistent-chat-id")
    
    assert response.status_code == 404


def test_missing_parameters(client):
    """Test handling of missing required parameters."""
    # Try to export without chat_id
    response = client.get("/export/chat")
    
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
