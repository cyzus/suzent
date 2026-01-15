# Scripts Directory

> 💡 **Most users should use Docker Compose** (see [`docker/README.md`](../docker/README.md)) for the easiest setup. These scripts are for advanced users with existing PostgreSQL installations (native, managed services like AWS RDS, etc.).

This directory contains utility scripts for manually setting up the Suzent memory system database.

## Setup Scripts

### `setup_memory_db.ps1` / `setup_memory_db.sh`
Sets up a PostgreSQL database with pgvector extension for the memory system.

**Usage (PowerShell):**
```powershell
.\scripts\setup_memory_db.ps1
```

**Usage (Bash):**
```bash
./scripts/setup_memory_db.sh
```

**Prerequisites:**
- PostgreSQL with pgvector extension installed (or Docker)
- Environment variables configured in `.env`:
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`
  - `POSTGRES_USER`, `POSTGRES_PASSWORD`

**What it does:**
1. Reads configuration from `.env` file
2. Creates the database if it doesn't exist
3. Runs `src/suzent/memory/schema.sql` to create tables and indexes
4. Enables pgvector and other required extensions

## Configuration

All scripts use the `.env` file in the project root for configuration. Required variables:

```bash
# PostgreSQL Connection
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5430
POSTGRES_DB=suzent
POSTGRES_USER=suzent
POSTGRES_PASSWORD=ultra_secret

```

**Note:** Use `127.0.0.1` instead of `localhost` on Windows to avoid IPv6 connection delays.

## When to Use These Scripts

**Use Docker Compose** (recommended) if:
- You want the easiest setup experience
- You're setting up a development environment
- You need SearXNG + PostgreSQL + Redis together

**Use these scripts** if:
- You already have PostgreSQL installed natively
- You're using a managed PostgreSQL service (AWS RDS, Azure, etc.)
- You prefer not to use Docker
- You need to initialize the schema on an existing database

## Troubleshooting

### Connection Issues
- Verify PostgreSQL is running: `docker ps` or `Get-Service postgresql*`
- Check port is correct in `.env`
- Use `127.0.0.1` instead of `localhost` to avoid IPv6 delays on Windows
- Ensure firewall allows connections

### Schema Already Exists
- Scripts will skip if tables already exist
- To recreate: manually drop tables first, then re-run script

