# demoparser2 notes

[demoparser2](https://github.com/LaihoE/demoparser) is a fast, low-level CS2 demo reader (Rust core, Python and JS bindings).
You *query* it for raw properties or events and get pandas DataFrames back. We started with it, then moved the main tools to awpy
(see [awpy.md](awpy.md)). These notes are here for when we need it again.

## Install / use

```
pip install --break-system-packages demoparser2 pandas
```

```python
from demoparser2 import DemoParser
p = DemoParser("match.dem")
p.parse_header()                      # map_name, server_name, game_directory, ...
p.list_game_events()                  # which events this demo actually contains
p.parse_player_info()                 # steamid, name, team_number - bots included here
p.parse_ticks(["X", "Y", "Z", "health", "team_num", "is_alive", "active_weapon_name", "last_place_name"])
p.parse_event("player_death", player=["X", "Y", "last_place_name"], other=["total_rounds_played"])
p.parse_event("player_hurt")          # dmg_health, hitgroup, weapon, attacker/user names
p.parse_event("weapon_fire")
```

`player=[...]` on `parse_event` adds attacker_/user_ prefixed columns with each player's props at that tick.

## The big gotcha: bots disappear from per-tick data

`parse_ticks` (and the attacker/victim names on events) **dropped every bot** in our bot-match demo. Bots have tiny
"steamids" (2, 3, 4...), and only the human player came back. `parse_player_info()` still lists the bots, so the data is in the
file, but the tick and event tables leave them out.

- Real matchmaking/FACEIT demos (10 humans): demoparser2 is fine.
- Anything with bots (practice demos, prefire maps): use awpy.

## Useful property names (demoparser2 aliases)

| Alias | Meaning |
|---|---|
| `X`, `Y`, `Z` | position (Hammer units) |
| `pitch`, `yaw` | view angles. Pitch positive = looking down |
| `last_place_name` | callout (LongDoors, LongA, Pit is inside LongA on Dust2, MidDoors, ...) |
| `spotted` | visible on the enemy team's radar |
| `approximate_spotted_by` | who can see this player (game's approximate check) |
| `velocity_X`, `velocity_Y` | movement |
| `is_alive`, `health`, `armor_value`, `has_helmet`, `balance` | state |
| `FORWARD`, `LEFT`, `RIGHT`, `BACK`, `FIRE` | buttons held |
| `accuracy_penalty`, `i_recoil_idx` | gun accuracy state |

## Other things we found

- Before spawning, players sit at Z ≈ -5120 (placeholder positions). Filter `Z > -5000` before drawing or counting.
- The demo stores sound-making *events* (`player_footstep`, `weapon_fire`, `weapon_reload`, grenade and bomb events), not audio.
- A client `record` demo of a prefire workshop map still contains the workshop bots.
