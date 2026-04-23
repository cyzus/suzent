# SUZENT Setup & Update Script for Windows
# Usage:
#   Fresh install:  powershell -c "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
#   Update:         suzent update   (or re-run this script inside the repo)
# Flags (env vars): $env:SUZENT_DIR, $env:SUZENT_BRANCH, $env:SUZENT_SKIP_PLAYWRIGHT

param(
    [string]$Dir    = "",
    [string]$Branch = "",
    [switch]$SkipPlaywright,
    [switch]$Update
)

$ErrorActionPreference = "Stop"

# ── Resolve config ────────────────────────────────────────────────────────────
$SuzentDir    = if ($Dir)    { $Dir }    elseif ($env:SUZENT_DIR)    { $env:SUZENT_DIR }    else { Join-Path $env:USERPROFILE "suzent" }
$SuzentBranch = if ($Branch) { $Branch } elseif ($env:SUZENT_BRANCH) { $env:SUZENT_BRANCH } else { "main" }
$SkipPW       = $SkipPlaywright -or ($env:SUZENT_SKIP_PLAYWRIGHT -eq "1")
$RepoUrl      = "https://github.com/cyzus/suzent.git"
$MinNodeMajor = 20

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Ok   { param($m) Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Info { param($m) Write-Host " [*] $m" -ForegroundColor Cyan }
function Write-Warn { param($m) Write-Host " [!] $m" -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host "[ERR] $m" -ForegroundColor Red; exit 1 }

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
}

function Add-ToUserPath {
    param([string]$NewDir)
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($current -split ";" | Where-Object { $_ -ieq $NewDir })) { return }
    [Environment]::SetEnvironmentVariable("Path", "$current;$NewDir", "User")
    $env:Path = "$env:Path;$NewDir"
    Write-Warn "Added $NewDir to user PATH (restart terminal if command not found)"
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ███████╗██╗   ██╗███████╗███████╗███╗   ██╗████████╗" -ForegroundColor Cyan
Write-Host "  ██╔════╝██║   ██║╚══███╔╝██╔════╝████╗  ██║╚══██╔══╝" -ForegroundColor Cyan
Write-Host "  ███████╗██║   ██║  ███╔╝ █████╗  ██╔██╗ ██║   ██║   " -ForegroundColor Cyan
Write-Host "  ╚════██║██║   ██║ ███╔╝  ██╔══╝  ██║╚██╗██║   ██║   " -ForegroundColor Cyan
Write-Host "  ███████║╚██████╔╝███████╗███████╗██║ ╚████║   ██║   " -ForegroundColor Cyan
Write-Host "  ╚══════╝ ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   " -ForegroundColor Cyan
Write-Host ""

# ── Detect update vs fresh install ───────────────────────────────────────────
$IsUpdate = (Test-Path (Join-Path $SuzentDir ".git"))

Write-Ok "Windows detected"

# ── Check/install: git ────────────────────────────────────────────────────────
function Ensure-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) { return }

    Write-Info "git not found — attempting install via winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git --source winget --accept-package-agreements --accept-source-agreements --silent
        Refresh-Path
        if (Get-Command git -ErrorAction SilentlyContinue) {
            Write-Ok "git installed via winget"
            return
        }
    }
    Write-Fail "git is required. Install from https://git-scm.com/download/win and re-run."
}

Ensure-Git
Write-Ok "git $(git --version)"

# ── Check/install: Node.js ────────────────────────────────────────────────────
function Get-NodeMajor {
    try {
        $v = (node --version 2>$null) -replace '^v', ''
        return [int]($v.Split('.')[0])
    } catch { return 0 }
}

function Ensure-Node {
    $major = Get-NodeMajor
    if ($major -ge $MinNodeMajor) {
        Write-Ok "Node.js v$(node --version) found"
        return
    }
    if ($major -gt 0) {
        Write-Warn "Node.js v$(node --version) is below required v$MinNodeMajor"
    } else {
        Write-Info "Node.js not found — installing..."
    }

    # Try winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install OpenJS.NodeJS.LTS --source winget --accept-package-agreements --accept-source-agreements --silent
        Refresh-Path
        if ((Get-NodeMajor) -ge $MinNodeMajor) {
            Write-Ok "Node.js installed via winget"
            return
        }
        Write-Warn "winget install completed, but Node.js is still unavailable in this shell"
        Write-Warn "Close and reopen PowerShell, then re-run this script."
        exit 1
    }

    # Try Chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install nodejs-lts -y
        Refresh-Path
        if ((Get-NodeMajor) -ge $MinNodeMajor) { Write-Ok "Node.js installed via Chocolatey"; return }
    }

    # Try Scoop
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        scoop install nodejs-lts
        Refresh-Path
        if ((Get-NodeMajor) -ge $MinNodeMajor) { Write-Ok "Node.js installed via Scoop"; return }
    }

    Write-Host ""
    Write-Fail "Could not auto-install Node.js. Please install v${MinNodeMajor}+ from https://nodejs.org/ and re-run."
}

