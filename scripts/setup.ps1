# Suzent Setup Script for Windows

Write-Host "🤖 Waking up SUZENT..." -ForegroundColor Cyan

# 1. Check Prerequisites
function Check-Command($cmd, $name) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$name is not installed. Please install it and try again."
        exit 1
    }
}

# Helper: refresh PATH from system/user environment so newly-installed tools are visible
function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Check-Command "git" "Git"
Check-Command "node" "Node.js"

# 1.1. Check Node.js version (20+ required)
$nodeVersion = (node --version) -replace '^v', ''
$nodeMajor = [int]($nodeVersion.Split('.')[0])
if ($nodeMajor -lt 20) {
    Write-Host "⚠️  Node.js version $nodeVersion detected. Version 20+ is required." -ForegroundColor Red
    Write-Host "   Please upgrade Node.js from https://nodejs.org/" -ForegroundColor Cyan
    exit 1
}
Write-Host "✅ Node.js v$nodeVersion" -ForegroundColor Green

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
        Refresh-Path
    } catch {
        Write-Error "Failed to install Rust automatically. Please install it manually from https://rustup.rs/"
        exit 1
    }
}

# 2. Install uv if missing
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    Refresh-Path
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

# 5. Check for C++ Build Tools (Linker) — must happen BEFORE Rust compilation
function Find-VCToolsPath {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($installPath) {
            return $installPath
        }
    }
    return $null
}

function Add-VCToolsToPath($vsPath) {
    # Find the latest VC tools version directory and add to PATH for this session
    $vcToolsDir = Join-Path $vsPath "VC\Tools\MSVC"
    if (Test-Path $vcToolsDir) {
        $latest = Get-ChildItem $vcToolsDir -Directory | Sort-Object Name -Descending | Select-Object -First 1
        if ($latest) {
            $binDir = Join-Path $latest.FullName "bin\Hostx64\x64"
            if (Test-Path $binDir) {
                $env:Path = "$binDir;$env:Path"
                Write-Host "   ✅ Added MSVC linker to PATH for this session." -ForegroundColor Green
                return $true
            }
        }
    }
    return $false
}

$needRestart = $false
# Detect MSVC linker via vswhere first, fall back to PATH check
$vsPath = Find-VCToolsPath
$hasMSVCLinker = $false
if ($vsPath) {
    $vcToolsDir = Join-Path $vsPath "VC\Tools\MSVC"
    if (Test-Path $vcToolsDir) {
        $latest = Get-ChildItem $vcToolsDir -Directory | Sort-Object Name -Descending | Select-Object -First 1
        if ($latest) {
            $binDir = Join-Path $latest.FullName "bin\Hostx64\x64"
            if (Test-Path (Join-Path $binDir "link.exe")) {
                $hasMSVCLinker = $true
            }
        }
    }
}

if (-not $hasMSVCLinker) {
    if ($vsPath) {
        Write-Host "⚠️  C++ Build Tools detected at: $vsPath" -ForegroundColor Yellow
        Write-Host "   However, 'link.exe' is not in your PATH."
        $added = Add-VCToolsToPath $vsPath
        if (-not $added) {
            Write-Host "   ⚠️  Could not auto-add linker to PATH. Rust builds might fail" -ForegroundColor Yellow
            Write-Host "      unless you run from a Developer Command Prompt." -ForegroundColor Yellow
            $needRestart = $true
        }
    } else {
        Write-Host "⚠️  MSVC C++ Build Tools not found!" -ForegroundColor Yellow
        Write-Host "   This is REQUIRED for compiling Rust/Tauri dependencies." -ForegroundColor Red
        Write-Host "   Installing Visual Studio Build Tools via winget..." -ForegroundColor Cyan

        try {
            $wingetCheck = Get-Command "winget" -ErrorAction SilentlyContinue
            if (-not $wingetCheck) {
                Write-Host "   ❌ 'winget' not found. Please install Build Tools manually:" -ForegroundColor Red
                Write-Host "      https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Cyan
                Write-Host "      Select 'Desktop development with C++' workload." -ForegroundColor Cyan
                exit 1
            }
            winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
                # -1978335189 = already installed
                $vsPath = Find-VCToolsPath
                if ($vsPath) {
                    Add-VCToolsToPath $vsPath | Out-Null
                }
                Write-Host "   ✅ Build Tools installed." -ForegroundColor Green
            } else {
                Write-Host "   ⚠️  Build Tools installation returned code $LASTEXITCODE" -ForegroundColor Yellow
                Write-Host "      You may need to run the installer as Administrator." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "   ❌ Failed to install Build Tools: $_" -ForegroundColor Red
            Write-Host "      Please install manually from https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Cyan
            exit 1
        }
        $needRestart = $true
    }
} else {
    Write-Host "✅ MSVC C++ Build Tools found." -ForegroundColor Green
}

