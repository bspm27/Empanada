#!/usr/bin/env python3
"""Print a compact summary of site/data.json so the Actions log shows whether the numbers look right."""
import json
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent / "site" / "data.json").read_text())
M = d["managers"]
print("League:", d["league"])
print("Managers:", ", ".join(m["name"] for m in M.values()))
for t in d["trophies"]:
    g = lambda k: (t.get(k) or {}).get("team")
    print(f"{t['season']}: champ={g('champion')} 2nd={g('runner_up')} 3rd={g('third')} last={g('last')} {(t.get('last') or {}).get('record')}")
for s in d["seasons"]:
    print(f"-- {s['season']} standings ({s['status']})")
    for r in s["standings"]:
        print(f"   {r['team']:<28} {r['w']}-{r['l']}-{r['t']}  PF {r['pf']:>8}  Max {r['maxpf']:>8}  Eff {r['eff']}  fin {r['finish']}  po {r['playoffs']}")
sim = d.get("sim")
if sim:
    print(f"Sim: weeks {sim['first_week']}-{sim['playoff_week_start'] - 1}, playoff teams {sim['playoff_teams']}, num teams {sim['num_teams']}")
    for w in sim["weeks"]:
        proj = {M.get(k, {}).get("name", k): v for k, v in w["proj"].items()}
        print(f"   wk {w['week']}: {len(w['games'])} games; proj {proj}")
print("Trades:", len(d["trades"]), "pairs:", d["trade_pairs"])
print("Deposits:", [(x["season"], x["owes_team"], x["holder_team"]) for x in d["deposits"]])
print("Top waivers:", [(w["player"], w["team"], w["pts"]) for w in d["waivers"][:5]])
print("Winnings:", [(M[r["owner"]]["name"], r["winnings"]) for r in d["alltime"] if r["winnings"]])
print("High week:", [(x["team"], x["pts"], x["season"], x["week"]) for x in d["records"]["high_week"][:3]])
