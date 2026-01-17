# Sandbox Module

The Sandbox module provides secure, isolated code execution environments using **Microsandbox** (Firecracker MicroVMs). It allows agents to execute Python, Node.js, and shell commands safely with persistent storage.

When creating an agent conversation, you can toggle **Sandbox Execution**. 

- **Enabled**: The agent is equipped with a `BashTool` that executes commands *inside* the secure microVM. File operations (`ReadFileTool`, `WriteFileTool`, etc.) will also target the sandbox filesystem.
- **Disabled**: The `BashTool` is removed. File operations target the host's local filesystem (restricted to the workspace).

## Features

- **Dynamic Integration**: The `BashTool` is automatically added/removed based on the chat's sandbox setting.
- **Isolation**: Each session runs in its own Firecracker MicroVM.
- **Persistence**: Per-chat storage at `/persistence` is preserved across restarts.
- **Shared Storage**: Global storage at `/shared` accessible by all sessions.
- **Auto-Healing**: Automatically detects crashes/timeouts and restarts sessions.
- **Custom Volumes**: Mount host directories for access to local files (e.g., datasets).
- **File Uploads**: Drag-and-drop file support directly into the sandbox via the frontend sidebar.

## Prerequisites

1.  **Docker**: Required to run the `microsandbox` service.
2.  **Python Dependencies**: `httpx` (for efficient RPC calls).

## Setup

### 1. Docker Compose (Windows/WSL2 Support)

To enable volume mounting on Windows (via WSL2), you must map the host paths to the container's expected structure.

Update your `docker/sandbox-compose.yml`:

```yaml
services:
  microsandbox:
    image: microsandbox/microsandbox:latest
    privileged: true
    volumes:
      # Data persistence
      - microsandbox-data:/root/.local/share/microsandbox
      
      # Project workspace
      - ..:/workspace
      
      # [WINDOWS-SPECIFIC] Mount users directory for custom volume access
      # This maps C:\Users on host to /mnt/c/Users in container
      # Required for SandboxManager to mount host files into MicroVMs
      - C:/Users:/mnt/c/Users
```

> [!IMPORTANT]
> Do **NOT** use the `:ro` (read-only) flag if you want the sandbox to be able to write files back to your host system (e.g., saving generated artifacts).

### 2. Configuration (`config/default.yaml`)

Configure the sandbox connection and default volumes in your configuration file:

```yaml
# Sandbox Server URL
sandbox_server_url: "http://localhost:7263"  # or your WSL2 IP if running properly

# Custom Volume Mounts
# Format: "host_path:container_path"
sandbox_volumes:
  - "D:/data:/data"
```

> **Note**: On Windows, always use forward slashes (`/`) in paths. The `SandboxManager` automatically handles the path translation if the Docker volume mapping (`C:/Users` -> `/mnt/c/Users`) is set up correctly.

## Usage

### Basic Execution

```python
from suzent.sandbox import SandboxManager, Language

# Use as a context manager for automatic cleanup
async with SandboxManager() as manager:
    # Execute Python
    result = manager.execute(
        session_id="chat-123",
        content="print('Hello from Sandbox!')"
    )
    print(result.output)

    # Execute Shell Command
    cmd_result = manager.execute(
        session_id="chat-123",
        content="ls -la /persistence",
        language=Language.COMMAND
    )
```

### Persistence

-   **`/persistence`**: Files written here survive session restarts. Use this for user-specific data.
-   **`/shared`**: Files written here are visible to ALL sessions. Use this for common datasets or tools.

```python
# Write to persistent storage
manager.execute("chat-123", "with open('/persistence/note.txt', 'w') as f: f.write('Saved!')")

# Read back later (even after restart)
manager.execute("chat-123", "print(open('/persistence/note.txt').read())")
```

## Troubleshooting

### `TimeoutError` or `ConnectionRefused`
- Only `httpx` is supported for RPC calls. Ensure `sandbox_server_url` matches your running `microsandbox` instance.
- If running on Windows/WSL2, `localhost` might not work from outside WSL. Use the WSL IP address in `config/default.yaml`.

### Volume Mount Fails
- Ensure `C:/Users/...` is mapped to `/mnt/c/Users/...` in `docker-compose.yml`.
- Check that the target path inside the sandbox (e.g., `/data`) does not conflict with existing system paths.
- Remove `:ro` from `docker-compose.yml` if you get "Read-only file system" errors.

### Node.js Errors
- If you see `500 Internal Server Error` when running Node.js, the sandbox image might not support it. The system handles this by skipping tests, but for usage, switch to a supported image.
