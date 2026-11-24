"""CS2Room laptop pipeline: Steam stats, new-match check + demo download, demo processing, site build, match-over listener.

usage (from CS2Room\\.venv\\Scripts\\python.exe):
  cs2room.py run        steam stats + check for new Valve matches + process inbox + rebuild site (the 30-min backup task)
  cs2room.py steam      only refresh Steam lifetime stats
  cs2room.py check      only look for new matches and download their demos into demos\\inbox
  cs2room.py process    only parse demos in demos\\inbox, add them to match history, archive them
  cs2room.py build      only rebuild site\\
  cs2room.py reprocess  run every archived demo through the current tools again (after updates)
  cs2room.py serve      web server for site\\ on port 8080, with the "Check for new matches" button (POST /api/check)
                        and "Sign in through Steam" (/auth/steam): through the tunnel only signed-in, allowed players can check
  cs2room.py listen     match-over listener for CS2 Game State Integration (port 3000); runs the pipeline after a match ends
  cs2room.py tunnel     Cloudflare quick tunnel to the site; posts its address to the repo (data/tunnel.json) for the launcher

Folder layout: see laptop/README.md. Private settings come from config\\secrets.dpapi (Windows-encrypted)
or config\\secrets.local.json (plain, before setup.ps1 encrypts it). Nothing here prints or uploads them.
"""
import bz2, datetime, json, os, subprocess, sys, threading, time, urllib.parse, urllib.request, zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # CS2Room\app
ROOT = os.path.dirname(APP)                                            # CS2Room
CONFIG, LOGS = os.path.join(ROOT, "config"), os.path.join(ROOT, "logs")
DATA, SITE = os.path.join(ROOT, "data"), os.path.join(ROOT, "site")
INBOX, ARCHIVE = os.path.join(ROOT, "demos", "inbox"), os.path.join(ROOT, "demos", "archive")
STATE = os.path.join(CONFIG, "state.json")
LOCK = os.path.join(CONFIG, "run.lock")
PY = sys.executable
GSI_PORT = 3000
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}   # don't flash console windows from background tasks

def log(msg):
    os.makedirs(LOGS, exist_ok=True)
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with open(os.path.join(LOGS, "cs2room.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")

# ---------- secrets ----------
def _dpapi_decrypt(blob):
    import ctypes
    from ctypes import wintypes
    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(blob, len(blob))
    inp, out = BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise RuntimeError("could not decrypt config\\secrets.dpapi (different Windows user?)")
    data = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return data

def secrets():
    enc = os.path.join(CONFIG, "secrets.dpapi")
    if os.path.exists(enc) and os.name == "nt":
        # written by PowerShell ConvertFrom-SecureString: hex of a DPAPI blob holding UTF-16LE text
        return json.loads(_dpapi_decrypt(bytes.fromhex(open(enc).read().strip())).decode("utf-16-le"))
    return json.load(open(os.path.join(CONFIG, "secrets.local.json"), encoding="utf-8"))

def load_state():
    try: return json.load(open(STATE, encoding="utf-8"))
    except Exception: return {}

def save_state(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), indent=1)

# ---------- one run at a time ----------
class RunLock:
    def __enter__(self):
        if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 1800:
            raise RuntimeError("another run is in progress")
        open(LOCK, "w").write(str(os.getpid())); return self
    def __exit__(self, *a):
        try: os.remove(LOCK)
        except OSError: pass

def get_json(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "cs2room"}), timeout=timeout) as r:
        return r.status, json.loads(r.read().decode() or "{}")

