# Memory System Database Setup Script (PowerShell)
# This script helps you set up PostgreSQL with pgvector for the memory system
# Supports both native PostgreSQL and Docker

$ErrorActionPreference = "Stop"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Suzent Memory System Database Setup" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Function to read .env file
function Read-EnvFile {
    param([string]$Path)

    if (Test-Path $Path) {
        Write-Host "✓ Loading configuration from .env file..." -ForegroundColor Gray
        Get-Content $Path | ForEach-Object {
            $line = $_.Trim()
            # Skip empty lines and comments
            if ($line -and -not $line.StartsWith('#')) {
                # Parse key=value (handle quoted values)
                if ($line -match '^([^=]+)=(.*)$') {
                    $key = $matches[1].Trim()
                    $value = $matches[2].Trim().Trim('"').Trim("'")
                    Set-Item -Path "Env:$key" -Value $value -Force
                }
            }
        }
    } else {
        Write-Host "⚠ No .env file found at: $Path" -ForegroundColor Yellow
        Write-Host "  Using default values or existing environment variables" -ForegroundColor Gray
    }
}

# Read .env file from project root
$envPath = Join-Path $PSScriptRoot ".." ".env"
Read-EnvFile -Path $envPath

# Get values from environment (set by .env or existing env vars)
$DB_USER = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "suzent" }
$DB_PASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "ultra_secret" }
$DB_NAME = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "suzent" }
$DB_HOST = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "localhost" }
$DB_PORT = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5430" }

Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Host: $DB_HOST"
Write-Host "  Port: $DB_PORT"
Write-Host "  Database: $DB_NAME"
Write-Host "  User: $DB_USER"
Write-Host ""

# Check if Docker is available and if there's a postgres container
$dockerAvailable = Get-Command docker -ErrorAction SilentlyContinue
$useDocker = $false

if ($dockerAvailable) {
    $postgresContainer = docker ps --filter "name=postgres" --format "{{.Names}}" 2>$null
    if ($postgresContainer) {
        Write-Host "✓ Found PostgreSQL Docker container: $postgresContainer" -ForegroundColor Green
        $useDocker = $true
        
        # For Docker, we'll use docker exec instead of psql
        $DB_HOST = "localhost"
    }
}

# If not using Docker, check if psql is available
if (-not $useDocker) {
    $psqlPath = Get-Command psql -ErrorAction SilentlyContinue

    if (-not $psqlPath) {
        Write-Host "❌ PostgreSQL (psql) not found and no Docker container detected!" -ForegroundColor Red
        Write-Host ""
        Write-Host "Installation options:" -ForegroundColor Yellow
        Write-Host "  1. Install PostgreSQL: https://www.postgresql.org/download/windows/" -ForegroundColor White
        Write-Host "  2. Or use Docker (recommended):" -ForegroundColor White
        Write-Host ""
        Write-Host "     docker run -d --name suzent-postgres ``" -ForegroundColor Cyan
        Write-Host "       -e POSTGRES_USER=$DB_USER ``" -ForegroundColor Cyan
        Write-Host "       -e POSTGRES_PASSWORD=$DB_PASSWORD ``" -ForegroundColor Cyan
        Write-Host "       -e POSTGRES_DB=$DB_NAME ``" -ForegroundColor Cyan
        Write-Host "       -p ${DB_PORT}:5432 ``" -ForegroundColor Cyan
        Write-Host "       pgvector/pgvector:pg18" -ForegroundColor Cyan
        Write-Host ""
        exit 1
    }
    
    Write-Host "✓ PostgreSQL client found" -ForegroundColor Green
}

# Set password for psql commands
$env:PGPASSWORD = $DB_PASSWORD

# Check if database exists and create if needed
Write-Host ""
Write-Host "Checking database..." -ForegroundColor Cyan

