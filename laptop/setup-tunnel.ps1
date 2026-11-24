# One-time setup for the Cloudflare tunnel (lets you open CS2 ROOM from anywhere through the GitHub launcher page).
#   powershell -ExecutionPolicy Bypass -File "$HOME\Documents\CS2Room\app\laptop\setup-tunnel.ps1"
# 1. asks for the GitHub key (fine-grained token, Contents: read and write, only the cs2-demo-coach repo) and stores it
#    Windows-encrypted in config\github.dpapi (only your Windows user can read it; it never leaves this laptop)
# 2. makes sure tools\cloudflared.exe is there
# 3. registers the "CS2Room tunnel" task (starts at logon, restarts if it stops) and restarts the site so it has the new code
# Run it again any time to replace the key.

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Cfg = Join-Path $Root "config"
$Tools = Join-Path $Root "tools"
$Venv = Join-Path $Root ".venv"
$main = "`"$Root\app\laptop\cs2room.py`""
New-Item -ItemType Directory -Force -Path $Cfg, $Tools | Out-Null

# 1. GitHub key
$keyFile = Join-Path $Cfg "github.dpapi"
if ((Test-Path $keyFile) -and -not ($args -contains "-NewKey")) {
  Write-Host "GitHub key already saved (run with -NewKey to replace it)." -ForegroundColor DarkGray
} else {
  Write-Host "Paste the GitHub key (it starts with github_pat_). Nothing shows while you paste; press Enter after." -ForegroundColor Cyan
  $sec = Read-Host -AsSecureString "GitHub key"
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  $hdr = @{ Authorization = "Bearer $plain"; "User-Agent" = "cs2room-laptop"; Accept = "application/vnd.github+json" }
  try {
    $repo = Invoke-RestMethod -Uri "https://api.github.com/repos/mojolowjo/cs2-demo-coach" -Headers $hdr
    if (-not $repo.permissions.push) { throw "this key can read the repo but not write to it (Contents must be 'Read and write')" }
  } catch {
    Write-Host "That key didn't work: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check: repository access = only cs2-demo-coach, permission Contents = Read and write. Then run this again." -ForegroundColor Yellow
    exit 1
  } finally { $plain = $null }
  $sec | ConvertFrom-SecureString | Set-Content $keyFile
  Write-Host "GitHub key saved (encrypted)." -ForegroundColor Green
}

# 2. cloudflared
$cf = Join-Path $Tools "cloudflared.exe"
if (-not (Test-Path $cf)) {
  Write-Host "Downloading cloudflared…"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf
}
Unblock-File $cf -ErrorAction SilentlyContinue
& $cf --version

# 3. tasks
$pyw = "$Venv\Scripts\pythonw.exe"
$always = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Stop-ScheduledTask -TaskName "CS2Room tunnel" -ErrorAction SilentlyContinue
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "CS2Room tunnel" -Force -Settings $always -Trigger $logon `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument "$main tunnel" -WorkingDirectory $Root) | Out-Null
Stop-ScheduledTask -TaskName "CS2Room site" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "CS2Room site"
Start-ScheduledTask -TaskName "CS2Room tunnel"
Write-Host "Tunnel started. In about a minute, https://mojolowjo.github.io/cs2-demo-coach/ will send you to CS2 ROOM." -ForegroundColor Green
Write-Host "Progress is in $Root\logs\cs2room.log (look for 'tunnel:')."
