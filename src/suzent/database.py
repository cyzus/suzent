"""
Database layer for chat persistence using SQLite.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path


class ChatDatabase:
    """Handles SQLite database operations for chat persistence."""

    def __init__(self, db_path: str = "chats.db"):
        self.db_path = Path(db_path)
        self.init_database()

    def init_database(self):
        """Initialize the database and create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    config TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    agent_state BLOB
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chats_updated_at 
                ON chats(updated_at DESC)
            """)

            # Create plans table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
                )
            """)

            # Create tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    number INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    note TEXT,
                    capabilities TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (plan_id) REFERENCES plans (id) ON DELETE CASCADE
                )
            """)

            # Create indexes for plans and tasks
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_plans_chat_id 
                ON plans(chat_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_plan_id 
                ON tasks(plan_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_number 
                ON tasks(plan_id, number)
            """)

            # Add agent_state column if it doesn't exist (for existing databases)
            try:
                conn.execute("ALTER TABLE chats ADD COLUMN agent_state BLOB")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists
                pass

            # Add capabilities column to tasks if it doesn't exist
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN capabilities TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists
                pass

            # Create user_preferences table for global config persistence
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    model TEXT,
                    agent TEXT,
                    tools TEXT,
                    memory_enabled INTEGER DEFAULT 0,
                    updated_at TIMESTAMP NOT NULL
                )
            """)

            # Create mcp_servers table for MCP server persistence
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    name TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    url TEXT,
                    command TEXT,
                    args TEXT,
                    env TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)

            conn.commit()

    def create_chat(
        self,
        title: str,
        config: Dict[str, Any],
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
    ) -> str:
        """Create a new chat and return its ID."""
        chat_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        messages = messages or []

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO chats (id, title, created_at, updated_at, config, messages, agent_state)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    chat_id,
                    title,
                    now,
                    now,
                    json.dumps(config),
                    json.dumps(messages),
                    agent_state,
                ),
            )
            conn.commit()

        return chat_id

    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific chat by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM chats WHERE id = ?
            """,
                (chat_id,),
            )
            row = cursor.fetchone()

            if row:
                result = {
                    "id": row["id"],
                    "title": row["title"],
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                    "config": json.loads(row["config"]),
                    "messages": json.loads(row["messages"]),
                }

                # Include agent state if it exists
                if row["agent_state"] is not None:
                    result["agent_state"] = row["agent_state"]

                return result
            return None

    def update_chat(
        self,
        chat_id: str,
        title: str = None,
        config: Dict[str, Any] = None,
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
    ) -> bool:
        """Update an existing chat."""
        with sqlite3.connect(self.db_path) as conn:
            # First check if chat exists and get current values
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, title, messages, agent_state FROM chats WHERE id = ?",
                (chat_id,),
            )
            existing_row = cursor.fetchone()
            if not existing_row:
                return False

            # Build update query dynamically
            updates = []
            params = []

            # Track whether we should update the timestamp
            # Only update timestamp for meaningful content changes (not just config)
            should_update_timestamp = False

            if title is not None:
                existing_title = existing_row["title"]
                if title != existing_title:
                    updates.append("title = ?")
                    params.append(title)
                    should_update_timestamp = True

            if config is not None:
                updates.append("config = ?")
                params.append(json.dumps(config))
                # Config changes alone don't update timestamp

            if messages is not None:
                # Compare with existing messages to see if they actually changed
                existing_messages = json.loads(existing_row["messages"])
                if messages != existing_messages:
                    updates.append("messages = ?")
                    params.append(json.dumps(messages))
                    should_update_timestamp = True

            if agent_state is not None:
                existing_agent_state = existing_row["agent_state"]
                # Only update if agent_state actually changed
                if agent_state != existing_agent_state:
                    updates.append("agent_state = ?")
                    params.append(agent_state)
                    should_update_timestamp = True

            # Only update timestamp if meaningful content changed
            if updates and should_update_timestamp:
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())

            if updates:
                params.append(chat_id)
                # Reset row_factory for execute
                conn.row_factory = None
                conn.execute(
                    f"""
                    UPDATE chats SET {", ".join(updates)} WHERE id = ?
                """,
                    params,
                )
                conn.commit()

            return True

    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0

    def reassign_plan_chat(self, old_chat_id: str, new_chat_id: str) -> int:
        """Reassign all plans from one chat_id to another. Returns number of plans updated."""
        if old_chat_id == new_chat_id:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE plans SET chat_id = ?, updated_at = ? WHERE chat_id = ?",
                (new_chat_id, datetime.now().isoformat(), old_chat_id),
            )
            conn.commit()
            return cursor.rowcount

    def list_chats(
        self, limit: int = 50, offset: int = 0, search: str = None
    ) -> List[Dict[str, Any]]:
        """List chat summaries ordered by last updated, optionally filtered by search query."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if search:
                # Search in title and message content
                search_pattern = f"%{search}%"
                cursor = conn.execute(
                    """
                    SELECT id, title, created_at, updated_at, messages
                    FROM chats 
                    WHERE title LIKE ? OR messages LIKE ?
                    ORDER BY updated_at DESC 
                    LIMIT ? OFFSET ?
                """,
                    (search_pattern, search_pattern, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, title, created_at, updated_at, messages
                    FROM chats 
                    ORDER BY updated_at DESC 
                    LIMIT ? OFFSET ?
                """,
                    (limit, offset),
                )

            chats = []
            for row in cursor.fetchall():
                messages = json.loads(row["messages"])
                last_message = None
                if messages:
                    # Get the last user or assistant message content (truncated)
                    last_msg = messages[-1]
                    last_message = last_msg.get("content", "")[:100]
                    if len(last_msg.get("content", "")) > 100:
                        last_message += "..."

                chats.append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "createdAt": row["created_at"],
                        "updatedAt": row["updated_at"],
                        "messageCount": len(messages),
                        "lastMessage": last_message,
                    }
                )

            return chats

    def get_chat_count(self, search: str = None) -> int:
        """Get total number of chats, optionally filtered by search query."""
        with sqlite3.connect(self.db_path) as conn:
            if search:
                search_pattern = f"%{search}%"
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM chats WHERE title LIKE ? OR messages LIKE ?",
                    (search_pattern, search_pattern),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM chats")
            return cursor.fetchone()[0]

    # Plan management methods
    def create_plan(
        self, chat_id: str, objective: str, tasks: List[Dict[str, Any]] = None
    ) -> int:
        """Create or update the single plan for a chat and return its ID."""
        now = datetime.now().isoformat()
        tasks = tasks or []

        with sqlite3.connect(self.db_path) as conn:
            # Check for existing plan
            cursor = conn.execute(
                "SELECT id FROM plans WHERE chat_id = ? LIMIT 1", (chat_id,)
            )
            row = cursor.fetchone()

            if row:
                plan_id = row[0]
                # Update existing plan
                conn.execute(
                    """
                    UPDATE plans SET objective = ?, updated_at = ? WHERE id = ?
                """,
                    (objective, now, plan_id),
                )

                # Delete existing tasks to overwrite with new ones (since we are "creating/updating" the plan structure)
                # Note: This resets history of phases if completely re-called.
                # Assuming this is desired behavior for "Creating/Updating" a plan as a whole.
                conn.execute("DELETE FROM tasks WHERE plan_id = ?", (plan_id,))
            else:
                # Create new plan
                cursor = conn.execute(
                    """
                    INSERT INTO plans (chat_id, objective, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (chat_id, objective, now, now),
                )
                plan_id = cursor.lastrowid

            # Create the tasks/phases
            for task in tasks:
                conn.execute(
                    """
                    INSERT INTO tasks (plan_id, number, description, status, note, capabilities, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        plan_id,
                        task.get("number"),
                        task.get("description"),
                        task.get("status", "pending"),
                        task.get("note"),
                        task.get("capabilities"),
                        now,
                        now,
                    ),
                )

            conn.commit()
            return plan_id

    def get_plan(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get the plan for a specific chat."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Get the plan
            cursor = conn.execute(
                """
                SELECT * FROM plans WHERE chat_id = ? ORDER BY created_at DESC LIMIT 1
            """,
                (chat_id,),
            )
            plan_row = cursor.fetchone()

            if not plan_row:
                return None

            # Get the tasks for this plan
            cursor = conn.execute(
                """
                SELECT * FROM tasks WHERE plan_id = ? ORDER BY number
            """,
                (plan_row["id"],),
            )
            task_rows = cursor.fetchall()

            tasks = []
            for task_row in task_rows:
                tasks.append(
                    {
                        "id": task_row["id"],
                        "number": task_row["number"],
                        "description": task_row["description"],
                        "status": task_row["status"],
                        "note": task_row["note"],
                        "capabilities": task_row["capabilities"],
                        "created_at": task_row["created_at"],
                        "updated_at": task_row["updated_at"],
                    }
                )

            return {
                "id": plan_row["id"],
                "chat_id": plan_row["chat_id"],
                "objective": plan_row["objective"],
                "tasks": tasks,
                "created_at": plan_row["created_at"],
                "updated_at": plan_row["updated_at"],
            }

    def get_plan_by_id(self, plan_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a plan and its tasks by plan ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                "SELECT * FROM plans WHERE id = ?",
                (plan_id,),
            )
            plan_row = cursor.fetchone()
            if not plan_row:
                return None

            task_cursor = conn.execute(
                "SELECT * FROM tasks WHERE plan_id = ? ORDER BY number",
                (plan_id,),
            )
            task_rows = task_cursor.fetchall()
            tasks = [
                {
                    "id": task_row["id"],
                    "number": task_row["number"],
                    "description": task_row["description"],
                    "status": task_row["status"],
                    "note": task_row["note"],
                    "capabilities": task_row["capabilities"],
                    "created_at": task_row["created_at"],
                    "updated_at": task_row["updated_at"],
                }
                for task_row in task_rows
            ]

            return {
                "id": plan_row["id"],
                "chat_id": plan_row["chat_id"],
                "objective": plan_row["objective"],
                "tasks": tasks,
                "created_at": plan_row["created_at"],
                "updated_at": plan_row["updated_at"],
            }

    def list_plans(
        self, chat_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Return all plans for a chat ordered by newest first."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            query = "SELECT * FROM plans WHERE chat_id = ? ORDER BY created_at DESC"
            params: List[Any] = [chat_id]
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)

            cursor = conn.execute(query, tuple(params))
            plan_rows = cursor.fetchall()
            plans: List[Dict[str, Any]] = []

            for plan_row in plan_rows:
                task_cursor = conn.execute(
                    "SELECT * FROM tasks WHERE plan_id = ? ORDER BY number",
                    (plan_row["id"],),
                )
                task_rows = task_cursor.fetchall()
                tasks = [
                    {
                        "id": task_row["id"],
                        "number": task_row["number"],
                        "description": task_row["description"],
                        "status": task_row["status"],
                        "note": task_row["note"],
                        "capabilities": task_row["capabilities"],
                        "created_at": task_row["created_at"],
                        "updated_at": task_row["updated_at"],
                    }
                    for task_row in task_rows
                ]

                plans.append(
                    {
                        "id": plan_row["id"],
                        "chat_id": plan_row["chat_id"],
                        "objective": plan_row["objective"],
                        "tasks": tasks,
                        "created_at": plan_row["created_at"],
                        "updated_at": plan_row["updated_at"],
                    }
                )

            return plans

    def update_plan(
        self,
        chat_id: str,
        objective: str = None,
        tasks: List[Dict[str, Any]] = None,
        plan_id: Optional[int] = None,
    ) -> bool:
        """Update an existing plan, optionally targeting a specific plan_id."""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Check if plan exists
            if plan_id is not None:
                cursor = conn.execute(
                    "SELECT id FROM plans WHERE id = ? AND chat_id = ?",
                    (plan_id, chat_id),
                )
            else:
                cursor = conn.execute(
                    "SELECT id FROM plans WHERE chat_id = ? ORDER BY created_at DESC LIMIT 1",
                    (chat_id,),
                )
            plan_row = cursor.fetchone()

            if plan_row:
                plan_id = plan_row[0]

                # Update objective if provided
                if objective is not None:
                    conn.execute(
                        """
                        UPDATE plans SET objective = ?, updated_at = ? WHERE id = ?
                    """,
                        (objective, now, plan_id),
                    )

                # Update tasks if provided
                if tasks is not None:
                    # Delete existing tasks
                    conn.execute("DELETE FROM tasks WHERE plan_id = ?", (plan_id,))

                    # Insert new tasks
                    for task in tasks:
                        conn.execute(
                            """
                            INSERT INTO tasks (plan_id, number, description, status, note, capabilities, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                plan_id,
                                task.get("number"),
                                task.get("description"),
                                task.get("status", "pending"),
                                task.get("note"),
                                task.get("capabilities"),
                                now,
                                now,
                            ),
                        )

                conn.commit()
                return True
            else:
                # Create new plan if it doesn't exist
                if objective is not None and tasks is not None:
                    self.create_plan(chat_id, objective, tasks)
                    return True
                return False

    def update_task_status(
        self,
        chat_id: str,
        task_number: int,
        status: str,
        note: str = None,
        plan_id: Optional[int] = None,
    ) -> bool:
        """Update the status and optionally note of a specific task for a plan."""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Get the plan ID for this chat
            if plan_id is not None:
                cursor = conn.execute(
                    "SELECT id FROM plans WHERE id = ? AND chat_id = ?",
                    (plan_id, chat_id),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id FROM plans WHERE chat_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                    (chat_id,),
                )
            plan_row = cursor.fetchone()

            if not plan_row:
                return False

            plan_id = plan_row[0]

            # Update the task
            update_fields = ["status = ?", "updated_at = ?"]
            params = [status, now]

            if note is not None:
                update_fields.append("note = ?")
                params.append(note)

            params.extend([plan_id, task_number])

            cursor = conn.execute(
                f"""
                UPDATE tasks SET {", ".join(update_fields)}
                WHERE plan_id = ? AND number = ?
            """,
                params,
            )

            conn.commit()
            return cursor.rowcount > 0

    def delete_plan(self, chat_id: str) -> bool:
        """Delete the plan for a specific chat."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM plans WHERE chat_id = ?", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0

    # User preferences methods
    def get_user_preferences(self) -> Optional[Dict[str, Any]]:
        """Get user preferences from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM user_preferences WHERE id = 1")
            row = cursor.fetchone()

            if row:
                return {
                    "model": row["model"],
                    "agent": row["agent"],
                    "tools": json.loads(row["tools"]) if row["tools"] else [],
                    "memory_enabled": bool(row["memory_enabled"]),
                    "updated_at": row["updated_at"],
                }
            return None

    def save_user_preferences(
        self,
        model: str = None,
        agent: str = None,
        tools: List[str] = None,
        memory_enabled: bool = None,
    ) -> bool:
        """Save user preferences to the database."""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Check if preferences exist
            cursor = conn.execute("SELECT id FROM user_preferences WHERE id = 1")
            exists = cursor.fetchone() is not None

            if exists:
                # Update existing preferences
                updates = []
                params = []

                if model is not None:
                    updates.append("model = ?")
                    params.append(model)

                if agent is not None:
                    updates.append("agent = ?")
                    params.append(agent)

                if tools is not None:
                    updates.append("tools = ?")
                    params.append(json.dumps(tools))

                if memory_enabled is not None:
                    updates.append("memory_enabled = ?")
                    params.append(1 if memory_enabled else 0)

                if updates:
                    updates.append("updated_at = ?")
                    params.append(now)
                    params.append(1)  # id = 1

                    conn.execute(
                        f"""
                        UPDATE user_preferences SET {", ".join(updates)} WHERE id = ?
                    """,
                        params,
                    )
            else:
                # Insert new preferences
                conn.execute(
                    """
                    INSERT INTO user_preferences (id, model, agent, tools, memory_enabled, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?)
                """,
                    (
                        model,
                        agent,
                        json.dumps(tools) if tools is not None else None,
                        1 if memory_enabled else 0,
                        now,
                    ),
                )

            conn.commit()
            return True

    # MCP server methods
    def get_mcp_servers(self) -> Dict[str, Any]:
        """Get all MCP servers from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM mcp_servers")
            rows = cursor.fetchall()

            urls = {}
            stdio = {}
            enabled = {}

            for row in rows:
                name = row["name"]
                enabled[name] = bool(row["enabled"])

                if row["type"] == "url":
                    urls[name] = row["url"]
                elif row["type"] == "stdio":
                    stdio_params = {"command": row["command"]}
                    if row["args"]:
                        stdio_params["args"] = json.loads(row["args"])
                    if row["env"]:
                        stdio_params["env"] = json.loads(row["env"])
                    stdio[name] = stdio_params

            return {"urls": urls, "stdio": stdio, "enabled": enabled}

    def add_mcp_server(
        self, name: str, url: str = None, stdio_params: Dict[str, Any] = None
    ) -> bool:
        """Add or update an MCP server."""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Delete existing server if it exists
            conn.execute("DELETE FROM mcp_servers WHERE name = ?", (name,))

            if url:
                # URL server
                conn.execute(
                    """
                    INSERT INTO mcp_servers (name, type, url, enabled, created_at, updated_at)
                    VALUES (?, 'url', ?, 1, ?, ?)
                """,
                    (name, url, now, now),
                )
            elif stdio_params:
                # Stdio server
                conn.execute(
                    """
                    INSERT INTO mcp_servers
                    (name, type, command, args, env, enabled, created_at, updated_at)
                    VALUES (?, 'stdio', ?, ?, ?, 1, ?, ?)
                """,
                    (
                        name,
                        stdio_params.get("command"),
                        json.dumps(stdio_params.get("args"))
                        if stdio_params.get("args")
                        else None,
                        json.dumps(stdio_params.get("env"))
                        if stdio_params.get("env")
                        else None,
                        now,
                        now,
                    ),
                )
            else:
                return False

            conn.commit()
            return True

    def remove_mcp_server(self, name: str) -> bool:
        """Remove an MCP server."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM mcp_servers WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def set_mcp_server_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable an MCP server."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE mcp_servers SET enabled = ?, updated_at = ? WHERE name = ?
            """,
                (1 if enabled else 0, datetime.now().isoformat(), name),
            )
            conn.commit()
            return cursor.rowcount > 0


# Global database instance
_db_instance = None


def get_database() -> ChatDatabase:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = ChatDatabase()
    return _db_instance


def generate_chat_title(first_message: str, max_length: int = 50) -> str:
    """Generate a chat title from the first user message."""
    if not first_message.strip():
        return "New Chat"

    # Clean and truncate the message
    title = first_message.strip()

    # Remove newlines and extra spaces
    title = " ".join(title.split())

    # Truncate if too long
    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return title
