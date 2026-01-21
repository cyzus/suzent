"""
Fix timestamp format mismatch after SQLModel migration.

Old code stored timestamps as ISO format with 'T': 2026-01-19T19:17:26
SQLModel stores with space: 2026-01-19 19:17:26

This causes sorting issues since space (ASCII 32) < 'T' (ASCII 84).
"""

import sqlite3
import sys


def fix_timestamps(db_path: str = "chats.db"):
    conn = sqlite3.connect(db_path)

    # Fix timestamps: replace T with space for consistent format
    tables = [
        ("chats", ["created_at", "updated_at"]),
        ("plans", ["created_at", "updated_at"]),
        ("tasks", ["created_at", "updated_at"]),
        ("user_preferences", ["updated_at"]),
        ("mcp_servers", ["created_at", "updated_at"]),
    ]

    for table, columns in tables:
        for col in columns:
            try:
                conn.execute(
                    f"UPDATE {table} SET {col} = REPLACE({col}, 'T', ' ') WHERE {col} LIKE '%T%'"
                )
            except sqlite3.OperationalError:
                pass  # Table or column might not exist

    conn.commit()
    print("Timestamps normalized to space format")

    # Verify
    cursor = conn.execute(
        "SELECT title, updated_at FROM chats ORDER BY updated_at DESC LIMIT 5"
    )
    print("\nTop 5 chats after fix:")
    for i, row in enumerate(cursor.fetchall(), 1):
        title = (row[0] or "Untitled")[:40]
        print(f"{i}. [{row[1]}] {title}")

    conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "chats.db"
    fix_timestamps(db_path)
