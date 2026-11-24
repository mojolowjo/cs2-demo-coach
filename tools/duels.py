"""Screen delay (TrueView input history), ping, and duel detection for one player.

Screen delay: every usercmd in a CS2 demo carries input-history entries with the tick the client was RENDERING and the tick it
was SIMULATING. simulated - rendered = how far behind the server that player's screen was (ping + interpolation), per player.

Duel = a moment when a clear eye-to-eye line opens between me and an enemy (wall check) and someone shoots or takes damage in
the next 3 s. For each duel:
  who peeked      the one moving (> 110 u/s) in the 0.25 s before the line opened while the other wasn't (< 70 u/s)
  edge_ms         estimated head start from MY side: + I saw him first, - he saw me first. A peeker sees the holder first by about
                  (peeker delay + holder delay) / 2. Estimate, not a measurement of either screen.
  appear          when he showed up on MY screen: line-open time, pushed later by my disadvantage when he peeked
  reaction        prefire (my first shot < 150 ms after appear) | already shooting (I fired in the 0.5 s before) |
                  reaction (150-1000 ms from appear to first shot, plus flick start) | late shot (> 1 s) | no shot
  outcome         won / lost (kill), won / lost on damage, or even
"""
import math, statistics
import numpy as np, pandas as pd

TICK_MS = 1000 / 64
LAG_MAX_TICKS = 40          # > 625 ms is a reconnect / hiccup, not real delay

def screen_delays(path, names=None):
    """{player name: pandas Series(tick -> delay ms)}, smoothed; empty for players without usercmds (bots)."""
    try:
        from demoparser2 import DemoParser
        t = DemoParser(path).parse_ticks(["usercmd_input_history"])
    except Exception as e:
        print(f"(no input history: {e})"); return {}
    out = {}
    t = t[t.usercmd_input_history.notna()]
    for name, g in t.groupby("name"):
        if names and name not in names: continue
        vals = []
        for h in g.usercmd_input_history:
            if h is None or len(h) == 0: vals.append(np.nan); continue
            e = h[0]
            d = (e["player_tick_count"] + e["player_tick_fraction"]) - (e["render_tick_count"] + e["render_tick_fraction"])
            vals.append(d if -1 <= d <= LAG_MAX_TICKS else np.nan)
        s = pd.Series(vals, index=g.tick.values).sort_index()
        s = s[~s.index.duplicated()].ffill(limit=64).rolling(33, center=True, min_periods=5).median() * TICK_MS
        out[name] = s.clip(lower=0)
    return out

def pings(d):
    try:
        x = d.ticks(["name", "m_iPing"]).to_pandas().rename(columns={"m_iPing": "ping"})
        return {n: g.set_index("tick").ping.sort_index() for n, g in x.groupby("name")}
    except Exception as e:
        print(f"(no ping: {e})"); return {}

def at(series, tick, default=None):
    if series is None or len(series) == 0: return default
    i = series.index.searchsorted(tick, side="right") - 1
    if i < 0: return default
    v = series.iloc[i]
    return default if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)

def _yaw_off(mx, my, myaw, ex, ey):
    yaw = math.degrees(math.atan2(ey - my, ex - mx))
    return (yaw - myaw + 180) % 360 - 180

