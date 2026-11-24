"""Aim analysis for practice demos (aim maps, bots): how m0j's clicks, flicks and tracking behave.

usage:
  python3 -I aim.py DEMO.dem [--player m0j] [--reaction 150 220] [--json OUT.json]

What it measures (see docs/aim.md for the method and its limits):
  clicks    every shot: target bot, error from the head at the exact shot angle, settle time (how long the crosshair had been
            on the head before the click), class: early (not on the head yet) / timed (< reaction low) / grey / tracked (> reaction high)
  flicks    every view movement of 8 deg or more that ends on a bot: duration, peak speed, where the peak is, corrections,
            over/undershoot of the first motion
  tracking  every stretch of 200 ms or more with the crosshair within 2.5 deg of a running bot's head: error, lag behind,
            speed match, catch-up surges
Data: exact shot angles from the server's shot events; the view angle about 256 times a second from the TrueView input history;
bot positions every tick. The head point is calibrated per session from m0j's own headshots.
"""
import sys, os, math, json, argparse
import numpy as np, pandas as pd

TICK_MS = 1000 / 64
GRID_MS = 4.0
ON_HEAD_DEG = 1.5          # "on the head" for settle time
TRACK_DEG = 2.5            # tracking window: crosshair within this of a running bot's head
RUNNING = 150              # u/s: bot counts as moving
FLICK_MIN_DEG = 8
MOVE_DEG_S = 30            # view speed that counts as a movement
EYE = 64                   # standing eye height


def wrap(a):
    return (a + 180) % 360 - 180


def count_peaks(v, frac):
    """Speed peaks (one per sub-movement): local maxima that stand out by frac of the top speed on both sides."""
    v = np.asarray(v); top = v.max(); n = 0; i = 1
    while i < len(v) - 1:
        if v[i] >= v[i - 1] and v[i] > v[i + 1]:
            l = i
            while l > 0 and v[l - 1] <= v[i]: l -= 1
            r = i
            while r < len(v) - 1 and v[r + 1] <= v[i]: r += 1
            if v[i] - max(v[l:i + 1].min(), v[i:r + 1].min()) >= frac * top or (l == 0 and r == len(v) - 1): n += 1
        i += 1
    return max(n, 1)


def first_dip(v, frac):
    """Index of the first speed low after the main peak that is followed by a rise of frac of the peak (end of the first motion)."""
    v = np.asarray(v); top = v.max()
    for i in range(1, len(v) - 1):
        if v[i] <= v[i - 1] and v[i] < v[i + 1] and (v[i + 1:].max() - v[i]) >= frac * top: return i
    return len(v) - 1


def view_series(path, me):
    """Sub-tick view angles from the TrueView input history: DataFrame(pt, pitch, yaw, tick), yaw unwrapped."""
    from demoparser2 import DemoParser
    t = DemoParser(path).parse_ticks(["usercmd_input_history"])
    t = t[t.name == me]
    rows = []
    for tk, h in zip(t.tick, t.usercmd_input_history):
        if h is None: continue
        for e in h:
            rows.append((e["player_tick_count"] + e["player_tick_fraction"], e["x"], e["y"], tk))
    A = pd.DataFrame(rows, columns=["pt", "pitch", "yaw", "tick"]).drop_duplicates("pt").sort_values("pt").reset_index(drop=True)
    A["yaw"] = np.degrees(np.unwrap(np.radians(A.yaw)))
    return A


def align(A, shots):
    """Map input-history time to demo ticks: pick the shift where the history angle matches the server's shot angles."""
    base = np.floor((A.pt - A.tick).median())
    tt = A.pt.values - base
    best = None
    for k in np.arange(-4, 4.001, 0.125):
        est = np.interp(shots.tick.values + k, tt, A.yaw.values)
        err = np.median(np.abs(wrap(est - shots.yaw.values)))
        if best is None or err < best[1]: best = (k, err)
    return tt - best[0], float(best[0]), float(best[1])