# 6. Install Backend Dependencies
Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
uv sync
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backend dependency installation failed (uv sync). Please check errors above."
    exit 1
}

# 6.5. Install Playwright Chromium browser (needed by browsing tool)
Write-Host "Installing Playwright Chromium browser..." -ForegroundColor Yellow
uv run playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Playwright browser install failed (non-fatal, will retry on first use)." -ForegroundColor Yellow
}

# 7. Install Frontend Dependencies
Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
Set-Location "frontend"
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend dependency installation failed (npm install). Please check errors above."
    Set-Location ..
    exit 1
}
Set-Location ..

# 7.5. Install Src-Tauri Dependencies
Write-Host "Installing src-tauri dependencies..." -ForegroundColor Yellow
Set-Location "src-tauri"
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Error "Src-tauri dependency installation failed (npm install). Please check errors above."
    Set-Location ..
    exit 1
}
Set-Location ..

# 7.6. Ensure Tauri resource placeholders exist
# These files are tracked in git but may be missing if:
#   - User cloned before the files were committed (stale .gitignore)
#   - bundle_python.py wiped the resources/ directory
#   - .gitignore negation patterns weren't applied on pull
Write-Host "Ensuring Tauri resource files exist..." -ForegroundColor Yellow
git checkout HEAD -- src-tauri/resources/suzent.cmd src-tauri/resources/suzent 2>$null
if ($LASTEXITCODE -ne 0) {
    # Files not in git (e.g. older branch) — create placeholders
    $resourceDir = Join-Path (Get-Location) "src-tauri\resources"
    if (-not (Test-Path $resourceDir)) {
        New-Item -ItemType Directory -Path $resourceDir -Force | Out-Null
    }
    $cmdShim = Join-Path $resourceDir "suzent.cmd"
    if (-not (Test-Path $cmdShim)) {
        Set-Content -Path $cmdShim -Value "@echo off`r`nREM Placeholder — actual shim is generated at runtime.`r`n" -NoNewline
    }
    $shShim = Join-Path $resourceDir "suzent"
    if (-not (Test-Path $shShim)) {
        Set-Content -Path $shShim -Value "#!/bin/sh`n# Placeholder — actual shim is generated at runtime.`n" -NoNewline
    }
}

# 8. Add to PATH (Global CLI)
$scriptsDir = Join-Path (Get-Location) "scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($currentPath -notlike "*$scriptsDir*") {
    Write-Host "Adding $scriptsDir to PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$scriptsDir", "User")
    $env:Path += ";$scriptsDir"
    Write-Host "✅ Added 'suzent' command to PATH" -ForegroundColor Green
}

if ($needRestart) {
    Write-Host ""
    Write-Host "⚠️  Please RESTART your terminal to ensure the MSVC linker is in PATH." -ForegroundColor Yellow
}

Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "To start Suzent, run:"
Write-Host "  suzent start" -ForegroundColor Cyan
