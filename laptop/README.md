# CS2Room on the laptop

m0j's Windows laptop (on 24/7) hosts **m0j's CS2 ROOM** for his home network.

```
C:\Users\mojol\Documents\CS2Room\
  app\           copy of this repo (refreshed every 30 min by update.ps1)
  site\          what the local web server shows (built by tools/build_site.py)
  demos\inbox\   new demos land here (auto-downloader, later; or dropped in by hand)
  demos\archive\ processed demos, zipped, by year\month (later)
  config\        local settings and secrets - never committed
  logs\          update.log and friends
  .venv\         CS2Room's own Python
```

## One-time setup
```
powershell -ExecutionPolicy Bypass -File "$HOME\Documents\CS2Room\app\laptop\setup.ps1"
```
Installs Python 3.12 for the user if missing (winget), creates `.venv` with awpy/demoparser2, builds the site and registers two
scheduled tasks for the current user:

| Task | What it does |
|---|---|
| CS2Room site | `pythonw -m http.server 8080` on `site\`, starts at logon, restarts if it stops |
| CS2Room update | every 30 min: download the repo zip from GitHub into `app\`, rebuild `site\` |

Open `http://localhost:8080` on the laptop or `http://<laptop IP>:8080` at home. Allow Python through the firewall on
**Private** networks only.

## Claude's access
This Claude chat is linked to the laptop through the Claude desktop app and has been granted `CS2Room`. Claude works on it from
`device_bash` (a Linux VM where the folder is mounted at `$HOME/mnt/CS2Room`): it can read and write files, but it can't run Windows
programs or reach `localhost:8080`. To show the page on m0j's phone, Claude can read `site\` and publish it as the claude.ai artifact.

## Not done yet (paused)
- processing new demos from `demos\inbox\` on the laptop
- auto-downloading Premier/Competitive demos (cs-demo-downloader, needs a second Steam account)
- FACEIT (private Downloads API; manual/browser automation later)
