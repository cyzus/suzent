@echo off
rem The `suzent` command of an installed Suzent: the bundled runtime's CLI.
setlocal
set "SUZENT_RESOURCES=%~dp0.."
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "SUZENT_PACKAGED_UI=%~dp0..\..\SUZENT.exe"
"%SUZENT_RESOURCES%\runtime\python\python.exe" -m suzent.cli %*
