# Uninstall Suzent CLI from Windows

$scriptsDir = Join-Path (Get-Location) "scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

# Only the launcher entries recorded in .suzent\shortcuts.json are removed, so
# anything the user made by hand survives.
$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "Removing launcher shortcuts..." -ForegroundColor Yellow
    & $venvPython -m suzent.cli shortcuts --remove
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ℹ️ No launcher shortcuts were removed" -ForegroundColor Cyan
    }
}

if ($currentPath -like "*$scriptsDir*") {
    Write-Host "Removing $scriptsDir from PATH..." -ForegroundColor Yellow
    
    # Remove the exact path entry depending on where it appears (start, middle, end)
    $newPath = $currentPath -replace ";$([regex]::Escape($scriptsDir))", "" 
    $newPath = $newPath -replace "$([regex]::Escape($scriptsDir));", ""
    $newPath = $newPath -replace "$([regex]::Escape($scriptsDir))", ""

    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "✅ Removed 'suzent' command from PATH" -ForegroundColor Green
} else {
    Write-Host "ℹ️ 'suzent' command was not found in PATH" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "To completely remove the project, delete this directory:"
Write-Host "  $(Get-Location)" -ForegroundColor White
