// Logs the demo-bot Steam account into CS2's game coordinator and asks for the replay link of each match share code.
// Input (stdin, JSON):  {"username": "...", "password": "...", "codes": ["CSGO-xxxxx-...", ...]}
// Output (stdout, JSON): {"results": [{"code", "url", "matchtime", "matchid"}], "error": null | "..."}
// The bot never plays; it only "launches" CS2 long enough to ask for match info.
const SteamUser = require("steam-user");
const GlobalOffensive = require("globaloffensive");

let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", main);

function finish(out) {
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
}

function main() {
  const cfg = JSON.parse(input);
  const results = [];
  const user = new SteamUser({ autoRelogin: false });
  const csgo = new GlobalOffensive(user);
  const timer = setTimeout(() => finish({ results, error: "timed out talking to Steam / the CS2 game coordinator" }), 120000);

  user.on("steamGuard", () => {
    clearTimeout(timer);
    finish({ results, error: "Steam Guard code requested for the bot account. Turn Steam Guard off on m0j_demobot." });
  });
  user.on("error", (e) => {
    clearTimeout(timer);
    finish({ results, error: "Steam login failed: " + (e && e.message ? e.message : String(e)) });
  });
  user.on("loggedOn", () => user.gamesPlayed([730]));

  csgo.on("connectedToGC", async () => {
    for (const code of cfg.codes) {
      try {
        const match = await new Promise((resolve, reject) => {
          const t = setTimeout(() => reject(new Error("no answer for " + code)), 20000);
          csgo.once("matchList", (matches) => { clearTimeout(t); resolve(matches && matches[0]); });
          csgo.requestGame(code);
        });
        if (!match) { results.push({ code, url: null, error: "match not found (too old?)" }); continue; }
        const rounds = match.roundstatsall || [];
        const last = rounds[rounds.length - 1] || {};
        results.push({ code, url: last.map || null, matchtime: match.matchtime || null, matchid: String(match.matchid || "") });
      } catch (e) {
        results.push({ code, url: null, error: e.message });
      }
    }
    clearTimeout(timer);
    user.logOff();
    setTimeout(() => finish({ results, error: null }), 500);
  });

  user.logOn({ accountName: cfg.username, password: cfg.password });
}
