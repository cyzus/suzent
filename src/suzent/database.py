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
                    messages TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chats_updated_at 
                ON chats(updated_at DESC)
            """)
            conn.commit()
    
    def create_chat(self, title: str, config: Dict[str, Any], messages: List[Dict[str, Any]] = None) -> str:
        """Create a new chat and return its ID."""
        chat_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        messages = messages or []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO chats (id, title, created_at, updated_at, config, messages)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                chat_id,
                title,
                now,
                now,
                json.dumps(config),
                json.dumps(messages)
            ))
            conn.commit()
        
        return chat_id
    
    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific chat by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM chats WHERE id = ?
            """, (chat_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "id": row["id"],
                    "title": row["title"],
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                    "config": json.loads(row["config"]),
                    "messages": json.loads(row["messages"])
                }
            return None
    
    def update_chat(self, chat_id: str, title: str = None, config: Dict[str, Any] = None, 
                   messages: List[Dict[str, Any]] = None) -> bool:
        """Update an existing chat."""
        with sqlite3.connect(self.db_path) as conn:
            # First check if chat exists
            cursor = conn.execute("SELECT id FROM chats WHERE id = ?", (chat_id,))
            if not cursor.fetchone():
                return False
            
            # Build update query dynamically
            updates = []
            params = []
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            
            if config is not None:
                updates.append("config = ?")
                params.append(json.dumps(config))
            
            if messages is not None:
                updates.append("messages = ?")
                params.append(json.dumps(messages))
            
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(chat_id)
            
            conn.execute(f"""
                UPDATE chats SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()
            
            return True
    
    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def list_chats(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List chat summaries ordered by last updated."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT id, title, created_at, updated_at, messages
                FROM chats 
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
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
                
                chats.append({
                    "id": row["id"],
                    "title": row["title"],
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                    "messageCount": len(messages),
                    "lastMessage": last_message
                })
            
            return chats
    
    def get_chat_count(self) -> int:
        """Get total number of chats."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM chats")
            return cursor.fetchone()[0]


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
        title = title[:max_length - 3] + "..."
    
    return title