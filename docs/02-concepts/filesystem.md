# Filesystem & Execution

Suzent provides secure file access and code execution through two modes: **Sandbox Mode** (isolated Docker container) and **Host Mode** (direct execution with restrictions).

## Execution Modes

| Mode | BashTool | File Tools | Path Style |
|------|----------|------------|------------|
| **Sandbox** | Runs in Docker container | Virtual filesystem | `/persistence`, `/shared`, `/mnt/*` |
| **Host** | Runs on host | Host filesystem | `$PERSISTENCE_PATH`, `$SHARED_PATH`, `$MOUNT_*` |

Toggle sandbox in the chat settings panel when creating a conversation.

---

## Virtual Filesystem (Both Modes)

| Virtual Path | Maps To | Purpose |
|-------------|---------|---------|
| `/persistence` | `.suzent/sandbox/sessions/{chat_id}/` | Per-chat storage |
| `/shared` | `.suzent/sandbox/shared/` | Shared across all chats |
| `/uploads` | `.suzent/sandbox/sessions/{chat_id}/uploads/` | Uploaded files |
| `/mnt/*` | Custom volumes | Host directories |

**Relative paths** default to `/persistence`: `data.csv` → `/persistence/data.csv`

### Custom Volume Mounts

```yaml
# config/default.yaml
sandbox_volumes:
  - "D:/datasets:/data"
  - "D:/skills:/mnt/skills"
```

Now `/data/file.csv` maps to `D:/datasets/file.csv` on your host.

---

## Sandbox Mode

Uses Docker containers for isolated execution. Each chat session gets its own named container (`suzent-sandbox-{id}`) that starts on first use and is kept running for the duration of the session.

### Features
- **Isolation**: Each session runs in its own container (network access on by default via `bridge`)
- **Persistent data**: `/persistence` and `/shared` are bind-mounted from the host — data survives container restarts and removal
- **Auto-healing**: Automatically restarts the container if it crashes
- **Multi-language**: Python, Node.js (with custom image), shell commands
- **Resource limits**: 512 MB memory, 1 CPU, 256 process limit

### Requirements

- **Docker Desktop** (Windows/macOS) or Docker Engine (Linux)
- No KVM, no privileged mode, no extra services required

### Setup

1. Ensure Docker Desktop is running

2. Enable sandbox in the chat config panel (sidebar), or set globally in `config/default.yaml`:

```yaml
sandbox_enabled: true
```

3. *(Optional)* Change the container image:

```yaml
# Default — Python + bash only
sandbox_image: python:3.11-slim

# Custom image — Python + Node.js + common packages (see below)
sandbox_image: suzent-sandbox
```

### Custom Sandbox Image (Python + Node.js)

The default `python:3.11-slim` image covers Python and shell commands. For Node.js support and pre-installed packages (numpy, pandas, requests, etc.), build the custom image:

```bash
docker compose -f docker/sandbox-compose.yml build
```

Then set `sandbox_image: suzent-sandbox` in `config/default.yaml`.

### Calling Suzent from Inside the Sandbox

`SUZENT_BASE_URL` is injected automatically so sandboxed code can reach the running host server. This lets agent-written scripts do everything the `suzent` CLI can do, without the CLI being installed.

| Variable | Example value |
|----------|---------------|
| `SUZENT_BASE_URL` | `http://host.docker.internal:25314` |

**CLI → API mapping:**

| CLI command | HTTP equivalent |
|-------------|----------------|
| `suzent cron list` | `GET  $SUZENT_BASE_URL/cron/jobs` |
| `suzent cron add ...` | `POST $SUZENT_BASE_URL/cron/jobs` |
| `suzent cron trigger {id}` | `POST $SUZENT_BASE_URL/cron/jobs/{id}/trigger` |
| `suzent cron remove {id}` | `DELETE $SUZENT_BASE_URL/cron/jobs/{id}` |
| `suzent nodes list` | `GET  $SUZENT_BASE_URL/nodes` |
| `suzent nodes describe {node_id_or_name}` | `GET  $SUZENT_BASE_URL/nodes/{node_id_or_name}` |
| `suzent nodes invoke {node_id_or_name} ...` | `POST $SUZENT_BASE_URL/nodes/{node_id_or_name}/invoke` |
| `suzent agent chat "msg"` | `POST $SUZENT_BASE_URL/chat` (streaming) |
| List chats | `GET  $SUZENT_BASE_URL/chats` |
| Memory search | `GET  $SUZENT_BASE_URL/memory/archival?query=...` |

