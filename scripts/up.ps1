param(
  [switch]$NoWorker,
  [switch]$NoReload,
  [string]$ApiHost = "127.0.0.1",
  [int]$ApiPort = 8000,
  [string]$AiQueue = "q.ai_processing",
  [string]$ReviewQueues = "q.review,q.review_p0,q.review_p1,q.review_p2,q.hold",
  [string]$DistributionQueues = "q.distribution,q.distribution_youtube,q.distribution_secondary",
  [string]$ReportQueue = "q.report",
  [string]$RewardQueue = "q.reward",
  [int]$HealthWaitSeconds = 20
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

function Test-PidAlive([string]$pidFile) {
  if (-not (Test-Path $pidFile)) { return $false }
  try {
    $pid = [int](Get-Content $pidFile -ErrorAction Stop)
    $proc = Get-Process -Id $pid -ErrorAction Stop
    return $null -ne $proc
  } catch {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    return $false
  }
}

function Wait-ApiReady([string]$url, [int]$timeoutSec) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $res = Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 3
      if ($res.status -eq "live") { return $true }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  return $false
}

$python = ".\.venv\Scripts\python.exe"
$uvicornExe = ".\.venv\Scripts\uvicorn.exe"
$celeryExe = ".\.venv\Scripts\celery.exe"

if (-not (Test-Path $python)) {
  throw "Virtual environment not found. Run scripts/setup.ps1 first."
}
if (-not (Test-Path $uvicornExe)) {
  throw "uvicorn not found in venv. Run scripts/setup.ps1 first."
}

if (Test-PidAlive ".api.pid") {
  throw "API appears already running (found live .api.pid). Run scripts/down.ps1 first."
}
if (-not $NoWorker) {
  $existingWorkers = Get-ChildItem ".celery.*.pid" -ErrorAction SilentlyContinue
  if ($existingWorkers) {
    throw "Celery worker pid files exist. Run scripts/down.ps1 first."
  }
}

if (-not (Test-Path ".logs")) {
  New-Item -ItemType Directory -Path ".logs" | Out-Null
}

Write-Host "Running DB migrate + seed..."
& $python scripts/manage_db.py migrate
& $python scripts/manage_db.py seed

$reloadArg = if ($NoReload) { "" } else { " --reload" }
$apiArgs = "app.main:app --host $ApiHost --port $ApiPort$reloadArg"
$apiProc = Start-Process -FilePath $uvicornExe -ArgumentList $apiArgs -RedirectStandardOutput ".logs\api.out.log" -RedirectStandardError ".logs\api.err.log" -PassThru
$apiProc.Id | Out-File ".api.pid" -Encoding ascii
Write-Host "API started. PID=$($apiProc.Id)"

$healthUrl = "http://$ApiHost`:$ApiPort/api/v1/health/live"
if (Wait-ApiReady -url $healthUrl -timeoutSec $HealthWaitSeconds) {
  Write-Host "API health check passed: $healthUrl"
} else {
  Write-Warning "API health check did not pass within $HealthWaitSeconds seconds. Check .logs\\api.err.log"
}

if (-not $NoWorker) {
  if (-not (Test-Path $celeryExe)) {
    Write-Warning "celery executable not found in venv. Skipping worker startup."
  } else {
    try {
      $redis = Test-NetConnection -ComputerName "127.0.0.1" -Port 6379 -WarningAction SilentlyContinue
      if ($redis.TcpTestSucceeded) {
        # On Windows use solo pool to avoid prefork permission issues.
        $workers = @(
          @{ Name = "ai"; Queues = $AiQueue; Log = "celery.ai" },
          @{ Name = "review"; Queues = $ReviewQueues; Log = "celery.review" },
          @{ Name = "distribution"; Queues = $DistributionQueues; Log = "celery.distribution" },
          @{ Name = "report"; Queues = $ReportQueue; Log = "celery.report" },
          @{ Name = "reward"; Queues = $RewardQueue; Log = "celery.reward" }
        )
        foreach ($w in $workers) {
          $celeryArgs = "-A app.orchestrator.tasks worker --pool=solo --concurrency=1 -Q $($w.Queues) --loglevel=info -n worker.$($w.Name)@%h"
          $outLog = ".logs\$($w.Log).out.log"
          $errLog = ".logs\$($w.Log).err.log"
          $proc = Start-Process -FilePath $celeryExe -ArgumentList $celeryArgs -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
          $pidFile = ".celery.$($w.Name).pid"
          $proc.Id | Out-File $pidFile -Encoding ascii
          Write-Host "Celery worker started. name=$($w.Name) PID=$($proc.Id) queues=$($w.Queues)"
        }
      } else {
        Write-Warning "Redis not detected at 127.0.0.1:6379. API started without Celery worker."
      }
    } catch {
      Write-Warning "Celery startup skipped: $($_.Exception.Message)"
    }
  }
}

Write-Host "Startup complete."
Write-Host "Logs: .logs\\api.out.log, .logs\\api.err.log, .logs\\celery.*.out.log, .logs\\celery.*.err.log"
Write-Host "Use scripts/down.ps1 to stop services."
