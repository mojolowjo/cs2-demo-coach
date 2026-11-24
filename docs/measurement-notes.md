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
