# cs2-demo-coach: instructions for Claude

This repo is Claude's toolkit for coaching **m0j** (GitHub `mojolowjo`) in CS2 from demo files.
Claude builds and maintains it. m0j attaches demos in chat; Claude analyzes them and updates his replay page.

## Ground rules
- **Post-match only.** m0j has said clearly he doesn't want to cheat. Never build anything that feeds live game info.
  Don't keep repeating the warning; he knows.
- Main focus: **decision making** (what he could read from radar, sound and the killfeed, and whether his choice was good).
  Then crosshair placement before contact, and shot pacing.
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
- `replay/index.html`: **m0j's CS2 ROOM** (published artifact: https://claude.ai/artifact/VNDU3fgne8WG5TGgzpZ2rY).
  Home (career stats, recent games) → Match history (`#history`: Year → Month → Day/Week/Month groups, numbered Match 1, 2, 3 within
  each group) → replay (`#demo-N`, `#demo-N-rK`) with radar / "your eyes" (wall check) views, "what you knew", kill feed, shot table,
  awpy stats and coach notes. Coach notes live in the `NOTES` object, keyed `"<demo file>|<segment label>"`.

## Adding a new demo to the page (match history must keep growing)
The workspace is wiped between sessions, so the **published artifact is the store of past matches**:
1. `Artifact read` the page URL with `path: "demos.json"` (and the radar PNGs if needed) to get the current data.
2. `python3 -I tools/export_replay.py out/demos.json --merge <downloaded demos.json> --demo "Label" new.dem "YYYY-MM-DD HH:MM"`
3. Add coach notes for the new rounds to `NOTES` in `replay/index.html`.
4. Publish `replay/index.html` to the same URL with `demos.json` and `radar_*.png` as files. Commit and push tool/page changes here.

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
- `docs/getting-demos.md`: how m0j gets demos, plus `cfg/coach.cfg` for quick bot tests

Never commit demos (`*.dem`, they contain Steam IDs) or generated replay data.
