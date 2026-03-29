$ErrorActionPreference = "Stop"

param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$UploaderRef = "demo_user_1",
  [string]$FilePath = "",
  [string]$Username = "admin",
  [string]$Password = "admin123",
  [switch]$ManualMode
)

Set-Location (Join-Path $PSScriptRoot "..")

if (-not $FilePath) {
  throw "Pass -FilePath with a local video file."
}

Write-Host "Logging in..."
$authResp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auth/login" -ContentType "application/json" -Body (@{
  username = $Username
  password = $Password
} | ConvertTo-Json)
$token = $authResp.data.access_token
$headers = @{ Authorization = "Bearer $token" }

Write-Host "Uploading file..."
$uploadResp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/videos/upload/file" -Form @{
  uploader_ref = $UploaderRef
  file = Get-Item $FilePath
} -Headers $headers

$videoId = $uploadResp.data.video_id
$jobId = $uploadResp.data.job_id
Write-Host "video_id=$videoId, job_id=$jobId"

if ($ManualMode) {
  Write-Host "Running phase-a manually..."
  $phaseA = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/workflow/$jobId/phase-a" -Headers $headers
} else {
  Write-Host "Waiting for auto phase-a trigger..."
  Start-Sleep -Seconds 3
  $phaseA = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/videos/$videoId/status" -Headers $headers
}
Write-Host "state=$($phaseA.data.state), priority=$($phaseA.data.priority)"

if ($phaseA.data.state -eq "HOLD") {
  Write-Host "Escalating HOLD to Gate 1..."
  $gate1Task = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/workflow/$jobId/hold/escalate" -Headers $headers
} else {
  $gate1Task = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/workflow/$jobId/gate-1/create" -Headers $headers
}

$gate1TaskId = $gate1Task.data.task_id
Write-Host "Gate1 task=$gate1TaskId"

Write-Host "Approving Gate 1..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/reviews/tasks/$gate1TaskId/decision?auto_progress=true&async_mode=false" -ContentType "application/json" -Headers $headers -Body (@{
  reviewer_ref = "moderator_1"
  decision = "APPROVE"
  notes = "demo approve gate 1"
} | ConvertTo-Json)

Write-Host "Fetching Gate 2 tasks..."
$tasks = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/reviews/tasks?gate=GATE_2&status=PENDING" -Headers $headers
$gate2TaskId = ($tasks.data | Where-Object { $_.job_id -eq $jobId } | Select-Object -First 1).task_id
if (-not $gate2TaskId) {
  throw "Gate 2 task not found."
}
Write-Host "Gate2 task=$gate2TaskId"

Write-Host "Approving Gate 2..."
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/reviews/tasks/$gate2TaskId/decision?auto_progress=true&async_mode=false" -ContentType "application/json" -Headers $headers -Body (@{
  reviewer_ref = "moderator_2"
  decision = "APPROVE"
  notes = "demo approve gate 2"
} | ConvertTo-Json)

Write-Host "Fetching outputs..."
$status = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/videos/$videoId/status" -Headers $headers
$report = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/reports/video/$videoId" -Headers $headers
$dist = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/distribution/video/$videoId" -Headers $headers
$wallet = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/wallet/$UploaderRef" -Headers $headers

Write-Host "Final status: $($status.data.state)"
Write-Host "Distribution entries: $($dist.data.Count)"
Write-Host "Wallet points: $($wallet.data.balance_points)"
Write-Host "Demo flow complete."
