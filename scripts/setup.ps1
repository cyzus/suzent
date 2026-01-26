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

# 7. Add to PATH (Global CLI)
$scriptsDir = Join-Path (Get-Location) "scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($currentPath -notlike "*$scriptsDir*") {
    Write-Host "Adding $scriptsDir to PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$scriptsDir", "User")
    $env:Path += ";$scriptsDir"
    Write-Host "✅ Added 'suzent' command to PATH" -ForegroundColor Green
}

# 8. Check for C++ Build Tools (Linker)
if (-not (Get-Command "link.exe" -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  C++ Linker (link.exe) not found!" -ForegroundColor Yellow
    Write-Host "   This is required for compiling Rust dependencies."
    Write-Host "   Running auto-installer..." -ForegroundColor Cyan
    
    # We use 'uv run suzent' because 'suzent' might not be in the current shell's PATH yet
    uv run suzent setup-build-tools

    Write-Host "⚠️  Please RESTART your terminal after installation to ensure the linker is in PATH." -ForegroundColor Yellow
}

Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "To start Suzent, run:"
Write-Host "  suzent start" -ForegroundColor Cyan
