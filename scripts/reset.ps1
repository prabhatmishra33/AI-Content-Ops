$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
& ".\.venv\Scripts\python.exe" scripts/manage_db.py reset
Write-Host "Reset complete. Run scripts/migrate.ps1 and scripts/seed.ps1."