class Bots:
    """Bot head directions from m0j's eye at any (fractional) demo tick."""

    def __init__(self, t, me, head_z):
        self.me = t[t.name == me].set_index("tick").sort_index()
        self.idx = self.me.index.values
        self.head_z = head_z
        self.b = {}
        for n, g in t[t.name != me].groupby("name"):
            g = g.set_index("tick").sort_index().reindex(self.idx)
            self.b[n] = g

    def at(self, name, tk, frac=False):
        """(yaw, pitch, dist, speed, alive) of a bot's head at demo tick tk (interpolated when frac)."""
        g = self.b[name]
        if frac:
            i = np.searchsorted(self.idx, tk) - 1
            if i < 0 or i + 1 >= len(self.idx): return None
            a = (tk - self.idx[i]) / max(self.idx[i + 1] - self.idx[i], 1)
            r0, r1 = g.iloc[i], g.iloc[i + 1]; m0, m1 = self.me.iloc[i], self.me.iloc[i + 1]
            bx, by, bz = [(1 - a) * r0[c] + a * r1[c] for c in ("X", "Y", "Z")]
            mx, my, mz = [(1 - a) * m0[c] + a * m1[c] for c in ("X", "Y", "Z")]
            hp, sp = r0.health, r0.velocity
        else:
            if tk not in g.index: return None
            r = g.loc[tk]; m = self.me.loc[tk]
            bx, by, bz, mx, my, mz, hp, sp = r.X, r.Y, r.Z, m.X, m.Y, m.Z, r.health, r.velocity
        if bx != bx or mx != mx: return None
        dx, dy, dz = bx - mx, by - my, (bz + self.head_z) - (mz + EYE)
        dist = math.hypot(dx, dy)
        return (math.degrees(math.atan2(dy, dx)), -math.degrees(math.atan2(dz, dist)), dist, sp, hp > 0)

    def nearest(self, tk, yaw, pitch, alive_tick=None):
        best = None
        for n in self.b:
            a = self.at(n, tk)
            if a is None: continue
            al = self.at(n, alive_tick) if alive_tick is not None else a
            if al is None or not al[4]: continue
            e = math.hypot(wrap(yaw - a[0]), pitch - a[1])
            if best is None or e < best[1]: best = (n, e, a)
        return best


def calibrate_head(t, me, shots, dm):
    """Head point height (units above the bot's origin) that centres m0j's headshot hits vertically."""
    H = dm[(dm.attacker_name == me) & (dm.hitgroup_name == "head")].groupby("tick").victim_name.first()
    S = shots[shots.tick.isin(H.index)]
    if len(S) < 5: return 66.0, 0
    M = t[t.name == me].set_index("tick")
    V = {n: g.set_index("tick") for n, g in t[t.name != me].groupby("name")}
    best = None
    for hz in np.arange(56, 72.01, 0.5):
        errs = []
        for r in S.itertuples():
            n = H.loc[r.tick]
            if r.tick not in V[n].index or r.tick not in M.index: continue
            b, m = V[n].loc[r.tick], M.loc[r.tick]
            dist = math.hypot(b.X - m.X, b.Y - m.Y)
            errs.append(r.pitch + math.degrees(math.atan2((b.Z + hz) - (m.Z + EYE), dist)))
        if errs:
            e = abs(np.median(errs))
            if best is None or e < best[1]: best = (float(hz), e)
    return best[0], len(S)


