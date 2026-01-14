# Docker Compose Setup

This Docker Compose configuration provides all the infrastructure services needed for Suzent:

- **PostgreSQL 18 + pgvector** - Memory system database
- **Redis (Valkey)** - Cache for SearXNG
- **SearXNG** - Privacy-respecting metasearch engine

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

The sandbox provides isolated Python code execution for the agent. It requires:
- WSL2 with nested virtualization enabled
- KVM support (`/dev/kvm`)

```bash
# Start sandbox server (separate from main services)
docker compose -f docker/sandbox-compose.yml up -d

# Check logs
docker logs suzent-microsandbox --tail 50
```

Enable sandbox in `config/default.yaml`:
```yaml
sandbox_enabled: true
```