# ---------- Steam lifetime stats ----------
def steam_stats():
    s = secrets(); key, sid = s["steam_web_api_key"], s["steam_id64"]
    _, raw = get_json(f"https://api.steampowered.com/ISteamUserStats/GetUserStatsForGame/v2/?appid=730&steamid={sid}&key={key}")
    raw = raw.get("playerstats", {})
    if not raw.get("stats"): raise RuntimeError("Steam returned no stats (Game details private?)")
    try:
        _, owned = get_json(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?steamid={sid}&include_played_free_games=1&appids_filter%5B0%5D=730&key={key}")
        cs = next((g for g in owned.get("response", {}).get("games", []) if g.get("appid") == 730), {})
    except Exception:
        cs = {}
    now = datetime.datetime.now(datetime.timezone.utc)
    out = {"fetched_at": now.isoformat(timespec="seconds"), "steamid": raw.get("steamID"),
           "playtime_minutes": cs.get("playtime_forever"), "playtime_2weeks_minutes": cs.get("playtime_2weeks"),
           "achievements_unlocked": len(raw.get("achievements", [])),
           "stats": {x["name"]: x["value"] for x in raw["stats"]}}
    d = os.path.join(DATA, "steam", "history"); os.makedirs(d, exist_ok=True)
    text = json.dumps(out, indent=1, sort_keys=True)
    open(os.path.join(DATA, "steam", "latest.json"), "w").write(text)
    open(os.path.join(d, f"{now:%Y-%m-%d}.json"), "w").write(text)
    log(f"steam stats updated ({len(out['stats'])} counters)")

# ---------- friends on the CS2 ROOM hub: their Steam name + whatever CS2 stats they make public ----------
PLAYERS_CFG = os.path.join(CONFIG, "players.json")   # {"friends": ["https://steamcommunity.com/id/...", ...]} (not in the repo)

def friend_stats():
    try: urls = json.load(open(PLAYERS_CFG, encoding="utf-8")).get("friends", [])
    except FileNotFoundError: return
    import re
    key = secrets()["steam_web_api_key"]
    d = os.path.join(DATA, "steam", "players"); os.makedirs(d, exist_ok=True)
    order = []
    for u in urls:
        try:
            m = re.search(r"/profiles/(\d{17})", u) or re.search(r"/id/([^/?#]+)", u)
            if not m: log(f"friends: can't read {u}"); continue
            sid = m.group(1)
            if not sid.isdigit():
                _, r = get_json("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?" + urllib.parse.urlencode({"key": key, "vanityurl": sid}))
                sid = r.get("response", {}).get("steamid")
                if not sid: log(f"friends: no Steam account at {u}"); continue
            _, r = get_json(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={key}&steamids={sid}")
            pl = (r.get("response", {}).get("players") or [{}])[0]
            out = {"steamid": sid, "name": pl.get("personaname") or "Player", "avatar": pl.get("avatarfull"),
                   "profile_public": pl.get("communityvisibilitystate") == 3,
                   "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "stats": None}
            try:
                _, raw = get_json(f"https://api.steampowered.com/ISteamUserStats/GetUserStatsForGame/v2/?appid=730&steamid={sid}&key={key}")
                st = raw.get("playerstats", {}).get("stats")
                if st: out["stats"] = {x["name"]: x["value"] for x in st}
            except Exception: pass                                     # game details private
            try:
                _, owned = get_json(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?steamid={sid}&include_played_free_games=1&appids_filter%5B0%5D=730&key={key}")
                cs = next((g for g in owned.get("response", {}).get("games", []) if g.get("appid") == 730), {})
                out["playtime_minutes"], out["playtime_2weeks_minutes"] = cs.get("playtime_forever"), cs.get("playtime_2weeks")
            except Exception: pass
            json.dump(out, open(os.path.join(d, sid + ".json"), "w", encoding="utf-8"), indent=1)
            order.append(sid)
        except Exception as e:
            log(f"friends: {u}: {e}")
    json.dump({"order": order}, open(os.path.join(d, "_order.json"), "w"))
    log(f"friends: {len(order)} player(s) updated")

# ---------- new Valve matches (Premier / Competitive / Wingman) ----------
def new_share_codes():
    s, st = secrets(), load_state()
    known = st.get("last_share_code") or s["oldest_share_code"]
    codes = [] if st.get("last_share_code") else [known]        # first run: also fetch the match the token points at
    while True:
        q = urllib.parse.urlencode({"key": s["steam_web_api_key"], "steamid": s["steam_id64"],
                                    "steamidkey": s["match_history_auth_code"], "knowncode": known})
        status, res = get_json("https://api.steampowered.com/ICSGOPlayers_730/GetNextMatchSharingCode/v1?" + q)
        nxt = res.get("result", {}).get("nextcode")
        if status == 202 or not nxt or nxt == "n/a": break       # 202 = no newer match yet
        codes.append(nxt); known = nxt
    return codes, known

def check_matches():
    codes, newest = new_share_codes()
    st = load_state()
    if not codes:
        log("no new matches"); return 0
    s = secrets()
    node = subprocess.run(["node", os.path.join(APP, "laptop", "fetch_demo.js")], cwd=os.path.join(APP, "laptop"),
                          input=json.dumps({"username": s["bot_steam_username"], "password": s["bot_steam_password"], "codes": codes}),
                          capture_output=True, text=True, timeout=180, **NO_WINDOW)
    try: res = json.loads(node.stdout)
    except Exception: raise RuntimeError("demo bot gave no answer: " + (node.stderr or "")[-300:])
    if res.get("error"):
        log("demo bot: " + res["error"])
        if not any(r.get("url") for r in res.get("results", [])): raise RuntimeError(res["error"])
    got = 0
    os.makedirs(INBOX, exist_ok=True)
    for r in res.get("results", []):
        if not r.get("url"):
            log(f"no demo link for {r['code']} ({r.get('error') or 'not ready yet'})"); continue
        name = f"mm_{r.get('matchid') or r['code'][-5:]}.dem"
        dest = os.path.join(INBOX, name)
        if not os.path.exists(dest):
            log(f"downloading {r['url']}")
            with urllib.request.urlopen(r["url"], timeout=300) as resp:
                data = resp.read()
            open(dest, "wb").write(bz2.decompress(data) if r["url"].endswith(".bz2") else data)
            when = datetime.datetime.fromtimestamp(r["matchtime"]) if r.get("matchtime") else datetime.datetime.now()
            json.dump({"source": "valve", "share_code": r["code"], "when": when.strftime("%Y-%m-%d %H:%M"), "label": "Matchmaking"},
                      open(dest + ".json", "w"))
        got += 1
    # only move past codes whose demo we have (or that are too old to ever have one)
    done = [r["code"] for r in res.get("results", []) if r.get("url") or "not found" in (r.get("error") or "")]
    if codes and set(codes) <= set(done):
        st["last_share_code"] = newest; save_state(st)
    log(f"{got} new demo(s) downloaded")
    return got

# ---------- process inbox ----------
def process_inbox():
    os.makedirs(INBOX, exist_ok=True)
    demos = sorted(f for f in os.listdir(INBOX) if f.endswith(".dem"))
    if not demos: return 0
    store = DATA
    for f in demos:
        path = os.path.join(INBOX, f)
        meta = {}
        try: meta = json.load(open(path + ".json"))
        except Exception: pass
        when = meta.get("when") or datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        label = meta.get("label") or os.path.splitext(f)[0]
        cmd = [PY, "-I", os.path.join(APP, "tools", "export_replay.py"), store, "--demo", label, path, when,
               "--overrides", os.path.join(CONFIG, "categories.json")]
        log(f"processing {f} ({when})")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, **NO_WINDOW)
        if p.returncode != 0:
            log(f"FAILED {f}: {(p.stderr or p.stdout)[-400:]}"); continue
        d = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M")
        out = os.path.join(ARCHIVE, f"{d:%Y}", f"{d:%m}"); os.makedirs(out, exist_ok=True)
        with zipfile.ZipFile(os.path.join(out, f + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
            z.write(path, f)
        os.remove(path)
        if os.path.exists(path + ".json"): os.remove(path + ".json")
    log(f"processed {len(demos)} demo(s)")
    return len(demos)

def reprocess():
    """Run every archived demo through the current tools again (new stats/fights after an update). Keeps labels and dates."""
    import tempfile
    metas = {}
    d = os.path.join(DATA, "demos")
    for f in (os.listdir(d) if os.path.isdir(d) else []):
        if f.endswith(".meta.json"):
            m = json.load(open(os.path.join(d, f), encoding="utf-8")); metas[m["file"]] = m
    zips = [os.path.join(r, f) for r, _, fs in os.walk(ARCHIVE) for f in fs if f.endswith(".dem.zip")]
    done = 0
    for z in sorted(zips):
        name = os.path.basename(z)[:-4]
        m = metas.get(name)
        if not m: log(f"reprocess: no saved date/label for {name}, skipped"); continue
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(z) as zf: zf.extractall(tmp)
            cmd = [PY, "-I", os.path.join(APP, "tools", "export_replay.py"), DATA, "--demo", m["label"], os.path.join(tmp, name),
                   f"{m['date']} {m['time']}", "--overrides", os.path.join(CONFIG, "categories.json")]
            log(f"reprocessing {name}")
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, **NO_WINDOW)
            if p.returncode != 0: log(f"FAILED {name}: {(p.stderr or p.stdout)[-400:]}"); continue
            done += 1
    log(f"reprocessed {done} demo(s)")
    return done

def build_site():
    p = subprocess.run([PY, "-I", os.path.join(APP, "tools", "build_site.py"), APP, SITE, "--demos", DATA,
                        "--steam", os.path.join(DATA, "steam", "latest.json")], capture_output=True, text=True, **NO_WINDOW)
    if p.returncode != 0: raise RuntimeError("site build failed: " + p.stderr[-300:])

def finish_tunnel_setup():
    """A GitHub key handed over in config\\github.key.txt (by Claude) means setup-tunnel.ps1 still has to run: run it here."""
    if os.name != "nt" or not os.path.exists(os.path.join(CONFIG, "github.key.txt")): return
    log("tunnel: key handed over; running setup-tunnel.ps1")
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(APP, "laptop", "setup-tunnel.ps1")],
                       capture_output=True, text=True, errors="replace", **NO_WINDOW)
    tail = [l for l in (p.stdout + p.stderr).splitlines() if l.strip()][-3:]
    log("tunnel setup: " + (" | ".join(tail) or f"exit {p.returncode}"))

def run_all(check=True):
    try: finish_tunnel_setup()
    except Exception as e: log(f"tunnel setup error: {e}")
    with RunLock():
        for name, fn in [("steam", steam_stats), ("friends", friend_stats)] + ([("check", check_matches)] if check else []) + [("process", process_inbox)]:
            try: fn()
            except Exception as e: log(f"{name} error: {e}")
        build_site()

# ---------- match-over listener (CS2 Game State Integration) ----------
def listen():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    token = open(os.path.join(CONFIG, "gsi_token.txt")).read().strip()
    state = {"phase": None, "busy": False}

    def after_match():
        # Valve publishes the demo a few minutes after the match; keep checking until it shows up.
        state["busy"] = True
        try:
            for wait in (120, 180, 300, 600, 1200, 1800):
                time.sleep(wait)
                try:
                    with RunLock():
                        steam_stats_safe()
                        got = check_matches()
                        process_inbox(); build_site()
                    if got: return
                except Exception as e:
                    log(f"after-match run: {e}")
        finally:
            state["busy"] = False

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
            self.send_response(200); self.end_headers()
            try: msg = json.loads(body or b"{}")
            except Exception: return
            if msg.get("auth", {}).get("token") != token: return
            # Only the map phase is used: we react to "the match is over", nothing else.
            phase = (msg.get("map") or {}).get("phase")
            if phase == "gameover" and state["phase"] != "gameover" and not state["busy"]:
                log(f"match over on {(msg.get('map') or {}).get('name')}; checking for the demo over the next hour")
                threading.Thread(target=after_match, daemon=True).start()
            if phase: state["phase"] = phase
        def log_message(self, *a): pass

    log(f"match-over listener on port {GSI_PORT}")
    ThreadingHTTPServer(("0.0.0.0", GSI_PORT), H).serve_forever()

def steam_stats_safe():
    try: steam_stats()
    except Exception as e: log(f"steam error: {e}")
    try: friend_stats()
    except Exception as e: log(f"friends error: {e}")

# ---------- web server for site\ + the "Check for new matches" button ----------
SITE_PORT = 8080
AUTH = os.path.join(CONFIG, "site_auth.json")   # {"secret": hex for signing sessions, "allowed": [SteamID64, ...]}
STEAM_OPENID = "https://steamcommunity.com/openid/login"
SESSION_DAYS = 90

def auth_conf():
    """Session signing secret + who may press the check button from outside the home network. Created on first use:
    allowed = the SteamID in data/steam/latest.json (m0j). Add friends' SteamID64s to "allowed" to let them check too."""
    try: c = json.load(open(AUTH, encoding="utf-8"))
    except Exception: c = {}
    changed = False
    if not c.get("secret"): c["secret"] = os.urandom(32).hex(); changed = True
    if not c.get("allowed"):
        try: c["allowed"] = [str(json.load(open(os.path.join(DATA, "steam", "latest.json"), encoding="utf-8"))["steamid"])]
        except Exception: c["allowed"] = []
        changed = True
    if changed:
        os.makedirs(CONFIG, exist_ok=True)
        json.dump(c, open(AUTH, "w", encoding="utf-8"), indent=1)
    return c

def _sign(secret, text):
    import hmac, hashlib
    return hmac.new(bytes.fromhex(secret), text.encode(), hashlib.sha256).hexdigest()

def steam_verify(params):
    """Ask Steam whether this sign-in response is genuine; returns the SteamID64 or None."""
    import re
    q = {k: v for k, v in params.items() if k.startswith("openid.")}
    q["openid.mode"] = "check_authentication"
    req = urllib.request.Request(STEAM_OPENID, data=urllib.parse.urlencode(q).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        ok = "is_valid:true" in r.read().decode("utf-8", "replace")
    m = re.fullmatch(r"https://steamcommunity\.com/openid/id/(\d{17})", params.get("openid.claimed_id", ""))
    return m.group(1) if ok and m else None

def serve():
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    status = {"running": False, "started": None, "finished": None, "new": 0, "message": "No check yet since the laptop started."}
    lock = threading.Lock()

    def do_check():
        try:
            with RunLock():
                steam_stats_safe()
                got = 0
                try: got = check_matches()
                except Exception as e: log(f"check error: {e}"); status["message"] = f"Couldn't check Valve matches: {e}"
                processed = process_inbox()
                build_site()
            status["new"] = processed
            if not status["message"].startswith("Couldn't"):
                status["message"] = f"Found {processed} new match{'es' if processed != 1 else ''}." if processed else "No new matches."
        except Exception as e:
            status["message"] = f"Check failed: {e}"
        finally:
            status["running"] = False
            status["finished"] = datetime.datetime.now().isoformat(timespec="seconds")

    class H(SimpleHTTPRequestHandler):
        def end_headers(self):
            if self.path.split("?")[0].endswith((".json", ".html", "/")) or self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()
        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        # --- who is this? at home (LAN, no Cloudflare header) or through the tunnel, signed in or not
        def _local(self):
            import ipaddress
            if self.headers.get("CF-Connecting-IP"): return False          # came in through the Cloudflare tunnel
            try: ip = ipaddress.ip_address(self.client_address[0])
            except ValueError: return False
            return ip.is_private or ip.is_loopback
        def _origin(self):
            proto = self.headers.get("X-Forwarded-Proto") or ("https" if self.headers.get("CF-Connecting-IP") else "http")
            return f"{proto}://{self.headers.get('Host', 'localhost')}"
        def _session(self):
            from http.cookies import SimpleCookie
            try: v = SimpleCookie(self.headers.get("Cookie", ""))["cs2room"].value
            except Exception: return None
            try: sid, exp, sig = v.split(".")
            except ValueError: return None
            if int(exp) < time.time() or _sign(auth_conf()["secret"], f"{sid}.{exp}") != sig: return None
            return sid
        def _me(self):
            sid = self._session(); local = self._local()
            allowed = bool(sid and sid in auth_conf().get("allowed", []))
            return {"local": local, "steamid": sid, "allowed": allowed, "canCheck": local or allowed}
        def _redirect(self, where, cookie=None):
            self.send_response(302); self.send_header("Location", where)
            if cookie is not None: self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", "0"); self.end_headers()
        def _back(self, q):
            r = (q.get("r") or [""])[0]
            return "/" + (r if r.startswith("#") else "")                # only ever back into this site

        def do_GET(self):
            path, _, qs = self.path.partition("?")
            q = urllib.parse.parse_qs(qs)
            if path == "/api/status": return self._json(200, status)
            if path == "/api/me": return self._json(200, self._me())
            if path == "/auth/steam":                                    # step 1: off to Steam's sign-in page
                o = self._origin(); back = (q.get("r") or [""])[0]
                ret = f"{o}/auth/return?" + urllib.parse.urlencode({"r": back})
                return self._redirect(STEAM_OPENID + "?" + urllib.parse.urlencode({
                    "openid.ns": "http://specs.openid.net/auth/2.0", "openid.mode": "checkid_setup",
                    "openid.return_to": ret, "openid.realm": o,
                    "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                    "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"}))
            if path == "/auth/return":                                   # step 2: Steam sent us back; check it with Steam
                params = {k: v[0] for k, v in q.items()}
                sid = None
                if params.get("openid.return_to", "").startswith(self._origin() + "/auth/return"):
                    try: sid = steam_verify(params)
                    except Exception as e: log(f"steam sign-in check failed: {e}")
                if not sid: return self._redirect(self._back(q))
                exp = str(int(time.time()) + SESSION_DAYS * 86400)
                val = f"{sid}.{exp}.{_sign(auth_conf()['secret'], f'{sid}.{exp}')}"
                secure = "; Secure" if self._origin().startswith("https") else ""
                log(f"steam sign-in: {sid}{' (allowed to check)' if sid in auth_conf().get('allowed', []) else ''}")
                return self._redirect(self._back(q), f"cs2room={val}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; SameSite=Lax{secure}")
            if path == "/auth/logout":
                return self._redirect(self._back(q), "cs2room=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            return super().do_GET()
        def list_directory(self, path):                                 # no folder listings
            self.send_error(404); return None
        def do_POST(self):
            if not self.path.startswith("/api/check"): return self._json(404, {"error": "not found"})
            if not self._me()["canCheck"]:
                return self._json(403, {"error": "Sign in through Steam to check for new matches.", "message": "Sign in through Steam to check for new matches."})
            with lock:
                if status["running"]: return self._json(202, status)
                status.update(running=True, started=datetime.datetime.now().isoformat(timespec="seconds"), new=0, message="Checking…")
            log("check started from the website button")
            threading.Thread(target=do_check, daemon=True).start()
            return self._json(202, status)
        def log_message(self, *a): pass

    log(f"site on port {SITE_PORT}")
    ThreadingHTTPServer(("0.0.0.0", SITE_PORT), partial(H, directory=SITE)).serve_forever()

# ---------- Cloudflare quick tunnel + address for the GitHub launcher ----------
CLOUDFLARED = os.path.join(ROOT, "tools", "cloudflared.exe")
REPO = "mojolowjo/cs2-demo-coach"

def github_token():
    """Fine-grained token (contents: write on this repo only), saved by laptop\\setup-tunnel.ps1 as config\\github.dpapi."""
    enc = os.path.join(CONFIG, "github.dpapi")
    if os.path.exists(enc) and os.name == "nt":
        return _dpapi_decrypt(bytes.fromhex(open(enc).read().strip())).decode("utf-16-le").strip()
    return os.environ.get("CS2ROOM_GITHUB_TOKEN", "").strip() or None

def publish_address(url):
    """Write data/tunnel.json in the repo through the GitHub API (no Git needed)."""
    import base64
    tok = github_token()
    if not tok: log("tunnel: no GitHub key yet (run laptop\\setup-tunnel.ps1); launcher not updated"); return False
    api = f"https://api.github.com/repos/{REPO}/contents/data/tunnel.json"
    hdr = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "cs2room-laptop"}
    sha = None
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=20) as r: sha = json.load(r).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
    body = {"message": "laptop: tunnel address", "content": base64.b64encode(json.dumps(
        {"url": url, "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}, indent=1).encode()).decode()}
    if sha: body["sha"] = sha
    req = urllib.request.Request(api, data=json.dumps(body).encode(), method="PUT", headers={**hdr, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20): pass
    log(f"tunnel: launcher now points to {url}")
    return True

def tunnel():
    """Keep a quick tunnel to the site running; publish each new address; restart it when it stops answering."""
    import re, queue
    if not os.path.exists(CLOUDFLARED): log(f"tunnel: {CLOUDFLARED} missing"); return
    while True:
        proc = subprocess.Popen([CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{SITE_PORT}"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **NO_WINDOW)
        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout], daemon=True).start()
        url, t0 = None, time.time()
        while url is None and time.time() - t0 < 90 and proc.poll() is None:
            try: m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", lines.get(timeout=5))
            except queue.Empty: continue
            if m: url = m.group(0)
        if not url:
            log("tunnel: no address from cloudflared; retrying in 1 min"); proc.kill(); time.sleep(60); continue
        log(f"tunnel: up at {url}")
        time.sleep(10)                                     # let Cloudflare's DNS for the new name settle
        try: publish_address(url)
        except Exception as e: log(f"tunnel: couldn't update the launcher: {e}")
        fails = 0
        while proc.poll() is None:                         # health check every 2 minutes, through Cloudflare
            time.sleep(120)
            try:
                with urllib.request.urlopen(urllib.request.Request(url + "/api/status", headers={"User-Agent": "cs2room-health"}), timeout=20): fails = 0
            except Exception:
                fails += 1
                if fails >= 3: log("tunnel: stopped answering; restarting it"); proc.kill(); break
        time.sleep(5)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        if cmd == "run": run_all()
        elif cmd == "steam": steam_stats(); friend_stats(); build_site()
        elif cmd == "check": check_matches()
        elif cmd == "process": process_inbox(); build_site()
        elif cmd == "build": build_site()
        elif cmd == "listen": listen()
        elif cmd == "serve": serve()
        elif cmd == "tunnel": tunnel()
        elif cmd == "reprocess":
            with RunLock(): reprocess(); build_site()
        else: print(__doc__)
    except Exception as e:
        log(f"{cmd} failed: {e}"); sys.exit(1)
