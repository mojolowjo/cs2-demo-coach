# Runs every 30 minutes (scheduled task "CS2Room update"): pulls the latest repo from GitHub
# (tools, page, match data, nightly Steam stats) into CS2Room\app and rebuilds CS2Room\site.
# Uses the public zip download, so Git doesn't need to be installed.

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Log = Join-Path $Root "logs\update.log"
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -Path $Log }

try {
  $tmp = Join-Path $env:TEMP "cs2room-update"
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path $tmp | Out-Null
  $zip = Join-Path $tmp "main.zip"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/mojolowjo/cs2-demo-coach/archive/refs/heads/main.zip" -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  $src = Join-Path $tmp "cs2-demo-coach-main"

  # Replace app\ with the fresh copy. robocopy /MIR mirrors it; exit codes below 8 mean success.
  robocopy $src (Join-Path $Root "app") /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

  & (Join-Path $Root ".venv\Scripts\python.exe") (Join-Path $Root "app\tools\build_site.py") (Join-Path $Root "app") (Join-Path $Root "site") | Out-Null
  Log "updated from GitHub and rebuilt site"
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
} catch {
  Log "ERROR: $($_.Exception.Message)"
  exit 1
}

# keep the log short
$lines = Get-Content $Log -ErrorAction SilentlyContinue
if ($lines.Count -gt 500) { $lines | Select-Object -Last 300 | Set-Content $Log }
