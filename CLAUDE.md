# cs2-demo-coach: instructions for Claude

This repo is Claude's toolkit for coaching **m0j** (GitHub `mojolowjo`) in CS2 from demo files.
Claude builds and maintains it. m0j attaches demos in chat; Claude analyzes them and updates his replay page.

## Ground rules
- **Post-match only.** m0j has said clearly he doesn't want to cheat. Never build anything that feeds live game info.
  Don't keep repeating the warning; he knows.
- Main focus: **decision making** (what he could read from radar, sound and the killfeed, and whether his choice was good).
  Then crosshair placement before contact, and shot pacing.
- Client-side `record` is cheat-protected since a Dec 2025 update: he can only get demos from servers that record (matchmaking,
  his own server with `tv_enable 1` + `tv_record`, services that hand out demos). Don't suggest workarounds.
- He learns best in **small pieces**: lead with 1–3 takeaways, short sections, offer to go deeper.
- Be honest about measurement limits (see `docs/measurement-notes.md`). Correct earlier claims openly when new numbers change them.

## Every session
```
git clone --depth 1 https://github.com/mojolowjo/cs2-demo-coach   # if not already here
bash setup.sh            # Python packages + newest awpy map data (radar images, wall geometry)
```
Copy each attached demo into its own folder in the scratchpad. Run scripts with `python3 -I`.

## Tools
- `tools/cs2coach.py DEMO.dem [--player m0j] [--round N] [rounds path sightings shots deaths]`
  Per round: path in callouts, teammates' spots, first sightings (wall-clear time and game-spotted time, crosshair offset, time to
  first shot), every shot (wait, inaccuracy, own speed, target, distance, yaw/pitch offset, body width, wall-clear, hit/miss),
  kills/deaths/trades, damage taken.
- `tools/export_replay.py OUT/demos.json [--merge OLD/demos.json] --demo "Label" DEMO.dem "YYYY-MM-DD HH:MM" [...] [--type practice]`
  Builds the data for the replay page (positions, wall check, shots, awpy stats, score, date) and copies `radar_<map>.png` next to it.
  WHEN is the local date/time the game was played (ask m0j or use the chat time); it drives the match history.
- `tools/duels.py`: ping, TrueView screen delay per player, fight detection (who peeked, head start, reaction, outcome).
- `tools/aim.py DEMO.dem [--reaction 150 220] [--json OUT]`: aim practice breakdown (click timing vs crosshair landing on the head,
  flick shape/corrections/overshoot, tracking lag and catch-up surges). Runs automatically in export for practice demos.
  Method, calibration and m0j's numbers (reaction 150–220 ms, 800 DPI × 1 sens, his track-then-click drill): `docs/aim.md`.
- `replay/index.html`: **m0j's CS2 ROOM** (published artifact: https://claude.ai/artifact/VNDU3fgne8WG5TGgzpZ2rY).
  Home (career stats, recent games) → Match history (`#history`: Year → Month → Day/Week/Month groups, numbered Match 1, 2, 3 within
  each group) → replay (`#demo-N`, `#demo-N-rK`) with radar / "your eyes" (wall check) views, "what you knew", kill feed, shot table,
  awpy stats and coach notes. Coach notes live in the `NOTES` object, keyed `"<demo file>|<segment label>"`.

## Steam lifetime stats
`.github/workflows/steam-stats.yml` runs daily (and on demand from the Actions tab) using the `STEAM_API_KEY` repo secret, and commits
`data/steam/latest.json` plus `data/steam/history/YYYY-MM-DD.json`. **Never ask for, store or print the key.** To refresh the page,
`git pull`, then publish with `data/steam/latest.json` as the artifact file `steam.json`. The page's home shows it in "Steam lifetime"
(tiles, top weapons, maps) and shows setup steps when the file is missing. Some counters may be CS:GO-era; say so when coaching from them.

## The laptop (main home now)
m0j's Windows laptop runs everything locally: see `laptop/README.md`. Its match history lives in
`C:\Users\mojol\Documents\CS2Room\data\demos.json`, not in this repo, and it gets code updates from this repo every 6 hours.
When this chat is linked to the laptop, read `CS2Room\logs\cs2room.log` first when something seems off.
After changing the tools, archived demos can be rebuilt with `cs2room.py reprocess` (keeps labels/dates).

## The public page (launcher)
**https://mojolowjo.github.io/cs2-demo-coach/** is now only a launcher (`launcher/index.html`, published by `.github/workflows/pages.yml`).
The real site runs on the laptop; the laptop exposes it through a Cloudflare quick tunnel (random `*.trycloudflare.com` address that
changes on restart) and commits the current address to `data/tunnel.json`; the launcher reads it (Pages copy + raw.githubusercontent)
and redirects. No password (m0j's choice). The site hides his SteamID; the "Check for new matches" button works at home (LAN, no Cloudflare
header) or for visitors signed in through Steam (OpenID, `/auth/steam`) whose SteamID64 is in `CS2Room\config\site_auth.json`
"allowed" (created with his ID). Live since Nov 24 2026: "CS2Room tunnel" task (`cs2room.py tunnel`), key in `config\github.dpapi` (fine-grained, this repo,
contents write). Steam sign-in through the tunnel still to be tried by m0j once.
The laptop site opens on the CS2 ROOM hub (player buttons); `#p-m0j` is m0j's page. Friends: their Steam profile links are in
`CS2Room\config\players.json` (`{"friends": [urls]}`, not in this repo); each run fetches their Steam name and whatever CS2 stats
they make public (`friend_stats()` → `data/steam/players/`), and the site shows them as `#p-<name>-<hash>` pages (no Steam IDs).
The claude.ai artifact (link above) is the older copy; update it too only if m0j still wants it.

## Adding a new demo (match history must keep growing)
`replay/demos.json` in this repo is the store of past matches.
1. `python3 -I tools/export_replay.py replay/demos.json --merge replay/demos.json --demo "Label" new.dem "YYYY-MM-DD HH:MM"`
2. Add coach notes for the new rounds to `NOTES` in `replay/index.html`.
3. Commit and push. The site rebuilds itself (check the Actions tab if it doesn't appear within a few minutes).

## Coaching frame (per round)
Rebuild what he knew (radar spots, likely-heard sounds, killfeed and alive counts, timer, money), then judge:
1. crosshair placement before contact (offset at first clear line, head height)
2. did he use the info he had (sound or radar → crosshair and position)
3. fight choice: isolated or tradeable, holding a long duel vs. resetting
4. trades given and received
5. timing: rotations, late-round time
6. moving while shooting
7. shot pacing vs. his own baseline, centering on a moving target

## Docs
- `docs/awpy.md`: main library, property names that work, map data and the wall check
- `docs/demoparser2.md`: the other parser, its bot gotcha, property aliases
- `docs/measurement-notes.md`: noise levels and pitfalls
- `docs/aim.md`: aim practice analysis (method, calibration, first sessions)
- `docs/getting-demos.md`: how m0j gets demos, plus `cfg/coach.cfg` for quick bot tests

Never commit raw demos (`*.dem`, they are large and contain Steam IDs). `replay/demos.json` is committed on purpose: it powers the site.
