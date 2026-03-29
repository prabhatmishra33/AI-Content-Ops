$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
& ".\.venv\Scripts\python.exe" scripts/manage_db.py seed
