"""Assemble m0j's CS2 ROOM as a plain static site (used by the laptop and by GitHub Pages).

usage: python build_site.py APP_DIR OUT_DIR [--demos STORE] [--steam FILE]
  APP_DIR  a copy of this repo (the page lives in replay/index.html)
  OUT_DIR  site folder: index.html, matches.json, demo/<id>.json, steam.json, radar_*.png
  --demos  data store (see tools/store.py; default APP_DIR/replay; the laptop uses CS2Room/data)
  --steam  Steam stats file (default APP_DIR/data/steam/latest.json)
"""
import argparse, glob, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from store import load_summaries, migrate

HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>body{margin:0}img{max-width:100%}</style></head><body>
"""
TAIL = "\n</body></html>\n"

def build(app, out, store=None, steam=None):
    store = store or os.path.join(app, "replay")
    steam = steam or os.path.join(app, "data", "steam", "latest.json")
    migrate(store)                                   # old single demos.json -> per-demo files (no-op afterwards)
    os.makedirs(os.path.join(out, "demo"), exist_ok=True)
    page = open(os.path.join(app, "replay", "index.html"), encoding="utf-8").read()
    # replay/index.html is written for claude.ai artifacts, which add the document skeleton; add it here.
    tmp = os.path.join(out, "index.html.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEAD + page + TAIL)
    os.replace(tmp, os.path.join(out, "index.html"))

    summaries = load_summaries(store)
    keep = set()
    for m in summaries:
        src = os.path.join(store, "demos", m["id"] + ".json")
        dst = os.path.join(out, "demo", m["id"] + ".json")
        keep.add(m["id"] + ".json")
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            shutil.copy(src, dst)
    for f in os.listdir(os.path.join(out, "demo")):  # drop demos removed from the store
        if f not in keep: os.remove(os.path.join(out, "demo", f))
    tmp = os.path.join(out, "matches.json.tmp")
    json.dump({"matches": summaries}, open(tmp, "w"), separators=(",", ":"))
    os.replace(tmp, os.path.join(out, "matches.json"))
    for png in glob.glob(os.path.join(store, "radar_*.png")):
        shutil.copy(png, out)
    if os.path.exists(steam):
        st = json.load(open(steam, encoding="utf-8"))
        st.pop("steamid", None)                      # the site can be reached from outside: keep the account ID off it
        json.dump(st, open(os.path.join(out, "steam.json"), "w"), separators=(",", ":"))
    # friends (laptop: data/steam/players/<steamid>.json from config/players.json): name + public stats, no Steam IDs on the site
    pdir = os.path.join(os.path.dirname(steam), "players")
    players = []
    os.makedirs(os.path.join(out, "players"), exist_ok=True)
    try: order = json.load(open(os.path.join(pdir, "_order.json")))["order"]
    except Exception: order = []
    import hashlib, re
    for sid in order:
        try: p = json.load(open(os.path.join(pdir, sid + ".json"), encoding="utf-8"))
        except Exception: continue
        slug = (re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-") or "player") + "-" + hashlib.sha1(sid.encode()).hexdigest()[:5]
        p.pop("steamid", None)
        json.dump(p, open(os.path.join(out, "players", slug + ".json"), "w"), separators=(",", ":"))
        players.append({"slug": slug, "name": p["name"], "avatar": p.get("avatar"), "hasStats": bool(p.get("stats"))})
    json.dump({"players": players}, open(os.path.join(out, "players.json"), "w"), separators=(",", ":"))
    old = os.path.join(out, "demos.json")
    if os.path.exists(old): os.remove(old)
    open(os.path.join(out, ".nojekyll"), "w").close()
    print("built", out, f"{len(summaries)} demos")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("app"); ap.add_argument("out"); ap.add_argument("--demos"); ap.add_argument("--steam")
    a = ap.parse_args()
    build(a.app, a.out, a.demos, a.steam)
