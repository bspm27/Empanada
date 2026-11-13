import json
from collections import defaultdict
from pathlib import Path
RAW = Path("data/raw")
d = json.loads(Path("site/data.json").read_text())
M = d["managers"]
AW = [k for k, v in M.items() if v["name"] == "awillis7"][0]
players = json.loads((RAW / "players.json").read_text())
ELIG = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "FLEX": {"RB", "WR", "TE"}, "SUPER_FLEX": {"QB", "RB", "WR", "TE"}}
def pos(pid):
    p = players.get(pid) or {}
    return set(p.get("fantasy_positions") or [p.get("position")])
def nm(pid):
    p = players.get(pid) or {}
    return p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip() or pid
def best(pp, slots):
    used, tot = set(), 0
    for sl in sorted(slots, key=lambda s: len(ELIG[s])):
        for pid, v in sorted(pp.items(), key=lambda kv: -kv[1]):
            if pid not in used and pos(pid) & ELIG[sl]:
                used.add(pid); tot += v; break
    return tot
seasons = json.loads((RAW / "seasons.json").read_text())
print("AW team names:", {s: next((r["team"] for r in x["standings"] if r["owner"] == AW), None) for x in d["seasons"] for s in [x["season"]]})
for x in d["seasons"]:
    st = x["standings"]
    me = next(r for r in st if r["owner"] == AW)
    pf_rank = sorted(st, key=lambda r: -r["pf"]).index(me) + 1
    eff_rank = sorted(st, key=lambda r: -(r["eff"] or 0)).index(me) + 1
    print(f"AW {x['season']}: rank {me['rank']} rec {me['w']}-{me['l']} PF {me['pf']} (#{pf_rank}) max {me['maxpf']} eff {me['eff']} (#{eff_rank}/12) finish {me['finish']} playoffs {me['playoffs']} bench_left {round(me['maxpf']-me['pf'],1)}")
print("AW alltime:", next(r for r in d["alltime"] if r["owner"] == AW))
print("Alltime eff ranking:", [(M[r["owner"]]["name"], r["eff"]) for r in sorted(d["alltime"], key=lambda r: -(r["eff"] or 0))])
print("Trophies:", [(t["season"], t["champion"]["team"] if t["champion"] else None, M[t["champion"]["owner"]]["name"] if t["champion"] else None, t["runner_up"] and M[t["runner_up"]["owner"]]["name"], t["third"] and M[t["third"]["owner"]]["name"]) for t in d["trophies"]])
cost_wins, zeros, blunders = [], [], []
for s in seasons:
    lg = json.loads((RAW / s / "league.json").read_text())
    slots = [p for p in lg["roster_positions"] if p in ELIG]
    ps = int(lg["settings"].get("playoff_week_start", 15))
    rosters = json.loads((RAW / s / "rosters.json").read_text())
    r2o = {r["roster_id"]: r.get("owner_id") for r in rosters}
    users = {u["user_id"]: u["display_name"] for u in json.loads((RAW / s / "users.json").read_text())}
    for w in range(1, 18):
        f = RAW / s / f"matchups_{w}.json"
        rows = json.loads(f.read_text()) if f.exists() else []
        if not rows or all((m.get("points") or 0) == 0 for m in rows):
            continue
        mine = next((m for m in rows if r2o.get(m["roster_id"]) == AW), None)
        if not mine:
            continue
        opp = next((m for m in rows if m is not mine and m.get("matchup_id") is not None and m.get("matchup_id") == mine.get("matchup_id")), None)
        pp = mine.get("players_points") or {}
        opt = best(pp, slots)
        act = mine.get("points") or 0
        st, sp = mine.get("starters") or [], mine.get("starters_points") or []
        for pid, v in zip(st, sp):
            if pid == "0":
                zeros.append((s, w, "EMPTY SLOT"))
            elif v == 0:
                zeros.append((s, w, nm(pid)))
        # biggest single swap: bench player who outscored a starter he could have replaced
        bench = [p for p in (mine.get("players") or []) if p not in st]
        for b in bench:
            for pid, v in zip(st, sp):
                if pid != "0" and pos(b) & pos(pid) and pp.get(b, 0) - v > 0:
                    blunders.append((round(pp.get(b, 0) - v, 1), s, w, f"started {nm(pid)} ({v}) over {nm(b)} ({pp.get(b,0)})"))
        if opp and w < ps and w not in (2, 3, 4):
            op = opp.get("points") or 0
            if act < op <= opt:
                cost_wins.append((s, w, users.get(r2o.get(opp["roster_id"])), round(act, 1), round(op, 1), round(opt, 1)))
        if opp and w >= ps and act < (opp.get("points") or 0) <= opt:
            cost_wins.append((s, w, "PLAYOFF vs " + str(users.get(r2o.get(opp["roster_id"]))), round(act, 1), round(opp.get("points") or 0, 1), round(opt, 1)))
print("Losses where optimal lineup would have won:", len(cost_wins))
for c in cost_wins: print("   ", c)
print("Zero-point starters:", zeros)
print("Top swap blunders:")
seen = set()
for b in sorted(blunders, reverse=True):
    if (b[1], b[2], b[3]) in seen: continue
    seen.add((b[1], b[2], b[3])); print("   ", b)
    if len(seen) >= 8: break
print("Trades:")
for t in d["trades"]:
    sides = {s["owner"]: s for s in t["sides"]}
    if AW in sides:
        me = sides[AW]; others = [s for s in t["sides"] if s["owner"] != AW]
        print("   ", t["date"], "got", [p["name"] for p in me["players"]] + [p["label"] + ("->" + p["became"] if p.get("became") else "") for p in me["picks"]], "gave", [p["name"] for o in others for p in o["players"]] + [p["label"] + ("->" + p["became"] if p.get("became") else "") for o in others for p in o["picks"]], "net_then", me.get("net_then"), "net_now", me.get("net_now"))
print("Draft picks:")
for dr in d["drafts"]:
    for p in dr["picks"]:
        if p["picker"] == AW:
            print("   ", dr["season"], p["pick"], p["player"], p["value"], "#" + str(p["vrank"]), p["diff"], p["grade"])
print("Waiver adds in HOF:", [(w["player"], w["pts"]) for w in d["waivers"] if w["owner"] == AW])
r = next(x for x in d["ktc"]["rankings"] if x["owner"] == AW)
ages = [(n, (next((p for p in players.values() if p.get("full_name") == n), {}) or {}).get("age")) for n, _, v in r["top"][:8]]
print("Top players ages:", ages)
print("Dynasty rank:", [i + 1 for i, x in enumerate(d["ktc"]["rankings"]) if x["owner"] == AW], "starters rank:", sorted(d["ktc"]["rankings"], key=lambda x: -x["starters"]).index(r) + 1)
if d.get("sim"):
    print("Sim team:", next(t for t in d["sim"]["teams"] if t["owner"] == AW))
