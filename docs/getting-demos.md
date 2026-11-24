# Getting a demo

Claude's workspace can't download demos from Valve and can't use the match-history auth code, so the demo has to be attached in chat.

## Real matches (Premier / Competitive)
- CS2 → **Watch → Your Matches** → pick a match → **Download**. The `.dem` lands in
  `~/.local/share/Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/replays/`.
- Or `https://steamcommunity.com/my/gcpd/730?tab=matchhistorypremier` (or `matchhistorycompetitive`) → **Download GOTV Replay**
  (`.dem.bz2`; unpack with `bunzip2`). About 30 days kept.

## Quick bot tests (no full game needed)
Copy `cfg/coach.cfg` into `.../game/csgo/cfg/`, then in the console:

1. `exec coach`
2. a map alias: `dust2`, `mirage`, `inferno`, `nuke`, `ancient`, `anubis`
3. once loaded: `go` (3 rounds, medium bots, skip warmup, start recording)
4. `done` when finished → `.../game/csgo/coach.dem` (overwritten each time; rename to keep)

Server-side GOTV recording (`tv_enable 1` before the map loads) is the only way to record on your own: since a Dec 2025 update the
client `record` command is cheat-protected ("command ignored" on any server without `sv_cheats 1`). On servers he joins, only the
server's own demos are available. Checked every demo command (CSDB / TotalCSGO lists, Nov 2026): none records client-side.

## Aim practice on your own server
1. `tv_enable 1` (before the map loads)
2. load the aim map (e.g. aim_fastreflex07 from the Workshop)
3. `tv_record prac1` once in, `tv_stoprecord` when done. Same weapon and stance each time so sessions compare (docs/aim.md).
