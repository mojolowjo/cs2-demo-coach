# Measurement notes (what we learned the hard way)

- **Placeholder positions.** Before spawning, players read Z ≈ -5120. Drop `Z < -5000`.
- **Which enemy a shot was at.** Measure against enemies at the tick *before* the shot: on a killing shot the victim already reads 0 hp.
  Prefer enemies with a clear line / spotted by me.
- **Aim noise.** Treat about ±0.5° as measurement noise (1 tick of target movement at 450u is about 0.5°). Don't make
  "N shots were off his body" claims from differences smaller than that.
- **Body width.** We use a 9-unit half-width estimate. At ~450u that's about ±1.2° from your view.
- **Pitch offset.** `pitch_off > 0` = aiming above the target point (enemy Z + 60).
- **Shot pacing.** The demo's `inaccuracy` value is in game units. Compare each shot to the player's *own* fresh-shot level for that
  weapon (first shot after a long pause), not an official number. First test, Deagle: fresh ≈ 0.069–0.074. Taps ~0.45–0.5s apart
  stayed near it; 0.25–0.3s apart rose to ≈ 0.088–0.095.
- **Who could see whom.** Two sources:
  - the game's spotted mask: approximate, lags and flickers mid-fight;
  - the exact wall check (`VisibilityChecker`): better. First test: line opened at 18.81s, game flagged at 19.23s.
  A single-frame "clear" blip can happen at edges. Look for a sustained run before calling it "the line opened".
- **Sounds.** Only sound-making events are stored. "Heard" is an estimate by distance (footsteps ~1100u, gunfire ~2500u), no walls.
- **Can't know:** voice comms, what was on screen beyond the data, the player's reasons. Ask.
- **Ping vs screen delay.** `m_iPing` is the scoreboard ping. Screen delay comes from each usercmd's input history (TrueView data,
  every player, in every recent server demo): simulated tick − rendered tick = how far behind the server that screen was
  (ping + interpolation). First Cache match: m0j 111 ms, lobby 37–98 ms. Values over 40 ticks (625 ms) are reconnects, dropped.
- **Duels** (`tools/duels.py`): a clear line opens after ≥ 0.25 s without one and someone shoots / takes damage within 3 s.
  Who peeked = the one moving (> 110 u/s) while the other wasn't (< 70 u/s); otherwise "both moving"/"both still".
  Head start ≈ (peeker delay + holder delay) / 2. An estimate from both screens' delays, not a measurement of either screen.
  Reaction = first shot − when he appeared on m0j's screen; < 150 ms = prefire, > 1 s = "late shot" (waited / repositioned).
- **"Your screen" view** draws every other player at (now − m0j's screen delay): where his screen had them. It's a reconstruction
  from server positions, so it can't show client-side prediction quirks.
- **View angles vs ticks.** The input-history clock (`player_tick_count + fraction`) is about one tick off the demo tick: align it to
  the server's shot angles before comparing the crosshair with positions (tools/aim.py does). Early aim numbers on Nov 23 2026 were
  made before this fix; the "behind the bot" result held after it.
- **Head point.** Calibrated from his headshots: about Z+64.5 to 65.5 above the bot's origin (not Z+60/62 as first assumed).
- **Local server delay.** On his own listen server his screen is exactly 1 tick (15.6 ms) behind: no ping, no buffer.
