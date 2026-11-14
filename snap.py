#!/usr/bin/env python3
"""One-off: snapshot current rosters, waivers and projections for a lineup decision."""
import json, urllib.request, time
from pathlib import Path
L = "1350581422095622144"
B = "https://api.sleeper.app/v1"
P = "https://api.sleeper.app"
OUT = Path("snapshot"); OUT.mkdir(exist_ok=True)
def get(u):
    for i in range(3):
        try:
            r = urllib.request.Request(u, headers={"User-Agent": "league-site/1.0"})
            with urllib.request.urlopen(r, timeout=60) as f:
                return json.loads(f.read().decode() or "null")
        except Exception as e:
            if i == 2: print("FAIL", u, e); return None
            time.sleep(2)
def save(n, o): (OUT / n).write_text(json.dumps(o, indent=0))
state = get(f"{B}/state/nfl"); save("state.json", state)
season, week = state["season"], int(state.get("week") or 1)
league = get(f"{B}/league/{L}"); save("league.json", league)
save("users.json", get(f"{B}/league/{L}/users"))
rosters = get(f"{B}/league/{L}/rosters"); save("rosters.json", rosters)
for w in (week - 1, week):
    save(f"matchups_{w}.json", get(f"{B}/league/{L}/matchups/{w}"))
save("transactions.json", get(f"{B}/league/{L}/transactions/{week}"))
save("traded_picks.json", get(f"{B}/league/{L}/traded_picks"))
pos = "&".join(f"position%5B%5D={p}" for p in ("QB", "RB", "WR", "TE"))
proj = {}
for w in range(week, week + 3):
    d = get(f"{P}/projections/nfl/{season}/{w}?season_type=regular&{pos}") or []
    proj[w] = {x["player_id"]: {"pts": (x.get("stats") or {}).get("pts_half_ppr"), "opp": x.get("opponent")} for x in d if x.get("player_id")}
save("projections.json", proj)
st = get(f"{P}/stats/nfl/{season}?season_type=regular&{pos}") or []
stats = {x["player_id"]: {"pts": (x.get("stats") or {}).get("pts_half_ppr"), "gp": (x.get("stats") or {}).get("gp")} for x in st if x.get("player_id")}
save("season_stats.json", stats)
save("trending_add.json", get(f"{B}/players/nfl/trending/add?lookback_hours=48&limit=50"))
players = get(f"{B}/players/nfl") or {}
keep = {}
rostered = {p for r in rosters for p in (r.get("players") or [])}
for pid, p in players.items():
    if p.get("position") not in ("QB", "RB", "WR", "TE"): continue
    if pid in rostered or pid in proj.get(week, {}) or pid in stats:
        keep[pid] = {k: p.get(k) for k in ("full_name", "position", "team", "age", "years_exp", "injury_status", "status", "depth_chart_order")}
save("players.json", keep)
print("week", week, "players", len(keep))
