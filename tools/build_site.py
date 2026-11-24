"""Assemble m0j's CS2 ROOM as a plain static site (used by the laptop and by GitHub Pages).

usage: python build_site.py APP_DIR OUT_DIR
  APP_DIR = a copy of this repo (needs replay/ and optionally data/steam/latest.json)
  OUT_DIR = folder to write index.html, demos.json, steam.json, radar_*.png into
"""
import sys, shutil, glob, os

HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>body{margin:0}img{max-width:100%}</style></head><body>
"""
TAIL = "\n</body></html>\n"

def build(app, out):
    os.makedirs(out, exist_ok=True)
    page = open(os.path.join(app, "replay", "index.html"), encoding="utf-8").read()
    # replay/index.html is written for claude.ai artifacts, which add the document skeleton; add it here.
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEAD + page + TAIL)
    shutil.copy(os.path.join(app, "replay", "demos.json"), out)
    for png in glob.glob(os.path.join(app, "replay", "radar_*.png")):
        shutil.copy(png, out)
    steam = os.path.join(app, "data", "steam", "latest.json")
    if os.path.exists(steam):
        shutil.copy(steam, os.path.join(out, "steam.json"))
    open(os.path.join(out, ".nojekyll"), "w").close()
    print("built", out, sorted(os.listdir(out)))

if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
