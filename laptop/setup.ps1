# One-time setup for CS2Room on m0j's Windows laptop. Safe to run again.
#   powershell -ExecutionPolicy Bypass -File "$HOME\Documents\CS2Room\app\laptop\setup.ps1"
#
# Installs (for this user only): Python 3.12, Node.js LTS, CS2Room's own Python env + Node packages.
# Encrypts config\secrets.local.json with Windows DPAPI (only this Windows account can read it) and deletes the plain copy.
# Asks once for admin (UAC) to open ports 8080 (site) and 3000 (match-over signal) on Private networks.
# Registers scheduled tasks: CS2Room site, CS2Room listener, CS2Room backup check, CS2Room update.

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent      # ...\CS2Room
$App = Join-Path $Root "app"
$Venv = Join-Path $Root ".venv"
$Cfg = Join-Path $Root "config"
Write-Host "CS2Room folder: $Root" -ForegroundColor Cyan

# 1. Folders, and seed local match data from the repo copy the first time
foreach ($d in "site", "data", "demos\inbox", "demos\archive", "config", "logs") { New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null }
if (-not (Test-Path "$Root\data\demos.json")) { Copy-Item "$App\replay\demos.json" "$Root\data\"; Copy-Item "$App\replay\radar_*.png" "$Root\data\" }

function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine") }

# 2. Python
function Find-Python { foreach ($c in @("py -3.12", "py -3", "python")) { try { $v = & cmd /c "$c --version 2>&1"; if ($v -match "Python 3\.(1[1-9])") { return $c } } catch {} }; return $null }
$py = Find-Python
if (-not $py) {
  Write-Host "Installing Python 3.12..." -ForegroundColor Cyan
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  Refresh-Path; $py = Find-Python
  if (-not $py) { throw "Python installed but not found yet. Close PowerShell, open a new one, and run setup.ps1 again." }
}
if (-not (Test-Path "$Venv\Scripts\python.exe")) { & cmd /c "$py -m venv `"$Venv`"" }
& "$Venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$Venv\Scripts\python.exe" -m pip install --quiet awpy demoparser2 pandas pyarrow
Write-Host "Python ready" -ForegroundColor Green

# 3. awpy map data (radar images + wall geometry for the line-of-sight check)
& cmd /c "`"$Venv\Scripts\awpy.exe`" get"
if ($LASTEXITCODE -ne 0) { Write-Host "Map data download failed; replays still work, the wall check will be off until it succeeds." -ForegroundColor Yellow }

# 4. Node.js + the demo-bot packages
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "Installing Node.js LTS..." -ForegroundColor Cyan
  winget install -e --id OpenJS.NodeJS.LTS --scope user --accept-package-agreements --accept-source-agreements
  Refresh-Path
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node installed but not found yet. Close PowerShell, open a new one, and run setup.ps1 again." }
# The bot's packages are plain JavaScript. Install them only if missing; find npm even when it isn't on PATH.
if (-not (Test-Path "$App\laptop\node_modules\globaloffensive")) {
  $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
  if (-not $npm) { $npm = Join-Path (Split-Path (Get-Command node).Source) "npm.cmd" }
  if (-not (Test-Path $npm)) { throw "npm not found. Install Node.js LTS from nodejs.org (or: winget install OpenJS.NodeJS.LTS), then run setup again." }
  & cmd /c "cd /d `"$App\laptop`" && `"$npm`" install --omit=dev --no-audit --no-fund"
  if (-not (Test-Path "$App\laptop\node_modules\globaloffensive")) { throw "npm install failed (see the messages above)" }
}
Write-Host "Node ready" -ForegroundColor Green

# 5. Secrets: encrypt with this Windows account (DPAPI), then remove the plain file
$plain = Join-Path $Cfg "secrets.local.json"
if (Test-Path $plain) {
  $json = Get-Content $plain -Raw
  ConvertTo-SecureString $json -AsPlainText -Force | ConvertFrom-SecureString | Set-Content (Join-Path $Cfg "secrets.dpapi")
  Remove-Item $plain
  Write-Host "Secrets encrypted (config\secrets.dpapi)" -ForegroundColor Green
}
# match-over signal password (shared with CS2's config file on the gaming PC)
$tokFile = Join-Path $Cfg "gsi_token.txt"
if (-not (Test-Path $tokFile)) { -join ((48..57) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ }) | Set-Content $tokFile }
$token = (Get-Content $tokFile).Trim()

# 6. Firewall: allow the site (8080) and the match-over signal (3000) on Private networks (one admin prompt)
$rules = 'New-NetFirewallRule -DisplayName "CS2Room site" -Direction Inbound -Protocol TCP -LocalPort 8080 -Profile Private -Action Allow -ErrorAction SilentlyContinue; New-NetFirewallRule -DisplayName "CS2Room match signal" -Direction Inbound -Protocol TCP -LocalPort 3000 -Profile Private -Action Allow -ErrorAction SilentlyContinue'
if (-not (Get-NetFirewallRule -DisplayName "CS2Room site" -ErrorAction SilentlyContinue)) {
  Write-Host "Windows will ask for admin once, to open ports 8080 and 3000 on your home network." -ForegroundColor Yellow
  Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command $rules"
}

# 7. Scheduled tasks (current user). Restart the site task so a new server version takes over.
Stop-ScheduledTask -TaskName "CS2Room site" -ErrorAction SilentlyContinue
$pyw = "$Venv\Scripts\pythonw.exe"
$main = "`"$App\laptop\cs2room.py`""
$always = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1)
$short = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

Register-ScheduledTask -TaskName "CS2Room site" -Force -Settings $always -Trigger $logon `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument "$main serve" -WorkingDirectory $Root) | Out-Null
Register-ScheduledTask -TaskName "CS2Room listener" -Force -Settings $always -Trigger $logon `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument "$main listen" -WorkingDirectory $Root) | Out-Null
Register-ScheduledTask -TaskName "CS2Room backup check" -Force -Settings $short `
  -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)) `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument "$main run" -WorkingDirectory $Root) | Out-Null
Register-ScheduledTask -TaskName "CS2Room update" -Force -Settings $short `
  -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 6)) `
  -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$App\laptop\update.ps1`"") | Out-Null

# 8. First run: stats, your latest match, site
Write-Host "First run (Steam stats + your latest match; downloading a demo can take a minute)..." -ForegroundColor Cyan
& "$Venv\Scripts\python.exe" "$App\laptop\cs2room.py" run
Start-ScheduledTask -TaskName "CS2Room site"; Start-ScheduledTask -TaskName "CS2Room listener"

# 9. The file for the gaming PC (CS2's match-over signal)
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL" -and $_.IPAddress -notmatch "^169\." -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
@"
"CS2Room match over"
{
  "uri"       "http://${ip}:3000/"
  "timeout"   "5.0"
  "buffer"    "1.0"
  "throttle"  "5.0"
  "heartbeat" "60.0"
  "auth" { "token" "$token" }
  "data" { "map" "1" }
}
"@ | Set-Content (Join-Path $Cfg "gamestate_integration_cs2room.cfg")

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Site:  http://localhost:8080  (at home from other devices: http://${ip}:8080)"
Write-Host "  Log:   $Root\logs\cs2room.log"
Write-Host "  For the gaming PC: copy $Cfg\gamestate_integration_cs2room.cfg into CS2's game\csgo\cfg folder (Claude will give you the command)."
