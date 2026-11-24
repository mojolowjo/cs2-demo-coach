#!/usr/bin/env python3
"""cs2coach.py - post-match CS2 demo review for one player.

Usage:
  python3 -I cs2coach.py DEMO.dem [--player NAME] [--round N] [section ...]
Sections (default: all): rounds path sightings shots deaths
"""
import argparse, sys
import numpy as np, pandas as pd
from awpy import Demo

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 40)
TICK = 64
BODY_HALF_WIDTH_UNITS = 9.0   # rough player-model half width, for "was the crosshair on him" checks
MASK = "m_entitySpottedState.m_bSpottedByMask.0000"

def load(path):
    d = Demo(path)
    t = d.ticks(["X", "Y", "Z", "name", "team_num", "health", "velocity", "m_szLastPlaceName",
                 "m_angEyeAngles", "m_entitySpottedState.m_bSpotted", MASK]).to_pandas()
    t = t.rename(columns={"m_szLastPlaceName": "place", "m_entitySpottedState.m_bSpotted": "spotted", MASK: "mask"})
    a = t.m_angEyeAngles.astype(str).str.extract(r"QAngle\(([-\d.e]+), ([-\d.e]+)").astype(float)
    t["pitch"], t["yaw"] = a[0], a[1]
    t = t.drop(columns="m_angEyeAngles")
    t["mask"] = t["mask"].fillna(0).astype("int64")
    t = t[t.Z > -5000]                      # drop pre-spawn placeholder positions
    return d, t

def pick_player(d, t, name):
    if name: return name
    p = d.players.to_pandas()
    humans = p[p.steamid.astype(str).str.len() > 5]
    return humans.name.iloc[0] if len(humans) else t.name.value_counts().index[0]

def player_bit(d, t, me):
    """Find which bit in other players' spotted-by mask means 'seen by me' (vote over my kills)."""
    k = d.kills.to_pandas(); k = k[k.attacker_name == me]
    votes = {}
    for _, r in k.iterrows():
        v = t[(t.name == r.victim_name) & (t.tick.between(r.tick - 8, r.tick))]
        for m in v["mask"]:
            b = 0
            while m:
                if m & 1: votes[b] = votes.get(b, 0) + 1
                m >>= 1; b += 1
    return 1 << max(votes, key=votes.get) if votes else None

def angle_off(me, en, eye=64, target_h=60):
    dx, dy = en.X - me.X, en.Y - me.Y; dist = float(np.hypot(dx, dy))
    yaw = np.degrees(np.arctan2(dy, dx)); pit = -np.degrees(np.arctan2((en.Z + target_h) - (me.Z + eye), dist))
    dyaw = (yaw - me.yaw + 180) % 360 - 180; dp = pit - me.pitch       # dp > 0: aiming ABOVE target
    return float(dyaw), float(dp), dist

def sec(tick, fe): return round((tick - fe) / TICK, 2)

EYE = 64  # standing eye height in units (crouching is not modeled yet)

def get_checker(map_name):
    """Exact wall check from awpy map geometry. None if the map data isn't installed (run setup.sh)."""
    try:
        from awpy import VisibilityChecker
        return VisibilityChecker(map_name)
    except Exception as e:
        print(f"(wall check unavailable: {e})")
        return None

