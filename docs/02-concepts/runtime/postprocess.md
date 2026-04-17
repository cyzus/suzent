# Chat Post-Processing

When an agent turn finishes, Suzent runs a series of background tasks — writing the transcript, updating memory, compressing context, and saving state. This page explains how that works and what to do when something goes wrong.

## Why it runs in the background

Saving state after a turn involves several steps that can take a few seconds each (memory extraction, context compression). Rather than making you wait, Suzent closes the stream immediately and handles those steps in the background. You can send your next message right away.

## Two phases

### Phase A: Quick snapshot

As soon as the agent finishes streaming, Suzent saves a lightweight snapshot of the conversation — just enough that if you send another message before the background work completes, the new turn still has the full history to work with.

### Phase B: Background job

In parallel, a background job runs through these steps in order:

| Step | What it does |
|---|---|
| **Transcript** | Appends the turn to a JSONL log file on disk |
| **Memory** | Extracts and indexes any facts worth remembering |
| **Compression** | Trims the context window if it's getting large |
| **Persistence** | Writes the final conversation state to the database |

Each step records whether it succeeded or failed, so it's easy to see exactly where something went wrong.

## Fast-follow turns

If you send another message before the background job finishes, Suzent detects the overlap and skips the stale write — the newer turn's job takes over. This is expected and harmless. The quick snapshot from Phase A means no history is lost.

## Retries

Failed jobs can be retried up to 3 times. A job is only eligible for retry if it failed (not if it was intentionally skipped as stale).

## Troubleshooting

### Something feels off with message history

Check whether the most recent job for that chat succeeded:

```python
from suzent.database import get_database

db = get_database()
jobs = db.list_postprocess_jobs("your-chat-id", limit=5)

for job in jobs:
    icon = "✓" if job.outcome == "success" else "✗"
    print(f"{icon} {job.job_id[:8]}  {job.outcome or job.status}  {job.duration_ms}ms")
    if job.error_message:
        print(f"   {job.error_message}")
```

### Jobs are failing consistently

Find which step is failing:

```python
import json

for job in db.list_postprocess_jobs("your-chat-id", limit=20):
    if job.step_status_json:
        steps = json.loads(job.step_status_json)
        for step, info in steps.items():
            if info["status"] == "failed":
                print(f"{job.job_id[:8]}  {step}: {info.get('error', '')[:80]}")
```

Common causes:

- **Transcript step** — disk full or the transcript directory isn't writable
- **Memory step** — embedding model unavailable; check that memory is enabled in config
- **Compression step** — usually a malformed message in the conversation history
- **Persistence step** — database write error; run `sqlite3 chats.db "PRAGMA integrity_check;"` to verify

To queue eligible jobs for retry:

```python
for job in db.get_retriable_postprocess_jobs():
    db.prepare_job_for_retry(job.job_id)
```

### A lot of "skipped stale" jobs

This is normal under heavy use — it just means you were sending messages faster than the background job could finish. As long as the most recent job succeeded, nothing was lost.

### Overall health check

```python
metrics = db.get_postprocess_metrics()
started = metrics["job_started"]

if started > 0:
    print(f"Success:  {metrics['job_success'] / started * 100:.0f}%")
    print(f"Failed:   {metrics['job_failed'] / started * 100:.0f}%")
    print(f"Stale:    {metrics['job_skipped_stale'] / started * 100:.0f}%")
```

A failure rate above ~5% is worth investigating. A stale rate of 10–30% is normal for active use.

## Useful SQL

If you need to dig into the database directly:

```sql
-- Recent jobs for a specific chat
SELECT job_id, status, outcome, duration_ms, error_message
FROM postprocess_jobs
WHERE chat_id = 'your-chat-id'
ORDER BY created_at DESC
LIMIT 10;

-- Jobs currently running (anything here for > 5 min is stuck)
SELECT job_id, chat_id, started_at
FROM postprocess_jobs
WHERE status = 'running';

-- Success rate over the last 24 hours
SELECT
  ROUND(100.0 * SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_pct,
  COUNT(*) AS total
FROM postprocess_jobs
WHERE finished_at > datetime('now', '-1 day');
```
