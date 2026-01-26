# Docker Services

This directory contains optional Docker configurations for auxiliary services used during development or for enhanced privacy.

## Available Services

**`services.yml`** provides:
- **Redis (Valkey)**: Caching
- **SearXNG**: Privacy-respecting metasearch engine (Optional, Suzent falls back to `ddgs` if not available)

## Usage

To run these services locally:

```bash
docker compose -f docker/services.yml up -d
```

Ensure your `.env` file is configured (copy from `.env.example`).

## Sandbox

The `microsandbox` is used for isolated Python execution.

### Windows

Requires WSL2 and KVM.

```bash
docker compose -f docker/sandbox-compose.yml up -d
```

### Linux / macOS

We recommend using the standard installation script:

```bash
curl -sSL https://get.microsandbox.dev | sh
msb server start --dev
```
