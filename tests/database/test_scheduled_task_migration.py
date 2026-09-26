"""The unified schedule columns land on a database created before they existed."""

import sqlite3

from suzent.database.facade import ChatDatabase

# cron_jobs as it looked before scheduled tasks gained kinds and binding.
LEGACY_SCHEMA = """
CREATE TABLE cron_jobs (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    cron_expr VARCHAR NOT NULL,
    prompt VARCHAR NOT NULL,
    active BOOLEAN NOT NULL,
    delivery_mode VARCHAR NOT NULL,
    model_override VARCHAR,
    last_run_at DATETIME,
    next_run_at DATETIME,
    last_result VARCHAR,
    last_error VARCHAR,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
"""


def test_an_existing_cron_job_survives_the_upgrade(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO cron_jobs (name, cron_expr, prompt, active, delivery_mode, "
        "created_at, updated_at) VALUES "
        "('daily', '0 9 * * *', 'report', 1, 'announce', "
        "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()

    db = ChatDatabase(str(db_path))
    try:
        job = db.list_cron_jobs()[0]

        # The row keeps working, and reads as the isolated cron task it was.
        assert job.name == "daily"
        assert job.cron_expr == "0 9 * * *"
        assert job.schedule_kind == "cron"
        assert job.context_mode == "isolated"
        assert job.chat_id is None
        assert job.suppress_ok is False
        assert job.source == "user"
        assert job.catch_up == "skip"
        assert job.jitter_seconds == 0
        assert job.retry_count == 0
    finally:
        db.engine.dispose()


def test_the_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(LEGACY_SCHEMA)
    conn.commit()
    conn.close()

    for _ in range(2):
        db = ChatDatabase(str(db_path))
        db.engine.dispose()

    conn = sqlite3.connect(db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(cron_jobs)")]
    conn.close()

    assert columns.count("chat_id") == 1
    assert "schedule_kind" in columns
