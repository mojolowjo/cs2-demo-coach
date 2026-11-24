"""Export one or more CS2 demos into a compact JSON for the replay page.
usage: python3 -I export_replay.py OUT_DIR/demos.json LABEL1 DEMO1 [LABEL2 DEMO2 ...]
Also copies the map's radar image (radar_<map>.png) next to demos.json when the awpy map data is installed.
"""
import sys, json, math, os
import numpy as np, pandas as pd
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from cs2coach import load, pick_player, player_bit, angle_off, get_checker, los_series, BODY_HALF_WIDTH_UNITS, TICK

OUT_DIR = "."

STEP = 4  # keep every 4th tick (16 frames per second)

def r1(v): return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 1)

def export(label, path):
    d, t = load(path)
    me = pick_player(d, t, "m0j" if "m0j" in set(t.name) else None)
    bit = player_bit(d, t, me) or 1
    rounds = d.rounds.to_pandas(); sh = d.shots.to_pandas(); dm = d.damages.to_pandas(); kl = d.kills.to_pandas()
    ev = d.events
    connect = ev["player_connect"].to_pandas() if "player_connect" in ev.names else pd.DataFrame(columns=["userid", "name"])
    uid = {str(r.userid): r.name for r in connect.itertuples()}; uid.setdefault("0", me)
    fs = ev["player_footstep"].to_pandas() if "player_footstep" in ev.names else pd.DataFrame(columns=["tick", "userid"])
    header = d.header if isinstance(d.header, dict) else {}
    map_name = header.get("map_name", "")
    vc = get_checker(map_name) if map_name else None
    radar = None
    try:  # real radar image + its world->pixel transform, copied next to the output file
        from awpy import data as awdata
        import shutil, os
        src = awdata.radar_path(map_name); md = awdata.map_data()[map_name]
        fname = f"radar_{map_name}.png"; shutil.copy(src, os.path.join(OUT_DIR, fname))
        radar = dict(file=fname, pos_x=md["pos_x"], pos_y=md["pos_y"], scale=md["scale"])
    except Exception as e:
        print(f"(no radar image for {map_name}: {e})")

    alive_t = t[(t.health > 0)]
    places = (alive_t[alive_t.place.astype(str).str.len() > 0].groupby("place")[["X", "Y"]].median().reset_index())

    if len(rounds):
        segs = [dict(label=f"Round {int(r.round_num)}", start=int(r.start_tick), fe=int(r.freeze_end_tick), end=int(r.end_tick) + 96,
                     winner=r.winner_side, reason=r.reason_name) for r in rounds.itertuples()]
    else:
        first = int(t[(t.name == me) & (t.health > 0) & (t.tick > t.tick.min() + 64)].tick.min())
        jump = t[t.name == me].sort_values("tick"); jump = jump[jump.tick > first]
        dx = np.hypot(jump.X.diff(), jump.Y.diff()); tp = jump[dx > 200].tick
        start = int(tp.iloc[0]) if len(tp) else first
        segs = [dict(label="Prefire run", start=start, fe=start, end=int(t.tick.max()), winner=None, reason=None)]

    out_segs = []
    for s in segs:
        R = t[(t.tick >= s["start"]) & (t.tick <= s["end"])]
        ticks = sorted(set(R.tick[(R.tick - s["start"]) % STEP == 0]))
        R = R[R.tick.isin(ticks)]
        players = {}
        for nm, g in R.groupby("name"):
            g = g.set_index("tick").reindex(ticks)
            team = int(g.team_num.dropna().iloc[-1]) if g.team_num.notna().any() else 0
            if team < 2: continue
            players[nm] = dict(team=team,
                               x=[None if math.isnan(v) else int(v) for v in g.X], y=[None if math.isnan(v) else int(v) for v in g.Y],
                               yaw=[None if math.isnan(v) else int(v) for v in g.yaw],
                               hp=[0 if math.isnan(v) else int(v) for v in g.health],
                               seen=[int((int(m) & bit) > 0) if not math.isnan(m) else 0 for m in g["mask"].astype(float)],
                               spotted=[int(bool(v)) if v == v and v is not None else 0 for v in g.spotted],
                               place=[str(v) if isinstance(v, str) else "" for v in g.place])
        myteam = players.get(me, {}).get("team", 0)
        # exact wall check: clear eye-to-eye line between me and each enemy, per frame
        if vc is not None and me in players:
            gm = R[R.name == me].set_index("tick").reindex(ticks)
            for nm, g in R.groupby("name"):
                if nm == me or nm not in players or players[nm]["team"] == myteam: continue
                g = g.set_index("tick").reindex(ticks)
                ok = (gm.health > 0) & (g.health > 0) & gm.X.notna() & g.X.notna()
                los = np.zeros(len(ticks), dtype=int)
                if ok.any():
                    los[ok.values] = los_series(vc, gm[ok], g[ok]).astype(int)
                players[nm]["los"] = los.tolist()
        k = kl[(kl.tick >= s["start"]) & (kl.tick <= s["end"])]
        kills = [dict(tick=int(x.tick), att=x.attacker_name if isinstance(x.attacker_name, str) else None, vic=x.victim_name,
                      ast=x.assister_name if isinstance(x.assister_name, str) else None,
                      weapon=x.weapon, hs=bool(x.headshot), ax=r1(x.attacker_x), ay=r1(x.attacker_y), vx=r1(x.victim_x), vy=r1(x.victim_y),
                      attSide=x.attacker_side, vicSide=x.victim_side) for x in k.itertuples()]
        # shots by me, with target analysis
        enemies = t[(t.tick >= s["start"]) & (t.tick <= s["end"]) & (t.team_num != myteam) & (t.team_num > 1)]
        u = t[(t.name == me)].set_index("tick")
        S = sh[(sh.name == me) & (sh.tick >= s["fe"]) & (sh.tick <= s["end"]) & ~sh.weapon.str.contains("knife|grenade|flash|smoke|molotov|decoy|c4", na=False)].sort_values("tick")
        shots, prev = [], None
        for x in S.itertuples():
            tk = int(x.tick); gap = None if prev is None else round((tk - prev) / TICK, 2); prev = tk
            best = None
            if tk in u.index:
                for nm, g in enemies[enemies.tick == tk - 1].groupby("name"):
                    e = g.iloc[0]
                    if e.health <= 0: continue
                    dyaw, dp, dist = angle_off(u.loc[tk], e)
                    seen = bool(int(e["mask"]) & bit)
                    score = abs(dyaw) + abs(dp) + (0 if seen else 1000)
                    if best is None or score < best[-1]: best = (nm, dyaw, dp, dist, e.velocity, seen, score)
            hit = dm[(dm.tick == tk) & (dm.attacker_name == me)]
            row = dict(tick=tk, weapon=x.weapon.replace("weapon_", ""), gap=gap, inacc=round(float(x.inaccuracy), 3),
                       speed=int(u.loc[tk].velocity) if tk in u.index and u.loc[tk].velocity == u.loc[tk].velocity else None,
                       hit=(hit.victim_name.iloc[0] if isinstance(hit.victim_name.iloc[0], str) else "target") if len(hit) else None,
                       hitgroup=hit.hitgroup_name.iloc[0] if len(hit) else None, dmg=int(hit.dmg_health.iloc[0]) if len(hit) else None)
            if best and best[5]:
                hw = math.degrees(math.atan2(BODY_HALF_WIDTH_UNITS, best[3]))
                row.update(target=best[0], dist=int(best[3]), yawOff=round(best[1], 1), pitchOff=round(best[2], 1), halfW=round(hw, 1),
                           onBody=abs(best[1]) <= hw, tSpeed=int(best[4]) if best[4] == best[4] else None)
            shots.append(row)
        f = fs[(fs.tick >= s["start"]) & (fs.tick <= s["end"])]
        steps = []
        for x in f.itertuples():
            nm = uid.get(str(x.userid));
            if not nm: continue
            p = t[(t.name == nm) & (t.tick == int(x.tick))]
            if len(p): steps.append(dict(tick=int(x.tick), name=nm, x=int(p.X.iloc[0]), y=int(p.Y.iloc[0])))
        hurt = dm[(dm.tick >= s["start"]) & (dm.tick <= s["end"]) & ((dm.victim_name == me) | (dm.attacker_name == me))]
        dmg = [dict(tick=int(x.tick), att=x.attacker_name if isinstance(x.attacker_name, str) else None,
                    vic=x.victim_name if isinstance(x.victim_name, str) else "target", weapon=x.weapon, dmg=int(x.dmg_health),
                    hg=x.hitgroup_name, hpAfter=int(x.health_post)) for x in hurt.itertuples()]
        bomb = []
        for n in ["bomb_planted", "bomb_defused", "bomb_exploded"]:
            if n in ev.names:
                b = ev[n].to_pandas(); b = b[(b.tick.astype(int) >= s["start"]) & (b.tick.astype(int) <= s["end"])]
                bomb += [dict(tick=int(x), kind=n.replace("bomb_", "")) for x in b.tick]
        A = sh[(sh.tick >= s["start"]) & (sh.tick <= s["end"]) & ~sh.weapon.str.contains("knife|grenade|flash|smoke|molotov|decoy|c4", na=False)]
        gunfire = [dict(tick=int(x.tick), name=x.name, x=int(x.x), y=int(x.y)) for x in A.itertuples() if x.x == x.x]
        out_segs.append(dict(label=s["label"], start=s["start"], fe=s["fe"], end=s["end"], winner=s["winner"], reason=s["reason"],
                             myTeam=myteam, ticks=ticks, players=players, kills=kills, shots=shots, footsteps=steps, damage=dmg, bomb=bomb,
                             gunfire=gunfire))
    return dict(label=label, file=path.rsplit("/", 1)[-1], map=map_name, me=me, radar=radar, wallCheck=vc is not None,
                places=[dict(name=r.place, x=int(r.X), y=int(r.Y)) for r in places.itertuples()],
                bounds=dict(minX=int(alive_t.X.min()), maxX=int(alive_t.X.max()), minY=int(alive_t.Y.min()), maxY=int(alive_t.Y.max())),
                segments=out_segs)

if __name__ == "__main__":
    out = sys.argv[1]; args = sys.argv[2:]
    OUT_DIR = os.path.dirname(os.path.abspath(out)); os.makedirs(OUT_DIR, exist_ok=True)
    demos = [export(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    def clean(o):
        if isinstance(o, float): return None if math.isnan(o) or math.isinf(o) else o
        if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list): return [clean(v) for v in o]
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return clean(float(o))
        if isinstance(o, (np.bool_,)): return bool(o)
        return o
    with open(out, "w") as fh: json.dump(clean(dict(demos=demos)), fh, separators=(",", ":"), allow_nan=False)
    for dd in demos:
        print(dd["label"], dd["map"], dd["me"], [(s["label"], len(s["ticks"]), len(s["players"]), len(s["kills"]), len(s["shots"]), len(s["footsteps"])) for s in dd["segments"]])
