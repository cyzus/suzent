"""
Unit tests for database operations.
"""
import pytest
import json
from datetime import datetime


def test_database_initialization(chat_db):
    """Test that database initializes with correct schema."""
    # Check that tables exist
    with chat_db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "chats" in tables
        assert "plans" in tables
        assert "tasks" in tables
        assert "user_preferences" in tables
        assert "mcp_servers" in tables


def test_create_chat(chat_db, sample_chat):
    """Test creating a new chat."""
    chat_id = chat_db.create_chat(
        title=sample_chat["title"],
        config=sample_chat["config"],
        messages=sample_chat["messages"],
    )
    
    assert chat_id is not None
    assert len(chat_id) > 0
    
    # Verify chat was created
    chat = chat_db.get_chat(chat_id)
    assert chat is not None
    assert chat["title"] == sample_chat["title"]
    assert chat["config"] == sample_chat["config"]
    assert chat["messages"] == sample_chat["messages"]


def test_update_chat(chat_db, sample_chat):
    """Test updating an existing chat."""
    # Create chat
    chat_id = chat_db.create_chat(
        title=sample_chat["title"],
        config=sample_chat["config"],
        messages=sample_chat["messages"],
    )
    
    # Update chat
    new_title = "Updated Test Chat"
    new_messages = sample_chat["messages"] + [
        {"role": "user", "content": "How are you?"}
    ]
    
    chat_db.update_chat(
        chat_id=chat_id,
        title=new_title,
        config=sample_chat["config"],
        messages=new_messages,
    )
    
    # Verify update
    updated_chat = chat_db.get_chat(chat_id)
    assert updated_chat["title"] == new_title
    assert len(updated_chat["messages"]) == 3


def test_delete_chat(chat_db, sample_chat):
    """Test deleting a chat."""
    # Create chat
    chat_id = chat_db.create_chat(
        title=sample_chat["title"],
        config=sample_chat["config"],
        messages=sample_chat["messages"],
    )
    
    # Delete chat
    chat_db.delete_chat(chat_id)
    
    # Verify deletion
    chat = chat_db.get_chat(chat_id)
    assert chat is None


def test_list_chats(chat_db, sample_chat):
    """Test listing chats."""
    # Create multiple chats
    chat_ids = []
    for i in range(3):
        chat_id = chat_db.create_chat(
            title=f"Test Chat {i}",
            config=sample_chat["config"],
            messages=sample_chat["messages"],
        )
        chat_ids.append(chat_id)
    
    # List chats
    chats = chat_db.list_chats()
    
    assert len(chats) >= 3
    titles = [chat["title"] for chat in chats]
    assert "Test Chat 0" in titles
    assert "Test Chat 1" in titles
    assert "Test Chat 2" in titles


def test_list_chats_with_search(chat_db, sample_chat):
    """Test listing chats with search filter."""
    # Create chats with different titles
    chat_db.create_chat(
        title="Python Tutorial",
        config=sample_chat["config"],
        messages=sample_chat["messages"],
    )
    chat_db.create_chat(
        title="JavaScript Guide",
        config=sample_chat["config"],
        messages=sample_chat["messages"],
    )
    
    # Search for Python
    chats = chat_db.list_chats(search="Python")
    
    assert len(chats) >= 1
    assert any("Python" in chat["title"] for chat in chats)


def test_agent_state_persistence(chat_db, sample_chat):
    """Test saving and loading agent state."""
    # Create chat
    chat_id = chat_db.create_chat(
        title=sample_chat["title"],
        config=sample_chat["config"],
        messages=sample_chat["messages"],
    )
    
    # Mock agent state (simple dict for testing)
    agent_state = {"memory": {"key": "value"}, "step_count": 5}
    serialized_state = json.dumps(agent_state).encode()
    
    # Save agent state
    chat_db.update_agent_state(chat_id, serialized_state)
    
    # Load agent state
    loaded_state = chat_db.get_agent_state(chat_id)
    
    assert loaded_state == serialized_state


def test_plan_creation(chat_db, sample_plan):
    """Test creating a plan."""
    from suzent.plan import Plan, Task
    
    # Create chat first
    chat_id = sample_plan["chat_id"]
    chat_db.create_chat(
        chat_id=chat_id,
        title="Test Chat",
        config={},
        messages=[],
    )
    
    # Create plan
    plan = Plan(
        objective=sample_plan["objective"],
        tasks=[
            Task(**task_data) for task_data in sample_plan["tasks"]
        ],
    )
    
    from suzent.plan import write_plan_to_database
    plan_id = write_plan_to_database(plan, chat_id)
    
    assert plan_id is not None
    
    # Verify plan was created
    plans = chat_db.list_plans(chat_id)
    assert len(plans) >= 1
    assert plans[0]["objective"] == sample_plan["objective"]


def test_task_status_update(chat_db, sample_plan):
    """Test updating task status."""
    from suzent.plan import Plan, Task, write_plan_to_database, update_task_status
    
    # Create chat and plan
    chat_id = sample_plan["chat_id"]
    chat_db.create_chat(
        chat_id=chat_id,
        title="Test Chat",
        config={},
        messages=[],
    )
    
    plan = Plan(
        objective=sample_plan["objective"],
        tasks=[Task(**task_data) for task_data in sample_plan["tasks"]],
    )
    plan_id = write_plan_to_database(plan, chat_id)
    
    # Update task status
    task_number = 1
    new_status = "completed"
    update_task_status(plan_id, task_number, new_status)
    
    # Verify update
    plans = chat_db.list_plans(chat_id)
    tasks = plans[0]["tasks"]
    task_1 = next(t for t in tasks if t["number"] == task_number)
    assert task_1["status"] == new_status


def test_mcp_server_persistence(chat_db):
    """Test MCP server CRUD operations."""
    # Add server
    server_name = "Test Server"
    server_url = "http://localhost:8080/mcp"
    
    chat_db.add_mcp_server(server_name, server_url)
    
    # List servers
    servers = chat_db.list_mcp_servers()
    assert len(servers) >= 1
    assert any(s["name"] == server_name for s in servers)
    
    # Disable server
    server = next(s for s in servers if s["name"] == server_name)
    chat_db.set_mcp_server_enabled(server["id"], False)
    
    # Verify disabled
    servers = chat_db.list_mcp_servers()
    server = next(s for s in servers if s["name"] == server_name)
    assert server["enabled"] == 0
    
    # Remove server
    chat_db.remove_mcp_server(server["id"])
    
    # Verify removed
    servers = chat_db.list_mcp_servers()
    assert not any(s["name"] == server_name for s in servers)