def los_series(vc, me_rows, en_rows):
    """Clear eye-to-eye line for aligned rows of me and an enemy. Returns a bool array."""
    a = np.column_stack([me_rows.X, me_rows.Y, me_rows.Z + EYE]).astype("float64")
    b = np.column_stack([en_rows.X, en_rows.Y, en_rows.Z + EYE]).astype("float64")
    return np.asarray(vc.is_visible_many(a, b).to_list(), dtype=bool)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("demo"); ap.add_argument("--player"); ap.add_argument("--round", type=int)
    ap.add_argument("sections", nargs="*", default=["rounds", "path", "sightings", "shots", "deaths"])
    A = ap.parse_args()
    d, t = load(A.demo); me = pick_player(d, t, A.player); bit = player_bit(d, t, me)
    rounds = d.rounds.to_pandas(); sh = d.shots.to_pandas(); dm = d.damages.to_pandas(); kl = d.kills.to_pandas()
    map_name = d.header.get("map_name") if isinstance(d.header, dict) else ""
    vc = get_checker(map_name) if map_name else None
    print(f"map {map_name} | player {me} | seen-by-me bit {bit} | wall check {'on' if vc else 'off'}")
    if "rounds" in A.sections:
        print(rounds[["round_num", "freeze_end_tick", "end_tick", "winner_side", "reason_name"]].to_string(index=False))
    for _, r in rounds.iterrows():
        if A.round and r.round_num != A.round: continue
        fe, end = r.freeze_end_tick, r.end_tick
        R = t[t.tick.between(fe, end)]; u = R[R.name == me].set_index("tick")
        if u.empty: continue
        team = u.team_num.iloc[0]; side = "CT" if team == 3 else "T"
        alive = u[u.health > 0]
        print(f"\n===== ROUND {r.round_num} | you {side} | {r.winner_side} won ({r.reason_name}) | alive until {sec(alive.index.max(), fe)}s =====")
        if "path" in A.sections:
            pl = alive.place; seg = pl[pl != pl.shift()]
            print("path:", " -> ".join(f"{p}@{sec(tk, fe)}s" for tk, p in seg.items()))
            mates = R[(R.team_num == team) & (R.name != me) & (R.tick == alive.index.max())]
            print("teammates at your last alive tick:", ", ".join(f"{m.name}({m.place},{m.health}hp)" for m in mates.itertuples()))
        enemies = R[(R.team_num != team) & (R.team_num > 1)]
        if "sightings" in A.sections and bit:
            print("-- first sightings ('game' = the game's approximate spotted check, 'wall' = exact eye-to-eye line through map geometry)")
            ualive = u[u.health > 0]
            for nm, g in enemies.groupby("name"):
                g = g.set_index("tick"); g = g[g.health > 0]
                seen = g[(g["mask"] & bit) > 0]
                first_wall = None
                if vc is not None:
                    common = g.index.intersection(ualive.index)
                    if len(common):
                        clear = los_series(vc, ualive.loc[common], g.loc[common])
                        if clear.any(): first_wall = common[int(np.argmax(clear))]
                if seen.empty and first_wall is None: continue
                ft = seen.index.min() if len(seen) else first_wall
                ref = min(x for x in [ft, first_wall] if x is not None)
                dyaw, dp, dist = angle_off(u.loc[ref], g.loc[ref])
                fs = sh[(sh.name == me) & sh.tick.between(ref - 32, ref + 640)]
                wall_txt = f"wall-clear {sec(first_wall, fe)}s" if first_wall is not None else "wall-clear never"
                game_txt = f"game-spotted {sec(ft, fe)}s" if len(seen) else "game-spotted never"
                print(f"  {nm}: {wall_txt}, {game_txt} | you in {u.loc[ref].place}, him in {g.loc[ref].place}, {dist:.0f}u | crosshair off yaw {dyaw:+.1f} pitch {dp:+.1f} deg at first sight | first shot {sec(fs.tick.min(), ref) if len(fs) else '-'}s after")
            sb = u[(u["mask"] > 0)]
            if len(sb): print(f"  first time ANY enemy spotted you: {sec(sb.index.min(), fe)}s in {sb.iloc[0].place}")
        if "shots" in A.sections:
            s = sh[(sh.name == me) & sh.tick.between(fe, end) & ~sh.weapon.str.contains("knife|grenade|flash|smoke|molotov|decoy|c4", na=False)].sort_values("tick")
            if len(s):
                print("-- your shots (target = enemy with smallest crosshair offset; inaccuracy: compare to your fresh-shot baseline for that weapon)")
                prev = None; rows = []
                for x in s.itertuples():
                    tk = x.tick; gap = None if prev is None else round((tk - prev) / TICK, 2); prev = tk
                    if tk not in u.index: continue
                    best = None
                    # use the tick BEFORE the shot: on a killing shot the victim already reads 0 hp
                    for nm, g in enemies[enemies.tick == tk - 1].groupby("name"):
                        e = g.iloc[0]
                        if e.health <= 0: continue
                        dyaw, dp, dist = angle_off(u.loc[tk], e)
                        seen = bool(e["mask"] & bit) if bit else None
                        score = abs(dyaw) + abs(dp) + (0 if seen else 1000)   # prefer enemies you could see
                        if best is None or score < best[6]: best = (nm, dyaw, dp, dist, e.velocity, seen, score, e)
                    hit = dm[(dm.tick == tk) & (dm.attacker_name == me)]
                    res = ("HIT " + hit.victim_name.iloc[0] + " " + hit.hitgroup_name.iloc[0] + f" -{hit.dmg_health.iloc[0]}") if len(hit) else "miss"
                    if best:
                        hw = np.degrees(np.arctan2(BODY_HALF_WIDTH_UNITS, best[3]))
                        rows.append(dict(t=sec(tk, fe), weapon=x.weapon.replace("weapon_", ""), gap=gap, inacc=round(x.inaccuracy, 3),
                                         your_speed=round(u.loc[tk].velocity), target=best[0], dist=round(best[3]), yaw_off=round(best[1], 1),
                                         body_halfw=round(hw, 1), on_body=abs(best[1]) <= hw, pitch_off=round(best[2], 1),
                                         target_speed=round(best[4]), seen=best[5],
                                         wall_clear=(bool(vc.is_visible((float(u.loc[tk].X), float(u.loc[tk].Y), float(u.loc[tk].Z) + EYE),
                                                                         (float(best[7].X), float(best[7].Y), float(best[7].Z) + EYE))) if vc else None),
                                         result=res))
                    else:
                        rows.append(dict(t=sec(tk, fe), weapon=x.weapon.replace("weapon_", ""), gap=gap, inacc=round(x.inaccuracy, 3), result=res))
                print(pd.DataFrame(rows).to_string(index=False))
        if "deaths" in A.sections:
            k = kl[kl.tick.between(fe, end) & ((kl.attacker_name == me) | (kl.victim_name == me) | (kl.assister_name == me))]
            if len(k):
                print("-- your kills/deaths/assists")
                print(k.assign(t=(k.tick - fe) / TICK)[["t", "attacker_name", "victim_name", "assister_name", "weapon", "headshot", "is_trade", "victim_traded"]].to_string(index=False))
            hurt = dm[dm.tick.between(fe, end) & (dm.victim_name == me)]
            if len(hurt):
                print("-- damage you took"); print(hurt.assign(t=(hurt.tick - fe) / TICK)[["t", "attacker_name", "weapon", "dmg_health", "hitgroup_name", "health_post"]].to_string(index=False))

if __name__ == "__main__":
    main()
