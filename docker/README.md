# Docker Compose Setup

This Docker Compose configuration provides all the infrastructure services needed for Suzent:

- **Redis (Valkey)** - Cache for SearXNG
- **SearXNG** - Privacy-respecting metasearch engine

The memory system now uses **LanceDB** (embedded vector database), which requires no separate service - data is stored in the mounted `data/memory` volume.

## Quick Start

### 1. Configure Environment

The Docker Compose setup uses the `.env` file from the project root. Make sure you have it configured:

```bash
# Copy example if needed
cp .env.example .env

# Edit configuration
nano .env  # or use your preferred editor

docker compose -f docker/docker-compose.yml up -d
```

## Sandbox (Optional)

The sandbox provides isolated Python code execution for the agent. 

### Windows

It requires:
- WSL2 with nested virtualization enabled
- KVM support (`/dev/kvm`)

**Optimized Startup**: The first run will build a custom image with pre-installed dependencies and kernels (Python/Node.js). usage:

```bash
# Start sandbox server (separate from main services)
# docker compose -f docker/sandbox-compose.yml up -d 
# or if you have an override file:
docker compose -f docker/sandbox-compose.yml -f docker/sandbox-compose.override.yml up -d

# Check logs
docker logs suzent-microsandbox --tail 50
```

### Linux / MacOS


```bash
curl -sSL https://get.microsandbox.dev | sh

msb server start --dev

msb pull microsandbox/python
```


### Config


Enable sandbox in `config/default.yaml`:
```yaml
sandbox_enabled: true
```