Ensure-Node

# ── Check/install: uv ────────────────────────────────────────────────────────
function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) { return }
    Write-Info "Installing uv..."
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    Refresh-Path
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Fail "uv installation failed. See https://docs.astral.sh/uv/"
    }
    Write-Ok "uv installed"
}

Ensure-Uv
Write-Ok "uv $(uv --version)"

# ── Clone or update repo ──────────────────────────────────────────────────────
if ($IsUpdate) {
    Write-Info "Updating SUZENT in $SuzentDir..."
    Set-Location $SuzentDir

    # Stash local changes
    $status = git status --porcelain 2>$null
    if ($status) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        Write-Warn "Stashing local changes (suzent-update-$stamp)..."
        git stash push -m "suzent-update-$stamp"
    }

    git fetch origin
    git checkout $SuzentBranch 2>$null
    git pull origin $SuzentBranch
    $sha = git rev-parse --short HEAD
    Write-Ok "Repository updated to $sha"
} else {
    if (Test-Path $SuzentDir) {
        Write-Fail "$SuzentDir already exists but is not a git repo. Remove it or set `$env:SUZENT_DIR to a different path."
    }
    Write-Info "Cloning SUZENT into $SuzentDir..."
    git clone --branch $SuzentBranch $RepoUrl $SuzentDir
    Write-Ok "Repository cloned"
    Set-Location $SuzentDir
}

Set-Location $SuzentDir

# ── Setup .env ────────────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Warn "Created .env from template — edit it with your API keys before starting."
    }
} else {
    Write-Ok ".env already exists"
}

# ── Python dependencies ───────────────────────────────────────────────────────
Write-Info "Syncing Python dependencies (uv sync)..."
uv sync
if ($LASTEXITCODE -ne 0) { Write-Fail "uv sync failed — check errors above." }
Write-Ok "Python dependencies ready"

# ── Frontend dependencies ─────────────────────────────────────────────────────
Write-Info "Installing frontend dependencies (npm install)..."
Push-Location "frontend"
npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Fail "npm install failed in frontend/." }
Pop-Location
Write-Ok "Frontend dependencies ready"

# ── src-tauri JS dependencies ─────────────────────────────────────────────────
Write-Info "Installing src-tauri dependencies (npm install)..."
Push-Location "src-tauri"
npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Fail "npm install failed in src-tauri/." }
Pop-Location
Write-Ok "Tauri JS dependencies ready"

# ── Playwright Chromium ───────────────────────────────────────────────────────
if (-not $SkipPW) {
    Write-Info "Installing Playwright Chromium (for web browsing tool)..."
    uv run playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Playwright install failed — web browsing may not work (non-fatal)."
    }
}

# ── Global CLI shim ───────────────────────────────────────────────────────────
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Force -Path $BinDir | Out-Null }

$ShimPath = Join-Path $BinDir "suzent.cmd"
$ShimContent = "@echo off`r`ncd /d `"$SuzentDir`"`r`nuv run suzent %*`r`n"
Set-Content -Path $ShimPath -Value $ShimContent -NoNewline -Encoding ASCII
Write-Ok "CLI shim written to $ShimPath"

Add-ToUserPath $BinDir

# Also add scripts/ dir (legacy, for suzent.ps1 wrapper)
$ScriptsDir = Join-Path $SuzentDir "scripts"
Add-ToUserPath $ScriptsDir

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
if ($IsUpdate) {
    Write-Ok "SUZENT updated successfully!"
    Write-Host ""
    Write-Host "  Run " -NoNewline
    Write-Host "suzent start" -ForegroundColor Cyan -NoNewline
    Write-Host " to launch."
} else {
    Write-Ok "SUZENT installed successfully!"
    Write-Host ""
    Write-Host "  Next: edit " -NoNewline
    Write-Host "$SuzentDir\.env" -ForegroundColor Cyan -NoNewline
    Write-Host " with your API keys, then run:"
    Write-Host "  " -NoNewline
    Write-Host "suzent start" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  If 'suzent' is not found, restart your terminal." -ForegroundColor Yellow
}
Write-Host ""
