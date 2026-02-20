# PowerShell build script for SUZENT Tauri application
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SUZENT Tauri Build Pipeline" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Step 1: Build frontend
Write-Host "`n[1/3] Building frontend..." -ForegroundColor Yellow
Push-Location "$ProjectRoot\frontend"
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

# Step 2: Bundle Python backend
Write-Host "`n[2/3] Bundling Python backend..." -ForegroundColor Yellow
python "$ProjectRoot\scripts\bundle_python.py"

# Step 3: Build Tauri application
Write-Host "`n[3/3] Building Tauri application..." -ForegroundColor Yellow
Push-Location "$ProjectRoot\src-tauri"
try {
    npm run build
} finally {
    Pop-Location
}

Write-Host "`nBuild complete!" -ForegroundColor Green
Write-Host "Artifacts: $ProjectRoot\src-tauri\target\release\bundle\" -ForegroundColor Cyan