def analyze(path, me=None, reaction=(150, 220)):
    from awpy import Demo
    d = Demo(path)
    t = d.ticks(["name", "X", "Y", "Z", "health", "velocity"]).to_pandas()
    shots = d.shots.to_pandas(); dm = d.damages.to_pandas(); kl = d.kills.to_pandas()
    header = d.header if isinstance(d.header, dict) else {}
    if me is None:
        p = d.players.to_pandas(); hum = p[p.steamid.astype(str).str.len() > 5]
        me = "m0j" if "m0j" in set(t.name) else (hum.name.iloc[0] if len(hum) else t.name.value_counts().index[0])
    S = shots[(shots.name == me) & ~shots.weapon.str.contains("knife|grenade|flash|smoke|molotov|decoy|c4", na=False)].sort_values("tick").reset_index(drop=True)
    if len(S) < 10: return None
    head_z, n_cal = calibrate_head(t, me, S, dm)
    bots = Bots(t, me, head_z)
    A = view_series(path, me)
    if len(A) < 100: return None
    tt, shift, align_err = align(A, S)
    g = np.arange(tt[0], tt[-1], GRID_MS / TICK_MS)            # demo-tick time grid, 4 ms apart
    ys = np.interp(g, tt, A.yaw.values); ps = np.interp(g, tt, A.pitch.values)
    k3 = np.ones(3) / 3
    yss, pss = np.convolve(ys, k3, "same"), np.convolve(ps, k3, "same")
    sp = np.hypot(np.gradient(yss, GRID_MS / 1000), np.gradient(pss, GRID_MS / 1000))
    hits = dm[dm.attacker_name == me].groupby("tick").agg(v=("victim_name", "first"), hg=("hitgroup_name", "first"))
    lo, hi = reaction

    # ---- clicks
    clicks = []
    prev = None
    for r in S.itertuples():
        tk = int(r.tick); gap = None if prev is None else (tk - prev) * TICK_MS / 1000; prev = tk
        nb = bots.nearest(tk, r.yaw, r.pitch, alive_tick=tk - 1)
        row = dict(tick=tk, gap=gap, hit=tk in hits.index, hg=hits.hg.get(tk) if tk in hits.index else None)
        if nb and nb[1] < 8:
            n, err, a = nb
            a1 = bots.at(n, tk - 1)                                            # speed before the shot (a killed bot reads 0)
            if a1 is not None: a = a[:3] + (a1[3],) + a[4:]
            a0 = bots.at(n, tk - 4)
            w = wrap(a[0] - a0[0]) * 16 if a0 else 0.0                     # target's sideways speed on screen, deg/s
            yerr = wrap(r.yaw - a[0])
            settle = 0.0
            j = int(np.searchsorted(g, tk)) - 1
            while j > 0 and settle < 2000:
                b = bots.at(n, g[j], frac=True)
                if b is None or not b[4] or math.hypot(wrap(ys[j] - b[0]), ps[j] - b[1]) > ON_HEAD_DEG: break
                settle += GRID_MS; j -= 1
            cls = "early" if settle < 16 else "timed" if settle < lo else "grey" if settle <= hi else "tracked"
            row.update(target=n, err=round(err, 2), yawErr=round(yerr, 2), pitchErr=round(r.pitch - a[1], 2),
                       lead=round(yerr * (1 if w >= 0 else -1), 2), dist=int(a[2]), tSpeed=int(a[3]) if a[3] == a[3] else None,
                       tAng=round(abs(w), 1), settle=round(settle), cls=cls, spray=gap is not None and gap <= 0.12)
        clicks.append(row)
    C = pd.DataFrame(clicks)

    # ---- flicks
    segs, on = [], False
    for j in range(len(sp)):
        if not on and sp[j] > MOVE_DEG_S: on, s0 = True, j
        elif on and sp[j] < MOVE_DEG_S:
            if (sp[j:j + 10] > MOVE_DEG_S).any(): continue        # brief dip under 40 ms: same movement
            on = False; segs.append((s0, j))
    shot_ticks = S.tick.values
    flicks = []
    for s0, e in segs:
        amp = math.hypot(wrap(yss[e] - yss[s0]), pss[e] - pss[s0])
        if amp < FLICK_MIN_DEG: continue
        seg = sp[s0:e + 1]; pk = int(np.argmax(seg))
        peaks = count_peaks(seg, 0.15)
        pe = s0 + pk + first_dip(seg[pk:], 0.1)
        nb = bots.nearest(int(round(g[e])), yss[e], pss[e])
        if not nb or nb[1] > 6: continue
        b_pe = bots.at(nb[0], g[pe], frac=True)
        if b_pe is None: continue
        dv = np.array([wrap(yss[e] - yss[s0]), pss[e] - pss[s0]]); dv /= np.linalg.norm(dv)
        ev = np.array([wrap(yss[pe] - b_pe[0]), pss[pe] - b_pe[1]])
        nxt = shot_ticks[shot_ticks >= g[s0]]
        flicks.append(dict(amp=round(amp, 1), dur=round((e - s0) * GRID_MS), peak=round(float(seg.max())), tPeak=round(pk / len(seg), 2),
                           corrections=int(peaks - 1), primaryErr=round(float(ev @ dv), 2),
                           shotAfter=round((nxt[0] - g[e]) * TICK_MS) if len(nxt) else None))
    F = pd.DataFrame(flicks)

    # ---- tracking
    windows = []
    for n in bots.b:
        hb = np.full(len(g), np.nan); hp = np.full(len(g), np.nan); run = np.zeros(len(g), bool)
        gi = bots.b[n]; idx = bots.idx
        m = bots.me
        dx, dy = gi.X.values - m.X.values, gi.Y.values - m.Y.values
        dz = (gi.Z.values + head_z) - (m.Z.values + EYE)
        by = np.degrees(np.unwrap(np.radians(np.nan_to_num(np.degrees(np.arctan2(dy, dx))))))
        bp = -np.degrees(np.arctan2(dz, np.hypot(dx, dy)))
        ok = (np.nan_to_num(gi.health.values) > 0) & (np.nan_to_num(gi.velocity.values) > RUNNING)
        hb = np.interp(g, idx, by); hp = np.interp(g, idx, np.nan_to_num(bp)); run = np.interp(g, idx, ok.astype(float)) > 0.99
        e = np.hypot(wrap(ys - hb), ps - hp); inside = (e < TRACK_DEG) & run
        i = 0
        while i < len(inside):
            if not inside[i]: i += 1; continue
            j = i
            while j < len(inside) and inside[j]: j += 1
            if (j - i) * GRID_MS >= 200:
                sl = slice(i, j)
                vt = np.gradient(hb[sl], GRID_MS / 1000); vc = np.convolve(np.gradient(ys[sl], GRID_MS / 1000), k3, "same")
                rel = vc - vt
                dirn = 1 if np.median(vt) >= 0 else -1
                windows.append(dict(ms=(j - i) * GRID_MS, err=float(np.mean(e[sl])), lead=float(np.mean(wrap(ys[sl] - hb[sl]) * dirn)),
                                    tSpeed=float(np.median(np.abs(vt))), ratio=float(np.median(np.abs(vc)) / max(np.median(np.abs(vt)), 1)),
                                    surges=float(np.mean(np.abs(vc) > 2 * np.abs(vt) + 5)),
                                    corrPerS=float(np.sum(np.diff(np.sign(rel[np.abs(rel) > 2])) != 0) / ((j - i) * GRID_MS / 1000))))
            i = j
    W = pd.DataFrame(windows)

    # ---- summary
    km = kl[(kl.attacker_name == me) & (kl.victim_name != me)]
    dur = float(header.get("playback_time") or 0) or (S.tick.max() - S.tick.min()) / 64
    alltaps = C[C.get("cls").notna() & ~C.spray.fillna(False).astype(bool)] if "cls" in C else C.iloc[0:0]
    moving = alltaps[alltaps.tSpeed.fillna(0) > 100]; still = alltaps[alltaps.tSpeed.fillna(0) <= 100]
    def share(x): return None if len(x) == 0 else round(float(x.mean()) * 100)
    def med(x): return None if len(x) == 0 else round(float(np.median(x)), 2)
    def classes_of(tp):
        out = {}
        for c in ("early", "timed", "grey", "tracked"):
            x = tp[tp.cls == c]
            out[c] = dict(n=int(len(x)), hit=share(x.hit), err=med(x.err) if len(x) else None)
        return out
    # the headline uses running bots when there are enough of them (moving-target drills), else standing bots
    targets = "moving" if len(moving) >= 20 or len(moving) >= len(still) else "still"
    taps = moving if targets == "moving" else still
    classes = classes_of(taps)
    fl = {}
    if len(F):
        F["over"] = F.primaryErr > 1; F["under"] = F.primaryErr < -1
        for lab, a, b in (("8-15", 8, 15), ("15-30", 15, 30), ("30-60", 30, 60), ("60+", 60, 999)):
            x = F[(F.amp >= a) & (F.amp < b)]
            fl[lab] = dict(n=int(len(x)), peak=med(x.peak), dur=med(x.dur), tPeak=med(x.tPeak), corr=share(x.corrections > 0),
                           over=share(x.over), under=share(x.under), errAbs=med(x.primaryErr.abs()))
    tw = W.ms / W.ms.sum() if len(W) else None
    out = dict(
        version=2, player=me, map=header.get("map_name"), reaction=[lo, hi],
        calibration=dict(headZ=head_z, fromHeadshots=n_cal, alignShiftTicks=shift, alignErrDeg=round(align_err, 3),
                         samplesPerSec=round(len(A) / max(dur, 1))),
        session=dict(minutes=round(dur / 60, 1), kills=int(len(km)), hsKills=int(km.headshot.sum()), shots=int(len(S)),
                     hits=int(C.hit.sum()), hitPct=share(C.hit), killsPerMin=round(len(km) / max(dur / 60, 0.1), 1),
                     shotsPerKill=round(len(S) / max(len(km), 1), 2),
                     weapons=S.weapon.str.replace("weapon_", "").value_counts().to_dict(),
                     sprayHitPct=share(C[C.spray.fillna(False).astype(bool)].hit) if "spray" in C else None),
        clicks=dict(targets=targets, movingTaps=int(len(moving)), stillTaps=int(len(still)), classes=classes,
                    other=classes_of(still if targets == "moving" else moving), earlyShare=share(taps.cls == "early") if len(taps) else None,
                    settleMedian=med(taps[taps.settle >= 16].settle) if len(taps) else None),
        flicks=dict(n=int(len(F)), medianDur=med(F.dur) if len(F) else None, tPeak=med(F.tPeak) if len(F) else None,
                    corr=share(F.corrections > 0) if len(F) else None, errPctOfAmp=med((F.primaryErr.abs() / F.amp) * 100) if len(F) else None,
                    over=share(F.over) if len(F) else None, under=share(F.under) if len(F) else None,
                    speedExp=round(float(np.polyfit(np.log(F.amp), np.log(F.peak.clip(lower=1)), 1)[0]), 2) if len(F) > 5 else None,
                    byAmp=fl),
        tracking=dict(windows=int(len(W)), seconds=round(float(W.ms.sum()) / 1000, 1) if len(W) else 0,
                      err=round(float((W.err * tw).sum()), 2) if len(W) else None, lead=round(float((W.lead * tw).sum()), 2) if len(W) else None,
                      ratio=med(W.ratio) if len(W) else None, surges=round(float((W.surges * tw).sum()) * 100) if len(W) else None,
                      corrPerS=med(W.corrPerS) if len(W) else None),
        perShot={str(int(r.tick)): dict(settle=r.settle, cls=r.cls, err=r.err) for r in C.itertuples() if getattr(r, "cls", None) == getattr(r, "cls", None) and isinstance(getattr(r, "cls", None), str)},
    )
    return out


