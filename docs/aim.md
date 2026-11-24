# Aim analysis (tools/aim.py)

For practice demos on aim maps (first one: `aim_fastreflex07`, bots running around, m0j standing in the middle with an AK).
`export_replay.py` runs it automatically for practice demos in Aim training / Bots / Refrag / Other practice and stores the result
as `aim` in the demo file (plus a headline in the `.meta.json`), and per shot `settle`, `cls`, `headErr` in the shots table.

```
python3 -I tools/aim.py DEMO.dem [--reaction 150 220] [--json out.json]
```

## m0j's numbers to keep in mind
- Reaction time: **150–220 ms** (online tests ~170 ms average). A click less than ~150 ms after the crosshair lands can't be a
  reaction to seeing it there: it was decided while the crosshair was still moving.
- Sensitivity 1, 800 DPI → eDPI 800, about **52 cm / 360°**. Pulsar Xlite V3 eS, 500 Hz; Motion Sync turned off on Nov 23 2026 (sessions before that had it on).
- His drill goal (Nov 2026): **track the head, then click** (not flick-click). He is already good at timed flick-clicks.

## Data sources
- **Shot angle**: the server's `weapon_fire` angles (awpy `shots.pitch/yaw`), exact (sub-tick).
- **View angle over time**: TrueView input history (`usercmd_input_history`, demoparser2). At most 4 samples per tick, so about
  **250 samples/s** whatever his FPS or mouse polling. Server-recorded demos only (`tv_record`, matchmaking).
- **Bots**: positions every tick (awpy ticks). Demos have no bones, so the head is a point: bot origin Z + `headZ`.

## Calibration (done per demo, printed by the tool)
- **Time alignment**: history time `player_tick_count + fraction` minus a constant ≈ demo tick. The tool searches the shift
  (1/8-tick steps) where the history angle matches the server's shot angles. On m0j's local server it came out at **+1.125 ticks**
  past the plain offset, with a 0.01–0.02° match. Without it the crosshair reads about one tick (≈0.4° on running bots) late.
- **Head height**: `headZ` is fitted so his headshot hits are centred vertically. Came out at Z+64.5 to 65.5 (eye = Z+64).
  Bot positions at the shot tick (not tick−1) gave the tightest left-right spread for headshots (~1.0° SD).
- On a killing shot the victim already reads 0 hp / speed 0 at the shot tick: speed and "alive" are read at tick−1.

## What each number means
- **Click classes** (single taps at bots running > 100 u/s, sprays ≤ 0.12 s apart excluded): settle = how long the crosshair had
  been within 1.5° of the head before the shot. `early` < 16 ms, `timed` < 150 ms, `grey` 150–220, `tracked` > 220 ms.
- **Flicks**: view movements (speed > 30°/s, dips under 40 ms merged) of 8° or more that end within 6° of a bot's head.
  `tPeak` = where in the movement the top speed is (0.5 = a smooth bell; real hands ~0.45). `corrections` = extra speed peaks.
  `primaryErr` = where the first motion stopped vs the head, along the flick direction (+ past it, − short). Over/under use ±1°.
- **Tracking**: stretches ≥ 200 ms with the crosshair within 2.5° of a running bot's head. `lead` + ahead / − behind, `ratio` =
  his aim speed ÷ the bot's, `surges` = share of time his aim moved more than twice the bot's speed (catch-up bursts).

## Limits
- Head width at 300–500 u is only about ±0.5–1°: differences under ~0.5° are noise.
- One 5-minute session gives ~200 flicks / ~200 taps: fine for trends, not for small differences (wrist vs arm).
- Open question (Nov 2026): tracked shots read closer to the head than timed ones but hit less often. Not explained by leftover
  inaccuracy (checked). Possibly bot direction changes or lag compensation details; look again with more sessions.

## First sessions (Nov 23 2026, aim_fastreflex07, AK, standing)
| | prac1 | prac2 wrist | prac3 arm |
|---|---|---|---|
| minutes / kills / HS | 1.8 / 49 / 46 | 4.8 / 106 / 106 | 5.0 / 131 / 128 |
| hit % / kills per min | 36 / 27 | 48 / 22 | 40 / 26 |
| early / timed / tracked hit % | 24 / 85 / 42 | 29 / 88 / 60 | 29 / 70 / 53 |
| clicked early | 43% | 47% | 46% |
| flick corrections / over / under | 23 / 35 / 33 % | 39 / 33 / 40 % | 36 / 40 / 37 % |
| tracking error / lead / surges | 1.25° / −0.36° / 20% | 1.2° / −0.4° / 15% | 1.2° / −0.27° / 18% |
Arm overshot big flicks (60°+: 52% over vs 26% under); wrist did not.