try {
    if ($useDocker) {
        # For Docker, use docker exec
        $containerName = docker ps --filter "name=postgres" --format "{{.Names}}" | Select-Object -First 1
        $dbExists = docker exec $containerName psql -U $DB_USER -lqt | Select-String -Pattern "\b$DB_NAME\b" -Quiet
        
        if ($dbExists) {
            Write-Host "✓ Database '$DB_NAME' exists" -ForegroundColor Green
        } else {
            Write-Host "Creating database '$DB_NAME'..." -ForegroundColor Yellow
            docker exec $containerName createdb -U $DB_USER $DB_NAME
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Database created" -ForegroundColor Green
            } else {
                Write-Host "❌ Failed to create database" -ForegroundColor Red
                exit 1
            }
        }
    } else {
        # Native PostgreSQL
        $dbExists = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -lqt postgres 2>$null | Select-String -Pattern "\b$DB_NAME\b" -Quiet

        if ($dbExists) {
            Write-Host "✓ Database '$DB_NAME' exists" -ForegroundColor Green
        } else {
            Write-Host "Creating database '$DB_NAME'..." -ForegroundColor Yellow
            createdb -h $DB_HOST -p $DB_PORT -U $DB_USER $DB_NAME
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Database created" -ForegroundColor Green
            } else {
                Write-Host "❌ Failed to create database" -ForegroundColor Red
                exit 1
            }
        }
    }
} catch {
    Write-Host "❌ Error checking/creating database: $_" -ForegroundColor Red
    exit 1
}

# Run schema
$SCHEMA_FILE = Join-Path $PSScriptRoot ".." "src" "suzent" "memory" "schema.sql"

if (-not (Test-Path $SCHEMA_FILE)) {
    Write-Host "❌ Schema file not found: $SCHEMA_FILE" -ForegroundColor Red
    Write-Host "Please run this script from the project root directory" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Running schema.sql..." -ForegroundColor Cyan

try {
    if ($useDocker) {
        Get-Content $SCHEMA_FILE | docker exec -i $containerName psql -U $DB_USER -d $DB_NAME
    } else {
        psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $SCHEMA_FILE
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Schema applied successfully" -ForegroundColor Green
    } else {
        Write-Host "⚠ Schema may have been partially applied (some errors occurred)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Error applying schema: $_" -ForegroundColor Red
    exit 1
}

# Verify pgvector extension
Write-Host ""
Write-Host "Verifying pgvector extension..." -ForegroundColor Cyan

try {
    if ($useDocker) {
        $version = docker exec $containerName psql -U $DB_USER -d $DB_NAME -tAc "SELECT extversion FROM pg_extension WHERE extname = 'vector';" 2>$null
    } else {
        $version = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT extversion FROM pg_extension WHERE extname = 'vector';" 2>$null
    }
    
    if ($version) {
        Write-Host "✓ pgvector extension version: $version" -ForegroundColor Green
        
        if ([version]$version -lt [version]"0.7.0") {
            Write-Host "⚠ pgvector version is below 0.7.0 (has 2000 dimension limit for indexes)" -ForegroundColor Yellow
            Write-Host "  Consider upgrading to pgvector 0.7.0+ for >2000 dimension support" -ForegroundColor Gray
        }
    } else {
        Write-Host "⚠ Could not verify pgvector version" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ Could not verify pgvector: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "✓ Memory system database setup complete!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Connection string:" -ForegroundColor Yellow
Write-Host "  postgresql://${DB_USER}:****@${DB_HOST}:${DB_PORT}/${DB_NAME}" -ForegroundColor White
Write-Host ""
Write-Host "Environment variables (add to .env):" -ForegroundColor Yellow
Write-Host "  POSTGRES_HOST=$DB_HOST" -ForegroundColor White
Write-Host "  POSTGRES_PORT=$DB_PORT" -ForegroundColor White
Write-Host "  POSTGRES_DB=$DB_NAME" -ForegroundColor White
Write-Host "  POSTGRES_USER=$DB_USER" -ForegroundColor White
Write-Host "  POSTGRES_PASSWORD=ultra_secret" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Ensure Python dependencies are installed: uv sync" -ForegroundColor White
Write-Host "  2. Configure your embedding model in config/default.yaml" -ForegroundColor White
Write-Host "  3. Test the setup: python -m suzent.memory.demo" -ForegroundColor White
Write-Host ""
