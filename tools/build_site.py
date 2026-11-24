"""Assemble m0j's CS2 ROOM as a plain static site (used by the laptop and by GitHub Pages).

usage: python build_site.py APP_DIR OUT_DIR [--demos DIR] [--steam FILE]
  APP_DIR  a copy of this repo (the page lives in replay/index.html)
  OUT_DIR  folder to write index.html, demos.json, steam.json, radar_*.png into
  --demos  folder holding demos.json + radar_*.png (default APP_DIR/replay; the laptop uses CS2Room/data)
  --steam  Steam stats file (default APP_DIR/data/steam/latest.json)
"""
import argparse, glob, os, shutil

HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>body{margin:0}img{max-width:100%}</style></head><body>
"""
TAIL = "\n</body></html>\n"

def build(app, out, demos=None, steam=None):
    demos = demos or os.path.join(app, "replay")
    steam = steam or os.path.join(app, "data", "steam", "latest.json")
    os.makedirs(out, exist_ok=True)
    page = open(os.path.join(app, "replay", "index.html"), encoding="utf-8").read()
    # replay/index.html is written for claude.ai artifacts, which add the document skeleton; add it here.
    tmp = os.path.join(out, "index.html.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEAD + page + TAIL)
    os.replace(tmp, os.path.join(out, "index.html"))
    if os.path.exists(os.path.join(demos, "demos.json")):
        shutil.copy(os.path.join(demos, "demos.json"), out)
    for png in glob.glob(os.path.join(demos, "radar_*.png")):
        shutil.copy(png, out)
    if os.path.exists(steam):
        shutil.copy(steam, os.path.join(out, "steam.json"))
    open(os.path.join(out, ".nojekyll"), "w").close()
    print("built", out, sorted(os.listdir(out)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("app"); ap.add_argument("out"); ap.add_argument("--demos"); ap.add_argument("--steam")
    a = ap.parse_args()
    build(a.app, a.out, a.demos, a.steam)
