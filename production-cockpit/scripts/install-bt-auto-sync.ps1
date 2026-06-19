# install-bt-auto-sync.ps1 — registers the Windows Scheduled Task that runs
# bt-auto-sync.ps1 every 12 hours and ~5 minutes after each logon (to catch up
# if the laptop was off at the scheduled time). Runs only while you're logged
# in (the BT scraper drives a browser, so it needs your session), hidden, on
# battery too. No admin rights required — it's a per-user task.
#
# Run once:   powershell -ExecutionPolicy Bypass -File scripts\install-bt-auto-sync.ps1
# Remove with: Unregister-ScheduledTask -TaskName "RossBuilt BT Auto-Sync" -Confirm:$false

$ErrorActionPreference = "Stop"
$taskName = "RossBuilt BT Auto-Sync"
$script = Join-Path $PSScriptRoot "bt-auto-sync.ps1"
if (-not (Test-Path $script)) { throw "Cannot find $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""

# Every 12h, anchored to the top of the current hour, repeating ~indefinitely.
$start = (Get-Date).Date.AddHours((Get-Date).Hour)
$t12 = New-ScheduledTaskTrigger -Once -At $start `
  -RepetitionInterval (New-TimeSpan -Hours 12) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

# ~5 minutes after logon (so a missed slot is picked up when you next sign in).
$tLogon = New-ScheduledTaskTrigger -AtLogOn
$tLogon.Delay = "PT5M"

$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
  -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action `
  -Trigger @($t12, $tLogon) -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Installed '$taskName': every 12h + 5 min after logon."
Write-Host "Reminder: set BT_USERNAME and BT_PASSWORD in production-cockpit\.env.local for unattended re-login."
