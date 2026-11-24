# One-time setup for CS2Room on m0j's Windows laptop.
# Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File "$HOME\Documents\CS2Room\app\laptop\setup.ps1"
# Safe to run again: it only adds what's missing and re-registers the two scheduled tasks.

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent      # ...\CS2Room
$Venv = Join-Path $Root ".venv"
Write-Host "CS2Room folder: $Root"

# 1. Folders
foreach ($d in "site", "demos\inbox", "demos\archive", "config", "logs") {
  New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null
}

# 2. Python (user install, no admin) via winget, if missing
function Find-Python {
  foreach ($c in @("py -3", "python")) {
    try { $v = & cmd /c "$c --version 2>&1"; if ($v -match "Python 3\.(1[1-9])") { return $c } } catch {}
  }
  return $null
}
$py = Find-Python
if (-not $py) {
  Write-Host "Installing Python 3.12 (user only)..."
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
  $py = Find-Python
  if (-not $py) { throw "Python installed but not found yet. Close PowerShell, open a new one, and run setup.ps1 again." }
}
Write-Host "Using: $py"

# 3. CS2Room's own Python environment (keeps its packages separate from everything else)
if (-not (Test-Path "$Venv\Scripts\python.exe")) { & cmd /c "$py -m venv `"$Venv`"" }
& "$Venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$Venv\Scripts\python.exe" -m pip install --quiet awpy demoparser2 pandas pyarrow
Write-Host "Python packages ready"

# 4. Build the site once
& "$Venv\Scripts\python.exe" (Join-Path $Root "app\tools\build_site.py") (Join-Path $Root "app") (Join-Path $Root "site")

# 5. Scheduled tasks (current user, no admin):
#    - "CS2Room site": web server on port 8080, starts at logon, no window
#    - "CS2Room update": every 30 minutes, pulls the repo from GitHub and rebuilds the site
$pyw = "$Venv\Scripts\pythonw.exe"
$siteAction = New-ScheduledTaskAction -Execute $pyw -Argument "-m http.server 8080 --bind 0.0.0.0 --directory `"$Root\site`"" -WorkingDirectory $Root
$siteTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "CS2Room site" -Action $siteAction -Trigger $siteTrigger -Settings $settings -Force | Out-Null

$upd = Join-Path $Root "app\laptop\update.ps1"
$updAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$upd`""
$updTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 30)
$updSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "CS2Room update" -Action $updAction -Trigger $updTrigger -Settings $updSettings -Force | Out-Null

Start-ScheduledTask -TaskName "CS2Room site"
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet" -and $_.IPAddress -notmatch "^169\." } | Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "Done. Open http://localhost:8080 on this laptop, or http://${ip}:8080 from your phone/PC at home."
Write-Host "If Windows asks about the firewall for Python, allow it on Private networks only."