def find_duels(t, me, seg, vc, lag, shots, damages, kills, eye=64):
    """Duels between me and each enemy inside one round. t: ticks with X,Y,Z,yaw,velocity,health,team_num,name."""
    from cs2coach import los_series
    fe, end, my_team = seg["fe"], seg["end"], seg["myTeam"]
    R = t[(t.tick >= fe) & (t.tick <= end)]
    u = R[R.name == me].set_index("tick").sort_index()
    if u.empty or vc is None: return []
    my_shots = shots[shots.name == me].tick.values
    out = []
    for en, g in R[(R.team_num != my_team) & (R.team_num > 1)].groupby("name"):
        g = g.set_index("tick").sort_index()
        common = g.index.intersection(u.index)
        if len(common) < 32: continue
        ok = (u.loc[common, "health"] > 0).values & (g.loc[common, "health"] > 0).values
        clear = np.zeros(len(common), bool)
        if ok.any():
            clear[ok] = los_series(vc, u.loc[common][ok], g.loc[common][ok])
        ticks = np.asarray(common)
        en_shots = shots[shots.name == en].tick.values
        i, n = 16, len(ticks)
        while i < n:
            # a line opens after at least 0.25 s of no line
            if not clear[i] or clear[max(0, i - 16):i].any():
                i += 1; continue
            t0 = int(ticks[i]); win_end = t0 + 192
            mine = my_shots[(my_shots >= t0 - 8) & (my_shots <= win_end)]
            his = en_shots[(en_shots >= t0 - 8) & (en_shots <= win_end)]
            dm_me = damages[(damages.tick >= t0) & (damages.tick <= win_end) & (damages.attacker_name == me) & (damages.victim_name == en)]
            dm_him = damages[(damages.tick >= t0) & (damages.tick <= win_end) & (damages.attacker_name == en) & (damages.victim_name == me)]
            if not len(mine) and not len(his) and dm_me.empty and dm_him.empty:
                i += 16; continue
            pre = R[(R.tick >= t0 - 16) & (R.tick <= t0)]
            v_me = float(pre[pre.name == me].velocity.mean() or 0); v_en = float(pre[pre.name == en].velocity.mean() or 0)
            if v_me > 110 and v_en < 70: peek = "you"
            elif v_en > 110 and v_me < 70: peek = "him"
            elif v_me > 110 and v_en > 110: peek = "both moving"
            else: peek = "both still"
            my_d, en_d = at(lag.get(me), t0), at(lag.get(en), t0)
            edge = None
            if my_d is not None and en_d is not None:
                half = (my_d + en_d) / 2
                edge = round(half) if peek == "you" else -round(half) if peek == "him" else 0
            appear = t0 + (max(0, -edge) / TICK_MS if edge else 0)
            # reaction
            already = bool(((my_shots >= t0 - 32) & (my_shots < t0 - 4)).any())
            first = int(mine[mine >= t0 - 8].min()) if len(mine) else None
            ux, uy, uyaw = u.loc[t0, "X"], u.loc[t0, "Y"], u.loc[t0, "yaw"]
            off0 = abs(_yaw_off(ux, uy, uyaw, g.loc[t0, "X"], g.loc[t0, "Y"]))
            flick = None
            if off0 > 3:
                prev = off0
                for tk in range(int(math.ceil(appear)), min(win_end, int(u.index.max()))):
                    if tk not in u.index or tk not in g.index: continue
                    o = abs(_yaw_off(u.loc[tk, "X"], u.loc[tk, "Y"], u.loc[tk, "yaw"], g.loc[tk, "X"], g.loc[tk, "Y"]))
                    if prev - o > 1.4:     # turning toward him faster than ~90 deg/s
                        flick = round((tk - appear) * TICK_MS); break
                    prev = o
            if already: kind, react = "already shooting", None
            elif first is None: kind, react = "no shot", None
            elif first - appear < 150 / TICK_MS: kind, react = "prefire", None
            elif (first - appear) * TICK_MS > 1000: kind, react = "late shot", None   # saw him, waited / repositioned first
            else: kind, react = "reaction", round((first - appear) * TICK_MS)
            # outcome
            k = kills[(kills.tick >= t0) & (kills.tick <= win_end + 64)]
            if ((k.attacker_name == me) & (k.victim_name == en)).any(): res = "won"
            elif ((k.attacker_name == en) & (k.victim_name == me)).any(): res = "lost"
            else:
                a, b = int(dm_me.dmg_health.sum()), int(dm_him.dmg_health.sum())
                res = "won on damage" if a > b else "lost on damage" if b > a else "even"
            out.append({"tick": t0, "enemy": en, "peek": peek, "myDelay": round(my_d) if my_d is not None else None,
                        "hisDelay": round(en_d) if en_d is not None else None, "edge": edge, "appear": int(round(appear)),
                        "kind": kind, "reaction": react, "flick": flick, "offset": round(off0, 1), "result": res,
                        "dist": round(math.hypot(ux - g.loc[t0, "X"], uy - g.loc[t0, "Y"]))})
            # skip ahead until the line has been closed for a while
            j = i + 1
            while j < n and (clear[j] or clear[max(0, j - 16):j].any()) and ticks[j] < win_end: j += 1
            i = max(j, i + 16)
    return sorted(out, key=lambda x: x["tick"])

def fight_summary(segments, me_delays=None):
    duels = [d for s in segments for d in s.get("duels", [])]
    won = lambda ds: sum(1 for d in ds if d["result"].startswith("won"))
    def wr(ds): return {"n": len(ds), "won": won(ds)}
    reacts = [d["reaction"] for d in duels if d["kind"] == "reaction" and d["reaction"] is not None]
    return {
        "duels": len(duels), "won": won(duels),
        "peek": wr([d for d in duels if d["peek"] == "you"]), "hold": wr([d for d in duels if d["peek"] == "him"]),
        "edgeFor": wr([d for d in duels if d["edge"] is not None and d["edge"] > 20]),
        "edgeAgainst": wr([d for d in duels if d["edge"] is not None and d["edge"] < -20]),
        "reactionMedian": round(statistics.median(reacts)) if reacts else None, "reactions": len(reacts),
        "prefires": sum(1 for d in duels if d["kind"] == "prefire"),
        "myDelayMedian": round(statistics.median(me_delays)) if me_delays else None,
    }
