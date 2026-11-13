import json
from collections import Counter, defaultdict
from pathlib import Path
RAW = Path("data/raw")
for s in json.loads((RAW / "seasons.json").read_text()):
    lg = json.loads((RAW / s / "league.json").read_text())
    ps = int(lg["settings"].get("playoff_week_start", 15))
    users = {u["user_id"]: u["display_name"] for u in json.loads((RAW / s / "users.json").read_text())}
    r2n = {r["roster_id"]: users.get(r.get("owner_id"), r["roster_id"]) for r in json.loads((RAW / s / "rosters.json").read_text())}
    meet = defaultdict(Counter)
    weeks_with_games = []
    for w in range(1, ps):
        rows = json.loads((RAW / s / f"matchups_{w}.json").read_text())
        mids = defaultdict(list)
        for m in rows:
            if m.get("matchup_id") is not None:
                mids[m["matchup_id"]].append(r2n[m["roster_id"]])
        if not mids:
            continue
        weeks_with_games.append(w)
        if w in (2, 3, 4):
            continue
        for p in mids.values():
            if len(p) == 2:
                meet[p[0]][p[1]] += 1; meet[p[1]][p[0]] += 1
    print(f"{s}: playoff_week_start={ps} weeks={weeks_with_games}")
    for team in sorted(meet, key=str):
        c = meet[team]
        dist = Counter(c.values())
        missing = [o for o in r2n.values() if o != team and o not in c]
        if set(c.values()) != {1} or missing:
            print(f"   {team}: meetings-per-opponent {dict(dist)} repeats={[o for o,n in c.items() if n>1]} never={missing}")
    if all(set(meet[t].values()) == {1} for t in meet):
        print("   every pair met exactly once")
