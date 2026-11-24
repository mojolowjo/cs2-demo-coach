# CS2Room on the laptop

m0j's Windows laptop (on 24/7) runs **m0j's CS2 ROOM** on its own: it hosts the site, refreshes Steam stats, downloads
new Valve match demos, parses them and rebuilds the site. GitHub is only used to receive Claude's code updates.

```
C:\Users\mojol\Documents\CS2Room\
  app\           copy of this repo (refreshed every 6 h by update.ps1; node_modules kept)
  data\          the laptop's own store: demos.json (match history), radar_*.png, steam\latest.json + steam\history\
  site\          what the web server shows (rebuilt after every change)
  demos\inbox\   new demos (auto-downloaded, or dropped in by hand)
  demos\archive\ processed demos, zipped, by year\month
  config\        secrets.dpapi (Windows-encrypted), gsi_token.txt, state.json, gamestate_integration_cs2room.cfg
  logs\          cs2room.log
  .venv\         CS2Room's own Python
```

## Setup (one time, safe to re-run)
```
powershell -ExecutionPolicy Bypass -File "$HOME\Documents\CS2Room\app\laptop\setup.ps1"
```
Installs Python 3.12 + Node LTS for the user (winget), awpy map data, Node packages; encrypts `config\secrets.local.json` into
`secrets.dpapi`; one UAC prompt opens TCP 8080 and 3000 on Private networks; registers the tasks below; runs once; writes the
CS2 config file for the gaming PC.

| Task | When | What |
|---|---|---|
| CS2Room site | at logon, always on | `cs2room.py serve`: site\ on 8080 plus `GET /api/status`, `POST /api/check` (the page's "Check for new matches" button, shown only when served by the laptop) |
| CS2Room listener | at logon, always on | `cs2room.py listen`: CS2 Game State Integration on port 3000. On "match over" it runs steam → check → process → build at +2, +5, +10, +20, +40, +70 min until the demo arrives |
| CS2Room backup check | every 30 min | `cs2room.py run` (catches matches the listener missed) |
| CS2Room update | every 6 h | `update.ps1`: refresh `app\` from GitHub, rebuild the site |

## Pieces
- `cs2room.py`: everything above. Secrets come from `config\secrets.dpapi` (or the plain JSON before setup).
  New matches: `ICSGOPlayers_730/GetNextMatchSharingCode` with the match-history auth code, starting from `state.json`'s
  `last_share_code` (first run also fetches the match the original token points at).
- `fetch_demo.js`: logs in the bot account `m0j_demobot` (Steam Guard must be OFF: Steam turns email Guard on by itself after the email is verified; CS2 in library), connects to the CS2 game coordinator,
  `requestGame(shareCode)` → replay URL (`.dem.bz2`). Credentials arrive on stdin, never on the command line.
- The GSI config only asks CS2 for the `map` block, and the listener only reacts to `map.phase == "gameover"`: post-match only.

## The gaming PC (Bazzite)
Copy `config\gamestate_integration_cs2room.cfg` to
`~/.local/share/Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/` and restart CS2.
It points at the laptop's IP; if the laptop's IP changes, re-run setup.ps1 and copy it again (or reserve the IP in the router).

## Claude's access
This chat is linked to the laptop through the Claude desktop app with `CS2Room` granted. Claude works there through `device_bash`
(a Linux VM with the folder at `$HOME/mnt/CS2Room`): it can read logs and data and edit files, but can't run Windows programs,
read `secrets.dpapi`, or open `localhost:8080`. To show the page on m0j's phone, publish `site\` as the claude.ai artifact.

## Later
- FACEIT (private Downloads API; browser automation or one-click download)
- pushing the laptop's matches to GitHub so the public Pages site stays in sync

## Reaching it from anywhere (Cloudflare quick tunnel)
`setup-tunnel.ps1` (run once): saves a GitHub key (fine-grained, Contents read/write, this repo only) Windows-encrypted in
`config\github.dpapi`, puts `tools\cloudflared.exe` in place and registers the **CS2Room tunnel** task (`cs2room.py tunnel`).
The task keeps a `*.trycloudflare.com` tunnel to port 8080 running, writes each new address to `data/tunnel.json` in the repo,
and restarts the tunnel if it stops answering. https://mojolowjo.github.io/cs2-demo-coach/ reads that file and sends you there.
Through the tunnel the "Check for new matches" button needs "Sign in through Steam" with an account listed in
`config\site_auth.json` → `allowed` (SteamID64s; created with m0j's). At home it works for anyone on the network.
