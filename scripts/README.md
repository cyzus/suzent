# Scripts Directory

> ⚠️ **DEPRECATED:** PostgreSQL setup scripts are archived. Suzent now uses **LanceDB** (embedded vector database) which requires no setup or external services.

> 💡 **For new installations:** Simply run Suzent - LanceDB data is automatically created in `data/memory/`

This directory contains utility scripts for Suzent, including archived PostgreSQL migration tools.

## Migration Scripts

### `migrate_memory.py`
Migrates existing memory data from PostgreSQL to LanceDB (one-time migration for existing users).

**Usage:**
```bash
python scripts/migrate_memory.py
```

**Prerequisites:**
- Existing PostgreSQL database with memory data
- PostgreSQL connection details in `.env` (old config)
- Python dependencies installed

**What it does:**
1. Connects to your existing PostgreSQL database
2. Exports all memory blocks and archival memories
3. Imports them into LanceDB at `data/memory/`
4. Preserves all data: timestamps, embeddings, metadata

**After migration:**
- You can safely remove PostgreSQL service
- LanceDB data persists in `data/memory/`
- No external database service needed

---

## Archived PostgreSQL Setup Scripts

The following scripts are **archived** and only relevant for users migrating from old PostgreSQL-based installations:

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

