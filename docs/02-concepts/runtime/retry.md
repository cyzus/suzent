# Retry

Retry re-runs the last user message from scratch, rolling back all changes the agent made during that turn.

## How to trigger

| Surface | Action |
|---------|--------|
| **Frontend** | Click the retry icon (↺) next to the copy button on any assistant response |
| **Social channels** | Send `/retry` in the active thread |

Retry is only available after at least one completed turn. While the agent is streaming a response the retry button is hidden.

## What gets rolled back

Before every turn Suzent automatically snapshots the following:

| What | Where |
|------|-------|
| Agent message history | Database (`agent_state`) |
| Display messages (chat UI) | Database (`messages`) |
| Sandbox session files | `sandbox/sessions/{chat_id}/` |
| Custom volume host directories | Each `host_path` in `sandbox_volumes` |

On retry all four are restored to their pre-turn state and `process_turn()` is called again with the original user message and files.

## What is NOT rolled back

| What | Why |
|------|-----|
| `/shared` | Shared across all chats — rolling it back for one chat would corrupt state (including memories) produced by other concurrent sessions |
| `/mnt/skills` | Read-only mount; the agent never writes here |

If the agent modified files in `/shared` during a turn and you retry, those changes remain in place.

## Checkpoint storage

Checkpoints are stored on disk under `sandbox/checkpoints/{chat_id}/`:

```
sandbox/checkpoints/{chat_id}/
  session/            ← copy of sandbox/sessions/{chat_id}/
  volumes/
    0/                ← copy of first custom-volume host dir
    1/                ← copy of second custom-volume host dir
  volume_map.json     ← [{host_path, container_path}, ...]
```

Only the **most recent** checkpoint is kept per chat — it is overwritten at the start of each new turn. This means you can only retry the last turn.

## Limitations

- **One level deep** — retry restores to the start of the immediately preceding turn only; there is no multi-step undo history.
- **Large volumes** — custom volumes are copied in full on every turn. If you have very large directories mounted, consider whether they need to be in `sandbox_volumes` or whether a more targeted mount (e.g. a specific subdirectory) would be more appropriate.
- **`/shared` changes** — see above; use `git` or manual backups if you need rollback for shared files.
