# Suzent Setup Script for Windows

Write-Host "🤖 Waking up SUZENT..." -ForegroundColor Cyan

# 1. Check Prerequisites
function Check-Command($cmd, $name) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$name is not installed. Please install it and try again."
        exit 1
    }
}

Check-Command "git" "Git"
Check-Command "node" "Node.js"

# 2. Install uv if missing
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" + [System.Environment]::GetEnvironmentVariable("Path","Machine")
}

# 3. Clone Repo (if needed)
$repoUrl = "https://github.com/cyzus/suzent.git"
$dirName = "suzent"

if (-not (Test-Path ".git")) {
    if (-not (Test-Path $dirName)) {
        Write-Host "Cloning Suzent..." -ForegroundColor Yellow
        git clone $repoUrl
    }
    Set-Location $dirName
}

# 4. Setup .env
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from template..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "IMPORTANT: Please edit .env with your API keys!" -ForegroundColor Red
}

# 5. Install Backend Dependencies
Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
uv sync

# 6. Install Frontend Dependencies
Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
Set-Location "frontend"
npm install
Set-Location ..

Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "To start Suzent, run:"
Write-Host "  scripts\start-tauri-dev.ps1" -ForegroundColor Cyan
