"""m0j's CS2 ROOM data store: one file per demo + a small summary per demo. JSON only (no awpy), so GitHub Pages can use it.

STORE/demos/<id>.json       everything the replay needs (positions, shots, kills...)
STORE/demos/<id>.meta.json  summary for the home page and match history
STORE/radar_<map>.png       radar images
"""
import json, math, os, re
try:
    import numpy as np
except ImportError:
    np = None

def clean(o):
    if isinstance(o, float): return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list): return [clean(v) for v in o]
    if np is not None:
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return clean(float(o))
        if isinstance(o, np.bool_): return bool(o)
    return o

def demo_id(dd):
    stem = re.sub(r"[^A-Za-z0-9]+", "-", os.path.splitext(dd["file"])[0]).strip("-")[:40]
    return f"{dd['date']}_{dd['time'].replace(':', '')}_{stem}"

def summarize(dd):
    """Small per-demo record for the home page and match history (the full demo loads only when opened)."""
    me = dd["me"]; k = d_ = hs = shots = hits = dmg = 0
    for sg in dd["segments"]:
        for x in sg["kills"]:
            if x.get("weapon") == "world": continue
            if x.get("att") == me and x.get("vic") != me:
                k += 1; hs += 1 if x.get("hs") else 0
            if x.get("vic") == me: d_ += 1
        shots += len(sg["shots"]); hits += sum(1 for x in sg["shots"] if x.get("hit"))
        dmg += sum(min(x["dmg"], 100) for x in sg["damage"] if x.get("att") == me and x.get("vic") != me)
    st = dd.get("stats") or {}
    line = {"k": st.get("kills", k), "d": st.get("deaths", d_), "a": st.get("assists", 0),
            "hs": round(st["headshot_pct"]) if st.get("headshot_pct") is not None else (round(hs / k * 100) if k else 0),
            "adr": round(st["adr"]) if st.get("adr") is not None else None, "kast": round(st["kast"]) if st.get("kast") is not None else None,
            "acc": round(hits / shots * 100) if shots else 0, "shots": shots, "rounds": st.get("rounds_played", 0)}
    # thumbnail: my path, at most ~300 points, plus where I got kills
    pts = []
    for sg in dd["segments"]:
        p = sg["players"].get(me)
        if not p: continue
        run = [[x, y] for x, y, h in zip(p["x"], p["y"], p["hp"]) if x is not None and h > 0]
        if run: pts.append(run)
    total = sum(len(r) for r in pts) or 1
    every = max(1, total // 300)
    path = [r[::every] for r in pts if len(r) > 1]
    kills = [[x["ax"], x["ay"]] for sg in dd["segments"] for x in sg["kills"] if x.get("att") == me and x.get("vic") != me and x.get("ax") is not None]
    return {"id": dd["id"], "label": dd["label"], "file": dd["file"], "date": dd["date"], "time": dd["time"], "map": dd["map"],
            "type": dd["type"], "category": dd.get("category"), "server": dd.get("server"), "score": dd.get("score"),
            "duration": dd.get("duration"), "me": me, "stats": dd.get("stats"), "line": line,
            "fights": dd.get("fights"), "lobbyDelay": dd.get("lobbyDelay"),
            "segs": [{"label": sg["label"], "winner": sg["winner"], "myTeam": sg["myTeam"]} for sg in dd["segments"]],
            "thumb": {"bounds": dd["bounds"], "radar": dd.get("radar"), "path": path, "kills": kills}}

def write_demo(store, dd):
    """store/demos/<id>.json (everything the replay needs) + store/demos/<id>.meta.json (the summary)."""
    os.makedirs(os.path.join(store, "demos"), exist_ok=True)
    dd = clean(dd); dd["id"] = dd.get("id") or demo_id(dd)
    with open(os.path.join(store, "demos", dd["id"] + ".json"), "w") as fh:
        json.dump(dd, fh, separators=(",", ":"), allow_nan=False)
    with open(os.path.join(store, "demos", dd["id"] + ".meta.json"), "w") as fh:
        json.dump(summarize(dd), fh, separators=(",", ":"), allow_nan=False)
    return dd["id"]

def migrate(store):
    """Old format (one store/demos.json holding everything) -> one file per demo. Keeps a .migrated copy."""
    old = os.path.join(store, "demos.json")
    if not os.path.exists(old): return
    for dd in json.load(open(old))["demos"]:
        dd.setdefault("category", "Prefire" if dd.get("type") == "practice" else "Bots" if "bot" in dd.get("label", "").lower() else "Other match")
        if dd["category"] == "Bots": dd["type"] = "practice"
        write_demo(store, dd)
    os.replace(old, old + ".migrated")


def load_summaries(store):
    d = os.path.join(store, "demos")
    if not os.path.isdir(d): return []
    out = [json.load(open(os.path.join(d, f), encoding="utf-8")) for f in os.listdir(d) if f.endswith(".meta.json")]
    return sorted(out, key=lambda m: (m.get("date", ""), m.get("time", "")))
