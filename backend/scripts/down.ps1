$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$BackendRoot = (Get-Location).Path
$BackendRootNorm = $BackendRoot.ToLower()

function Stop-ManagedProcess([string]$pidFile, [string]$label) {
  if (-not (Test-Path $pidFile)) { return }

  $raw = Get-Content $pidFile -ErrorAction SilentlyContinue
  if (-not $raw) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    return
  }

  $targetPid = 0
  if (-not [int]::TryParse(($raw | Select-Object -First 1), [ref]$targetPid)) {
    Write-Warning "Invalid PID value in $pidFile. Removing stale file."
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    return
  }

  if ($targetPid -eq $PID) {
    Write-Warning "Skipping $label PID $targetPid because it matches current shell process."
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    return
  }

  $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
  if (-not $proc) {
    Write-Host "$label PID $targetPid not running. Cleaning stale pid file."
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    return
  }

  # Safety check: only kill expected managed processes.
  $allowed = @("python", "uvicorn", "celery")
  if ($allowed -notcontains $proc.ProcessName.ToLower()) {
    Write-Warning "Refusing to stop PID $targetPid ($($proc.ProcessName)) from $pidFile."
    return
  }

  try {
    Stop-Process -Id $targetPid -Force -ErrorAction Stop
    Write-Host "Stopped $label process $targetPid"
  } catch {
    Write-Warning "Could not stop $label PID ${targetPid}: $($_.Exception.Message)"
  } finally {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  }
}

function Stop-StrayBackendProcesses() {
  $currentPid = $PID
  $candidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.Name -in @("python.exe", "uvicorn.exe", "celery.exe")) -and
    (
      ($_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($BackendRootNorm)) -or
      ($_.CommandLine -and $_.CommandLine.ToLower().Contains($BackendRootNorm))
    ) -and
    (
      ($_.CommandLine -and ($_.CommandLine.Contains("app.main:app") -or $_.CommandLine.Contains("app.orchestrator.tasks"))) -or
      ($_.Name -in @("uvicorn.exe", "celery.exe"))
    )
  }

  foreach ($p in $candidates) {
    $pidInt = [int]$p.ProcessId
    if ($pidInt -eq $currentPid) { continue }
    try {
      Stop-Process -Id $pidInt -Force -ErrorAction Stop
      Write-Host "Stopped stray process $pidInt ($($p.Name))"
    } catch {
      Write-Warning "Could not stop stray PID ${pidInt}: $($_.Exception.Message)"
    }
  }
}

Stop-ManagedProcess ".api.pid" "API"

$workerPidFiles = Get-ChildItem ".celery*.pid" -ErrorAction SilentlyContinue
foreach ($f in $workerPidFiles) {
  Stop-ManagedProcess $f.FullName "Celery"
}

# Safety sweep: stop backend-bound uvicorn/celery/python workers even if pid files are stale/missing.
Stop-StrayBackendProcesses

# Clean stale pid artifacts if any remain.
Get-ChildItem ".api.pid", ".celery*.pid" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Shutdown complete."
