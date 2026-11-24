# awpy notes (main library)

[awpy](https://github.com/pnxenopoulos/awpy) (v3.3+) is a higher-level CS2 analysis library with its own Rust reader.
It keeps bots, resolves names and sides on events, and ships map tools.

```python
from awpy import Demo, VisibilityChecker
d = Demo("match.dem")
d.rounds, d.kills, d.damages, d.shots, d.grenades, d.smokes, d.fires, d.blinds, d.bomb, d.players   # polars DataFrames
d.events.names; d.events["player_footstep"]                    # raw game events (userid -> name via d.events["player_connect"])
d.ticks(["X", "Y", "Z", "name", "team_num", "health", "velocity", "m_szLastPlaceName", "m_angEyeAngles",
         "m_entitySpottedState.m_bSpotted", "m_entitySpottedState.m_bSpottedByMask.0000"])
```

## Property names that work with `d.ticks`

| Field | Notes |
|---|---|
| `X`, `Y`, `Z`, `velocity`, `health`, `armor`, `team_num`, `name`, `money` | built-in aliases |
| `m_szLastPlaceName` | callout. (`last_place_name` alias does NOT work in awpy) |
| `m_angEyeAngles` | string `QAngle(pitch, yaw, 0)`, parse with a regex. (`yaw`/`pitch` aliases do NOT work) |
| `m_entitySpottedState.m_bSpotted` | on the enemy team's radar |
| `m_entitySpottedState.m_bSpottedByMask.0000` | bitmask of who can see this player. Infer "my" bit by voting over my kills (see `tools/cs2coach.py`) |

`d.shots` has per-shot `inaccuracy`, position and view angles for every player. `d.kills` has `is_trade` / `victim_traded`.

## Map data (radar images + wall geometry)

Published as GitHub releases of `pnxenopoulos/awpy-data`, tagged by CS2 `ClientVersion`. Contains `images.zip` (radar PNGs),
`geometry.zip` (`.mesh` collision for line of sight), `navs.zip`, `map_data.json` (world-to-radar transform per map).

In Claude's workspace, `awpy get` with no version fails (403): it asks `api.github.com` for the latest tag, which is blocked.
The direct download links work. `setup.sh` finds the newest tag with `git ls-remote --tags` and runs `awpy get <tag>`.
The cache lives in `~/.awpy/<tag>/` and is wiped with the workspace, so run `setup.sh` every session (~50 MB, under a minute).

```python
vc = VisibilityChecker("de_dust2")
vc.is_visible((x1, y1, z1 + 64), (x2, y2, z2 + 64))   # eye to eye, standing eye height 64
vc.is_visible_many(starts_Nx3, ends_Nx3)              # vectorized, returns a polars Series
```

Static geometry only: smokes, doors and bullet penetration aren't modeled. Crouching isn't handled in our tools yet (eye 64 always).

Radar transform (radar image is 1024 px): `px = (x - pos_x) / scale`, `py = (pos_y - y) / scale`.
