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

# 1.5. Check/Install Rust
if (-not (Get-Command "cargo" -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️  Rust (cargo) not found!" -ForegroundColor Yellow
    Write-Host "   Installing Rust via rustup-init..." -ForegroundColor Cyan
    
    $exe = "$env:TEMP\rustup-init.exe"
    try {
        Invoke-WebRequest "https://win.rustup.rs/x86_64" -OutFile $exe
        Start-Process -FilePath $exe -ArgumentList "-y" -Wait
        
        # Add to PATH for current session
        $cargo_bin = "$env:USERPROFILE\.cargo\bin"
        if (Test-Path $cargo_bin) {
            $env:Path = "$cargo_bin;$env:Path"
            Write-Host "✅ Rust installed and added to PATH." -ForegroundColor Green
        }
    } catch {
        Write-Error "Failed to install Rust automatically. Please install it manually from https://rustup.rs/"
        exit 1
    }
}

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
# 8. Check for C++ Build Tools (Linker)
if (-not (Get-Command "link.exe" -ErrorAction SilentlyContinue)) {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $installed = $false
    
    if (Test-Path $vswhere) {
        $output = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($output) {
            $installed = $true
            Write-Host "⚠️  C++ Build Tools detected at: $output" -ForegroundColor Yellow
            Write-Host "   However, 'link.exe' is not in your PATH."
            Write-Host "   Rust builds might fail unless you run from a Developer Command Prompt or add it to PATH."
            Write-Host "   Skipping auto-installer as tools are present." -ForegroundColor Green
        }
    }

    if (-not $installed) {
        Write-Host "⚠️  C++ Linker (link.exe) not found!" -ForegroundColor Yellow
        Write-Host "   This is required for compiling Rust dependencies."
        Write-Host "   Running auto-installer..." -ForegroundColor Cyan
        
        # We use 'uv run suzent' because 'suzent' might not be in the current shell's PATH yet
        uv run suzent setup-build-tools

        Write-Host "⚠️  Please RESTART your terminal after installation to ensure the linker is in PATH." -ForegroundColor Yellow
    }
}

Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "To start Suzent, run:"
Write-Host "  suzent start" -ForegroundColor Cyan
