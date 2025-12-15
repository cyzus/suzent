"""
Data export/import functionality for Suzent.

Provides utilities to export chats to various formats and import them back.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from suzent.database import ChatDatabase


def export_chat_to_json(chat_db: ChatDatabase, chat_id: str) -> Dict[str, Any]:
    """
    Export a single chat to JSON format.
    
    Args:
        chat_db: Database instance
        chat_id: ID of chat to export
        
    Returns:
        Dictionary containing chat data
    """
    chat = chat_db.get_chat(chat_id)
    if not chat:
        raise ValueError(f"Chat {chat_id} not found")
    
    # Get associated plans
    plans = chat_db.list_plans(chat_id)
    
    return {
        "id": chat["id"],
        "title": chat["title"],
        "created_at": chat["created_at"],
        "updated_at": chat["updated_at"],
        "config": chat["config"],
        "messages": chat["messages"],
        "plans": plans,
        "exported_at": datetime.now().isoformat(),
        "version": "1.0",
    }


def export_chat_to_markdown(chat_db: ChatDatabase, chat_id: str) -> str:
    """
    Export a single chat to Markdown format.
    
    Args:
        chat_db: Database instance
        chat_id: ID of chat to export
        
    Returns:
        Markdown string
    """
    chat = chat_db.get_chat(chat_id)
    if not chat:
        raise ValueError(f"Chat {chat_id} not found")
    
    lines = []
    lines.append(f"# {chat['title']}\n")
    lines.append(f"**Created:** {chat['created_at']}\n")
    lines.append(f"**Updated:** {chat['updated_at']}\n")
    lines.append(f"**Model:** {chat['config'].get('model', 'N/A')}\n")
    lines.append("\n---\n\n")
    
    # Export messages
    for msg in chat["messages"]:
        role = msg["role"].title()
        content = msg["content"]
        
        if isinstance(content, list):
            # Handle multi-part messages (text + images)
            text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
            image_parts = [part for part in content if part.get("type") == "image_url"]
            
            lines.append(f"## {role}\n\n")
            if text_parts:
                lines.append("\n".join(text_parts))
                lines.append("\n\n")
            if image_parts:
                lines.append(f"*[Contains {len(image_parts)} image(s)]*\n\n")
        else:
            lines.append(f"## {role}\n\n")
            lines.append(f"{content}\n\n")
        
        lines.append("---\n\n")
    
    # Export plans if any
    plans = chat_db.list_plans(chat_id)
    if plans:
        lines.append("## Plans\n\n")
        for plan in plans:
            lines.append(f"### {plan['objective']}\n\n")
            for task in plan.get("tasks", []):
                status_emoji = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "completed": "✅",
                    "failed": "❌",
                }.get(task["status"], "❓")
                lines.append(f"{status_emoji} **Task {task['number']}**: {task['description']}\n")
                if task.get("note"):
                    lines.append(f"   *Note: {task['note']}*\n")
            lines.append("\n")
    
    return "".join(lines)


def export_all_chats(chat_db: ChatDatabase, output_dir: Path) -> List[str]:
    """
    Export all chats to JSON files.
    
    Args:
        chat_db: Database instance
        output_dir: Directory to save exports
        
    Returns:
        List of exported file paths
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    chats = chat_db.list_chats(limit=1000)
    exported_files = []
    
    for chat in chats:
        chat_data = export_chat_to_json(chat_db, chat["id"])
        
        # Sanitize filename
        safe_title = "".join(c for c in chat["title"] if c.isalnum() or c in (' ', '-', '_'))
        safe_title = safe_title[:50]  # Limit length
        
        filename = f"{chat['id'][:8]}_{safe_title}.json"
        filepath = output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, indent=2, ensure_ascii=False)
        
        exported_files.append(str(filepath))
    
    return exported_files


def import_chat_from_json(chat_db: ChatDatabase, json_data: Dict[str, Any], 
                          preserve_id: bool = False) -> str:
    """
    Import a chat from JSON format.
    
    Args:
        chat_db: Database instance
        json_data: Chat data in JSON format
        preserve_id: Whether to preserve original chat ID (default: False, generates new ID)
        
    Returns:
        ID of imported chat
    """
    # Create chat
    chat_id = chat_db.create_chat(
        chat_id=json_data["id"] if preserve_id else None,
        title=json_data["title"],
        config=json_data["config"],
        messages=json_data["messages"],
    )
    
    # Import plans if present
    if "plans" in json_data:
        from suzent.plan import Plan, Task, write_plan_to_database
        
        for plan_data in json_data["plans"]:
            tasks = [Task(**task) for task in plan_data.get("tasks", [])]
            plan = Plan(
                objective=plan_data["objective"],
                tasks=tasks,
            )
            write_plan_to_database(plan, chat_id)
    
    return chat_id


def backup_database(db_path: str, backup_dir: Path) -> str:
    """
    Create a backup of the entire database.
    
    Args:
        db_path: Path to database file
        backup_dir: Directory to save backup
        
    Returns:
        Path to backup file
    """
    import shutil
    
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"chats_backup_{timestamp}.db"
    backup_path = backup_dir / backup_filename
    
    shutil.copy2(db_path, backup_path)
    
    return str(backup_path)


def get_database_stats(chat_db: ChatDatabase) -> Dict[str, Any]:
    """
    Get statistics about the database.
    
    Args:
        chat_db: Database instance
        
    Returns:
        Dictionary with statistics
    """
    with chat_db.get_connection() as conn:
        # Count chats
        chat_count = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        
        # Count messages
        messages_count = 0
        chats = chat_db.list_chats(limit=1000)
        for chat in chats:
            messages_count += len(chat.get("messages", []))
        
        # Count plans and tasks
        plan_count = conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        
        # Get database size
        db_size = Path(chat_db.db_path).stat().st_size
        
        # Get oldest and newest chat
        oldest = conn.execute(
            "SELECT created_at FROM chats ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        newest = conn.execute(
            "SELECT created_at FROM chats ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        
        return {
            "total_chats": chat_count,
            "total_messages": messages_count,
            "total_plans": plan_count,
            "total_tasks": task_count,
            "database_size_bytes": db_size,
            "database_size_mb": round(db_size / (1024 * 1024), 2),
            "oldest_chat": oldest[0] if oldest else None,
            "newest_chat": newest[0] if newest else None,
        }
