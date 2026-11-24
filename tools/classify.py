"""Decide what kind of demo this is, from what the demo itself says.

kind:     "match" | "practice"
category: match    -> "Premier / Competitive", "Wingman", "FACEIT", "Other match"
          practice -> "Prefire", "Aim training", "Movement", "Refrag", "Bots", "Other practice"

Rules, first hit wins:
  1. overrides (laptop config\\categories.json or --category): {"<demo file name>": "Prefire", ...}
  2. Valve matchmaking server name        -> match (Wingman if 2v2 / max 16 rounds)
  3. FACEIT server name                    -> match FACEIT
  4. Refrag server name                    -> practice Refrag
  5. workshop addon id in KNOWN_ADDONS     -> that practice category
  6. map name prefix (aim_, surf_, kz_, bhop_, prefire...) -> practice category
  7. bots on a local / listen server       -> practice Bots
  8. rounds + 6 or more real players       -> match Other match
  9. anything else                         -> practice Other practice
"""
import json, os, re

# Workshop maps we've seen; add more as m0j uses them.
KNOWN_ADDONS = {
    "3244203953": "Prefire",      # Dust2 prefire map (m0j's yurp.dem, Nov 2026)
}
MAP_RULES = [
    (r"prefire|pf_", "Prefire"),
    (r"^aim_|aim_botz|aimbotz|training_aim|^fast_aim|yprac.*aim", "Aim training"),
    (r"^surf_|^kz_|^bhop_|^mg_bhop|movement|^xc_", "Movement"),
    (r"yprac|prac_|practice", "Prefire"),
]
MATCH_CATS = ["Premier / Competitive", "Wingman", "FACEIT", "Other match"]
PRACTICE_CATS = ["Prefire", "Aim training", "Movement", "Refrag", "Bots", "Other practice"]

def kind_of(category):
    return "match" if category in MATCH_CATS else "practice"

def classify(header, file_name, humans, bots, rounds_played, max_rounds=None, addons="", overrides=None):
    server = (header.get("server_name") or "").lower()
    mapn = (header.get("map_name") or "").lower()
    if overrides and file_name in overrides:
        cat = overrides[file_name]
        return kind_of(cat), cat
    if server.startswith("valve counter-strike") or "valve" in server and "server" in server:
        if (max_rounds and max_rounds <= 16) or (humans and humans <= 4):
            return "match", "Wingman"
        return "match", "Premier / Competitive"
    if "faceit" in server:
        return "match", "FACEIT"
    if "refrag" in server:
        return "practice", "Refrag"
    for a in re.split(r"[,\s]+", str(addons or "")):
        if a in KNOWN_ADDONS:
            return "practice", KNOWN_ADDONS[a]
    for pat, cat in MAP_RULES:
        if re.search(pat, mapn):
            return "practice", cat
    if bots and bots >= humans:
        return "practice", "Bots"
    if rounds_played and humans >= 6:
        return "match", "Other match"
    return "practice", "Other practice"

def load_overrides(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