def report(a):
    s, c, f, tr = a["session"], a["clicks"], a["flicks"], a["tracking"]
    print(f"{a['map']} | {s['minutes']} min | {s['kills']} kills ({s['hsKills']} HS) | {s['shots']} shots, {s['hitPct']}% hit | "
          f"{s['killsPerMin']} kills/min | {s['shotsPerKill']} shots/kill | weapons {s['weapons']}")
    cal = a["calibration"]
    print(f"calibration: head point Z+{cal['headZ']} from {cal['fromHeadshots']} headshots, view samples {cal['samplesPerSec']}/s, "
          f"time shift {cal['alignShiftTicks']} ticks (match {cal['alignErrDeg']} deg)")
    lo, hi = a["reaction"]
    tg = c.get("targets", "moving")
    print(f"taps on {tg} bots: {c['movingTaps'] if tg == 'moving' else c['stillTaps']}  (click vs crosshair arriving on the head; reaction {lo}-{hi} ms)")
    names = {"early": "before arriving", "timed": f"timed (<{lo} ms)", "grey": f"{lo}-{hi} ms", "tracked": f"tracked (>{hi} ms)"}
    for k, v in c["classes"].items():
        print(f"  {names[k]:<18} n={v['n']:<4} hit {v['hit']}%  median err {v['err']} deg")
    print(f"flicks: {f['n']} | median {f['medianDur']} ms | peak at {f['tPeak']} of the move | corrections {f['corr']}% | "
          f"first-motion error {f['errPctOfAmp']}% of distance | over {f['over']}% under {f['under']}% | peak speed ~ amp^{f['speedExp']}")
    for k, v in f["byAmp"].items():
        print(f"  {k:>6} deg n={v['n']:<4} peak {v['peak']} deg/s  dur {v['dur']} ms  corr {v['corr']}%  over {v['over']}%  under {v['under']}%")
    print(f"tracking: {tr['seconds']} s in {tr['windows']} windows | error {tr['err']} deg | lead {tr['lead']} deg (+ ahead) | "
          f"speed x{tr['ratio']} | surges {tr['surges']}% of the time | {tr['corrPerS']} corrections/s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("demo"); ap.add_argument("--player"); ap.add_argument("--reaction", nargs=2, type=int, default=[150, 220])
    ap.add_argument("--json")
    A = ap.parse_args()
    a = analyze(A.demo, A.player, tuple(A.reaction))
    if a is None: sys.exit("not enough shots / view data for an aim analysis")
    report(a)
    if A.json:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from store import clean
        json.dump(clean(a), open(A.json, "w"), indent=1)
