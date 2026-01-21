"""Add sandbox_enabled column to user_preferences table."""

import sqlite3
from pathlib import Path


def migrate():
    db_path = Path("chats.db")
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("PRAGMA table_info(user_preferences)")
    columns = [row[1] for row in cursor.fetchall()]

    if "sandbox_enabled" in columns:
        print("Column 'sandbox_enabled' already exists")
        conn.close()
        return

    # Add the column with default value
    print("Adding 'sandbox_enabled' column to user_preferences...")
    cursor.execute("""
        ALTER TABLE user_preferences
        ADD COLUMN sandbox_enabled INTEGER DEFAULT 1
    """)

    conn.commit()
    print("Migration completed successfully!")

    # Verify
    cursor.execute("PRAGMA table_info(user_preferences)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Current columns: {columns}")

    conn.close()


if __name__ == "__main__":
    migrate()
