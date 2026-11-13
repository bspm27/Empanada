import json, sys
from collections import defaultdict
from pathlib import Path
sys.argv = ["x"]
RAW = Path("data/raw")
d = json.loads(Path("site/data.json").read_text())
M = d["managers"]
seasons = json.loads((RAW / "seasons.json").read_text())
first = seasons[0]
events = []  # (season, order, roster_owner, pid, how)
for s in seasons:
    users = {u["user_id"] for u in json.loads((RAW / s / "users.json").read_text())}
    r2o = {r["roster_id"]: r.get("owner_id") for r in json.loads((RAW / s / "rosters.json").read_text())}
    for dr in json.loads((RAW / s / "drafts.json").read_text()):
        p = RAW / s / f"draft_{dr['draft_id']}_picks.json"
        if not p.exists():
            continue
        for pk in json.loads(p.read_text()):
            if pk.get("player_id"):
                how = "startup draft" if s == first else "rookie draft"
                events.append((int(s), -1, int(dr.get("start_time") or 0), r2o.get(pk["roster_id"]), pk["player_id"], how))
    for t in json.loads((RAW / s / "transactions.json").read_text()):
        if t.get("status") != "complete":
            continue
        how = {"trade": "trade", "waiver": "waiver/FA", "free_agent": "waiver/FA"}.get(t["type"], t["type"])
        for pid, rid in (t.get("adds") or {}).items():
            events.append((int(s), int(t.get("leg") or 0), int(t.get("status_updated") or 0), r2o.get(rid), pid, how))
events.sort()
last_acq = {}
for s, leg, ts, owner, pid, how in events:
    last_acq[(owner, pid)] = (how, s)
cur = json.loads((RAW / seasons[-1] / "rosters.json").read_text())
ktc = {r["owner"]: r for r in d["ktc"]["rankings"]}
vals = {}
for r in d["ktc"]["rankings"]:
    for name, pos, v in r["top"]:
        vals[(r["owner"], name)] = v
players = json.loads((RAW / "players.json").read_text())
def pname(pid):
    p = players.get(pid) or {}
    return p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
print("ORIGIN of current roster KTC value by team (% of player value):")
rows = []
for r in cur:
    o = r.get("owner_id")
    agg = defaultdict(int)
    detail = []
    for pid in r.get("players") or []:
        v = vals.get((o, pname(pid)), 0)
        how, s = last_acq.get((o, pid), ("unknown", None))
        agg[how] += v
        detail.append((v, pname(pid), how, s))
    tot = sum(agg.values()) or 1
    rows.append((M[o]["name"], tot, {k: round(100 * v / tot) for k, v in agg.items()}, sorted(detail, reverse=True)[:8]))
for name, tot, pct, det in sorted(rows, key=lambda x: -x[2].get("startup draft", 0)):
    print(f"  {name:<13} players {tot:>6}  {pct}")
    if name == "awillis7":
        print("     awillis7 top players:", det)
sc = {x["owner"]: x for x in d["ktc"]["scorecard"]}
aw = [k for k, v in M.items() if v["name"] == "awillis7"][0]
print("awillis7 trade scorecard:", sc.get(aw))
print("awillis7 waiver HOF entries:", [(w["player"], w["pts"]) for w in d["waivers"] if w["owner"] == aw])
for dr in d["drafts"]:
    rc = next((x for x in dr["report"] if x["owner"] == aw), None)
    rank = [x["owner"] for x in dr["report"]].index(aw) + 1 if rc else None
    print(f"awillis7 {dr['season']} draft: rank {rank}/{len(dr['report'])}", rc)
print("dynasty rank:", [i + 1 for i, r in enumerate(d["ktc"]["rankings"]) if r["owner"] == aw], ktc[aw]["total"], ktc[aw]["players"], ktc[aw]["picks_value"])
