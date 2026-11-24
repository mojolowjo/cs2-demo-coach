# cs2-demo-coach

Post-match CS2 coaching from demo files: round-by-round review of decisions, crosshair placement and shot pacing,
plus a 2D replay page ("m0j's CS2 Room").

Built and maintained by Claude. See [CLAUDE.md](CLAUDE.md) for how it's used.

```
bash setup.sh                                                  # packages + map data
python3 -I tools/cs2coach.py match.dem --player m0j            # text review
python3 -I tools/export_replay.py replay/demos.json "My match" match.dem   # replay data
```

- `tools/` analysis and export scripts
- `replay/` the replay page
- `cfg/coach.cfg` quick bot-match recording setup for CS2 ([how to use](docs/getting-demos.md))
- `docs/` notes on awpy, demoparser2, and measurement limits

Post-match analysis only. Nothing here reads a live game.
