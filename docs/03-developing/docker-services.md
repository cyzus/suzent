# Docker Services (Optional)

This document describes optional Docker configurations for auxiliary services.

> **Note**: The core application does NOT require Docker. Docker is only needed if you want sandbox mode or the optional search/cache services.

## Auxiliary Services

**`services.yml`** provides:
- **Redis (Valkey)**: Caching
- **SearXNG**: Privacy-respecting metasearch engine (Suzent falls back to `ddgs` if not available)

```bash
docker compose -f docker/services.yml up -d
```

Ensure your `.env` file is configured (copy from `.env.example`).

---

## Sandbox

The sandbox system runs code in isolated Docker containers managed directly by the Python backend — no separate server process needed.

### Requirements

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- No KVM, no privileged mode, no WSL network tricks required

### Quick Start

1. Start Docker Desktop
2. Enable sandbox in the chat config panel (sidebar toggle), or set in `config/default.yaml`:

```yaml
sandbox_enabled: true
```

That's it. The first execution will pull `python:3.11-slim` and start the container automatically.

### Custom Image (Python + Node.js)

For Node.js support and pre-installed packages (numpy, pandas, requests, etc.):

```bash
docker compose -f docker/sandbox-compose.yml build
```

Then in `config/default.yaml`:

```yaml
sandbox_image: suzent-sandbox
```

### How It Works

- Each chat session gets its own container named `suzent-sandbox-{id}`
- The container runs `sleep infinity` and commands are exec'd into it
- `/persistence` and `/shared` are bind-mounted from the host — data persists across container restarts
- Containers are stopped when the chat session ends, and cleaned up on app restart
- Security: dropped capabilities, no privilege escalation, memory/CPU limits
- Network: `bridge` by default (internet access); set `sandbox_network: none` to fully isolate
- `SUZENT_BASE_URL` is injected automatically so sandboxed code can call the host server's REST API via `host.docker.internal` — a full replacement for the `suzent` CLI