Example — scheduling a cron job from sandboxed Python:

```python
import os, requests

base = os.environ["SUZENT_BASE_URL"]

requests.post(f"{base}/cron/jobs", json={
    "name": "daily-report",
    "cron_expr": "0 9 * * *",
    "prompt": "Summarize today's activity",
    "delivery_mode": "announce",
})
```

### Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `sandbox_enabled` | `false` | Enable sandbox mode |
| `sandbox_image` | `python:3.11-slim` | Docker image to use |
| `sandbox_network` | `bridge` | Network mode (`bridge` = internet access, `none` = isolated) |
| `sandbox_idle_timeout_minutes` | `30` | Stop idle containers after N minutes (checked every 5 min) |
| `sandbox_setup_command` | `""` | Shell command run once on container creation (login shell) |
| `sandbox_env` | `{}` | Extra env vars injected into container (secrets are blocked) |
| `sandbox_data_path` | `.suzent/sandbox` | Host path for persistent data |
| `sandbox_volumes` | `[]` | Extra bind mounts (`host:container`) |

---

## Host Mode

Executes directly on the host machine with path restrictions.

### Environment Variables

In host mode, use these environment variables in bash commands:

| Variable | Points To |
|----------|-----------|
| `$PERSISTENCE_PATH` | Session directory (same as `pwd`) |
| `$SHARED_PATH` | Shared directory |
| `$MOUNT_SKILLS` | Skills directory |
| `$MOUNT_*` | Other mounted volumes |

### Security

- Working directory (`pwd`) is the session's persistence folder
- Only paths within `.suzent/`, `/persistence`, `/shared`, and custom mounts are allowed
- Source code directories are **blocked** by default

---

## File Tools

### ReadFileTool
Read files with automatic format conversion (text, PDF, DOCX, XLSX, images with OCR).

```python
ReadFileTool(file_path="/persistence/data.csv")
ReadFileTool(file_path="report.pdf", offset=10, limit=50)
```

### WriteFileTool
Create or overwrite files.

```python
WriteFileTool(file_path="/persistence/output.txt", content="Hello")
```

> [!WARNING]
> Overwrites entire file. Use `EditFileTool` for small changes.

### EditFileTool
Make precise text replacements.

```python
EditFileTool(
    file_path="config.json",
    old_string='"debug": false',
    new_string='"debug": true'
)
```

### GlobTool
Find files by pattern.

```python
GlobTool(pattern="**/*.py")  # All Python files
GlobTool(pattern="*.csv", path="/data")  # CSVs in /data
```

### GrepTool
Search file contents.

```python
GrepTool(pattern="def.*:", path="/persistence")  # Find functions
GrepTool(pattern="TODO", include="*.py")  # TODOs in Python files
```

---

## Security

All paths are validated to prevent directory traversal:

- ✅ `/persistence/data.csv`
- ✅ `/shared/model.pt`
- ✅ `/data/file.txt` (if mounted)
- ❌ `/etc/passwd`
- ❌ `../../../secret`
- ❌ Project source code (in host mode)

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **File not found** | Check `.suzent/sandbox/sessions/{chat_id}/` on the host |
| **Path traversal error** | Ensure path is within allowed directories |
| **Volume not accessible** | Verify `sandbox_volumes` in config |
| **Container fails to start** | Check Docker Desktop is running (`docker ps`) |
| **Node.js not found** | Build the custom image: `docker compose -f docker/sandbox-compose.yml build`, set `sandbox_image: suzent-sandbox` |
| **Internet in sandbox** | Ensure `sandbox_network: bridge` (default) — `none` fully isolates |
