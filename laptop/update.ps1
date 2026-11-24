# Runs every 6 hours (scheduled task "CS2Room update"): refreshes CS2Room\app from GitHub so the laptop gets Claude's
# fixes to the tools and page, then rebuilds the site from the laptop's own data. Uses the public zip (no Git needed).
# Your match data, Steam stats and settings live outside app\ and are never touched or uploaded.

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$App = Join-Path $Root "app"
$Log = Join-Path $Root "logs\cs2room.log"
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  update: $m" | Add-Content -Path $Log }

try {
  $tmp = Join-Path $env:TEMP "cs2room-update"
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path $tmp | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/mojolowjo/cs2-demo-coach/archive/refs/heads/main.zip" -OutFile "$tmp\main.zip"
  Expand-Archive -Path "$tmp\main.zip" -DestinationPath $tmp -Force
  $before = (Get-FileHash "$App\laptop\package.json" -ErrorAction SilentlyContinue).Hash

  # mirror the fresh copy into app\, keeping the installed Node packages
  robocopy "$tmp\cs2-demo-coach-main" $App /MIR /XD node_modules /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

  if ((Get-FileHash "$App\laptop\package.json").Hash -ne $before -or -not (Test-Path "$App\laptop\node_modules\globaloffensive")) {
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npm) { $npm = Join-Path (Split-Path (Get-Command node).Source) "npm.cmd" }
    if (Test-Path $npm) { & cmd /c "cd /d `"$App\laptop`" && `"$npm`" install --omit=dev --no-audit --no-fund" | Out-Null }
    else { Log "npm not found; Node packages not updated" }
  }
  & (Join-Path $Root ".venv\Scripts\python.exe") "$App\laptop\cs2room.py" build | Out-Null
  # restart the always-on tasks so they run the new code
  foreach ($t in "CS2Room site", "CS2Room listener") {
    Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue; Start-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
  }
  Log "app refreshed from GitHub, site rebuilt, server restarted"
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
} catch {
  Log "ERROR: $($_.Exception.Message)"
  exit 1
}
