# bt-auto-sync.ps1 — headless "pull everything from Buildertrend" for the
# scheduled task. Starts an ephemeral local Next server, triggers
# POST /api/bt/sync-all {kind:"auto"} (which scrapes daily logs + POs + COs for
# every active job and upserts them to Supabase), waits for it to finish,
# then stops the server. The route records the run in the sync_runs table, so
# the app's "last synced" reflects the real run time.
#
# Buildertrend credentials come from production-cockpit/.env.local
# (BT_USERNAME / BT_PASSWORD), which Next loads into the route's environment.
# This script never sees the password. If those are absent the scraper falls
# back to its saved BT session (set once via the scraper's auth.py).
#
# Runs unattended — no terminal, no `npm run dev` needed.

$ErrorActionPreference = "Stop"
$appDir = Split-Path -Parent $PSScriptRoot          # ...\production-cockpit
$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $logDir "bt-sync-$stamp.log"
function Log($m) { "$(Get-Date -Format 'u')  $m" | Tee-Object -FilePath $log -Append | Out-Null }

# Keep only the last ~30 run logs so this folder doesn't grow forever.
Get-ChildItem $logDir -Filter "bt-sync-*.log" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 |
  Remove-Item -Force -ErrorAction SilentlyContinue

$port = 4319
$base = "http://localhost:$port"
Log "=== BT auto-sync starting (port $port, appDir $appDir) ==="

# Clear any stale listener on our dedicated port.
try {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /PID $_.OwningProcess /T /F 2>$null | Out-Null }
} catch {}

$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) { Log "ERROR: node not found on PATH"; exit 2 }
$nextBin = Join-Path $appDir "node_modules\next\dist\bin\next"
if (-not (Test-Path $nextBin)) { Log "ERROR: next missing at $nextBin (run npm install)"; exit 2 }

Log "Starting Next server (ephemeral)..."
$srvOut = Join-Path $logDir "server-$stamp.out.log"
$srvErr = Join-Path $logDir "server-$stamp.err.log"
$proc = Start-Process -FilePath $node -ArgumentList @("`"$nextBin`"", "dev", "-p", "$port") `
  -WorkingDirectory $appDir -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput $srvOut -RedirectStandardError $srvErr
Log "Server PID $($proc.Id); waiting for it to answer..."

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  try {
    $r = Invoke-WebRequest -Uri "$base/login" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -ge 200) { $ready = $true; break }
  } catch {}
}
if (-not $ready) {
  Log "ERROR: server never became ready; aborting."
  try { taskkill /PID $proc.Id /T /F 2>$null | Out-Null } catch {}
  exit 3
}
Log "Server ready. Triggering full BT sync (kind=auto). This can take 30-70 min..."

$ok = $false
try {
  $resp = Invoke-WebRequest -Uri "$base/api/bt/sync-all" -Method POST `
    -ContentType "application/json" -Body '{"kind":"auto"}' `
    -TimeoutSec 7200 -UseBasicParsing
  foreach ($line in ($resp.Content -split "`n")) {
    if ($line -match '\S') { Log "EVENT $line" }
  }
  $doneLine = ($resp.Content -split "`n" | Where-Object { $_ -match '"kind":"done"' } | Select-Object -Last 1)
  if ($doneLine -and $doneLine -match '"ok":true') { $ok = $true }
} catch {
  Log "ERROR during sync: $($_.Exception.Message)"
}

Log "Stopping server PID $($proc.Id)..."
try { taskkill /PID $proc.Id /T /F 2>$null | Out-Null } catch {}

if ($ok) { Log "=== BT auto-sync DONE: OK ==="; exit 0 }
Log "=== BT auto-sync DONE: completed with errors (see EVENT lines above) ==="
exit 1
