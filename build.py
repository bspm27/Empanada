#!/usr/bin/env python3
"""Turn data/raw/ into site/data.json for the league page."""
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data.json"

PAYOUTS = {1: 700, 2: 350, 3: 150}
BUY_IN = 100
DEPOSIT = BUY_IN // 2
PALOOZA_WEEKS = {2, 3, 4, 5}  # matchups set after the fact so the top 6 scorers win: count for records, not head-to-head

SLOT_ELIG = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"}, "WRRB_FLEX": {"RB", "WR"}, "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}
OUT_ALL_WEEKS = {"IR", "PUP", "Sus", "NA", "COV"}
OUT_THIS_WEEK = {"Out"}


def load(path, default=None):
    p = RAW / path
    return json.loads(p.read_text()) if p.exists() else default


def r2(x):
    return round(float(x), 2)


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


# ---------------------------------------------------------------- lineups
def lineup_slots(roster_positions):
    slots = [s for s in roster_positions if s in SLOT_ELIG]
    return sorted(slots, key=lambda s: len(SLOT_ELIG[s]))


def best_lineup_detail(points, positions, slots):
    """Same greedy fill as best_lineup, returning [(slot, pid, pts)] in lineup order."""
    ranked = sorted(points.items(), key=lambda kv: kv[1], reverse=True)
    used, out = set(), []
    for slot in slots:
        for pid, pts in ranked:
            if pid not in used and positions.get(pid, set()) & SLOT_ELIG[slot]:
                used.add(pid)
                out.append((slot, pid, pts))
                break
    order = ["QB", "RB", "WR", "TE", "FLEX", "WRRB_FLEX", "REC_FLEX", "SUPER_FLEX", "K", "DEF"]
    return sorted(out, key=lambda x: (order.index(x[0]) if x[0] in order else 99, -x[2]))


def best_lineup(points, positions, slots):
    """points: {pid: pts}; positions: {pid: set(pos)}. Greedy fill, tightest slot first.
    Optimal when slot eligibility sets are nested (true for standard lineups)."""
    ranked = sorted(points.items(), key=lambda kv: kv[1], reverse=True)
    used, total = set(), 0.0
    for slot in slots:
        elig = SLOT_ELIG[slot]
        for pid, pts in ranked:
            if pid not in used and positions.get(pid, set()) & elig:
                used.add(pid)
                total += pts
                break
    return total


# ---------------------------------------------------------------- load
state = load("state.json", {})
players = load("players.json", {})
season_ids = load("seasons.json", [])


def ppos(pid):
    p = players.get(pid) or {}
    fp = p.get("fantasy_positions") or ([p["position"]] if p.get("position") else [])
    return set(fp)


def pname(pid):
    p = players.get(pid) or {}
    if p.get("full_name"):
        return p["full_name"]
    if p.get("first_name"):
        return f"{p['first_name']} {p.get('last_name', '')}".strip()
    return pid


managers = {}          # owner_id -> {name, avatar}
seasons = []           # per-season dicts
games = []             # every completed head-to-head game
weekly_starters = defaultdict(dict)  # (season, week) -> {owner: {pid: pts}}

for s in season_ids:
    league = load(f"{s}/league.json")
    users = {u["user_id"]: u for u in load(f"{s}/users.json", [])}
    rosters = load(f"{s}/rosters.json", [])
    st = league.get("settings", {})
    ps = int(st.get("playoff_week_start") or 15)
    slots = lineup_slots(league.get("roster_positions", []))
    is_current = league.get("status") != "complete"
    if is_current and state.get("season") == s and state.get("season_type") == "regular":
        last_done = int(state.get("week") or 1) - 1
    elif is_current and league.get("status") == "pre_draft":
        last_done = 0
    else:
        last_done = 18

    r2o, teams = {}, {}
    for r in rosters:
        oid = r.get("owner_id") or f"roster_{r['roster_id']}"
        r2o[r["roster_id"]] = oid
        u = users.get(oid, {})
        managers[oid] = {
            "name": u.get("display_name") or managers.get(oid, {}).get("name") or f"Team {r['roster_id']}",
            "avatar": u.get("avatar") or managers.get(oid, {}).get("avatar"),
        }
        rs = r.get("settings", {})
        teams[oid] = {
            "owner": oid, "roster_id": r["roster_id"],
            "team": (u.get("metadata") or {}).get("team_name") or u.get("display_name") or f"Team {r['roster_id']}",
            "w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0,
            "maxpf_sleeper": (rs.get("ppts", 0) or 0) + (rs.get("ppts_decimal", 0) or 0) / 100,
            "maxpf_calc": 0.0, "scores": [], "results": [],
            "players": r.get("players") or [], "reserve": r.get("reserve") or [], "taxi": r.get("taxi") or [],
        }

    # matchups
    week_scores = {}
    for w in range(1, 19):
        rows = load(f"{s}/matchups_{w}.json", [])
        if not rows:
            continue
        done = w <= last_done
        by_mid = defaultdict(list)
        for m in rows:
            oid = r2o.get(m["roster_id"])
            if oid is None:
                continue
            week_scores[(w, m["roster_id"])] = m.get("points") or 0
            if done:
                starters = m.get("starters") or []
                sp = m.get("starters_points") or []
                weekly_starters[(s, w)][oid] = {pid: sp[i] for i, pid in enumerate(starters) if i < len(sp) and pid != "0"}
                if w < ps:
                    pp = m.get("players_points") or {}
                    teams[oid]["maxpf_calc"] += best_lineup(pp, {p: ppos(p) for p in pp}, slots)
            if m.get("matchup_id") is not None:
                by_mid[m["matchup_id"]].append(m)
        if not done or w >= ps:
            continue
        for pair in by_mid.values():
            if len(pair) != 2:
                continue
            a, b = pair
            oa, ob = r2o[a["roster_id"]], r2o[b["roster_id"]]
            pa, pb = a.get("points") or 0, b.get("points") or 0
            games.append({"season": s, "week": w, "a": oa, "b": ob, "pa": r2(pa), "pb": r2(pb), "playoff": False,
                          "palooza": w in PALOOZA_WEEKS})
            for me, opp, mp, op in ((oa, ob, pa, pb), (ob, oa, pb, pa)):
                t = teams[me]
                t["pf"] += mp
                t["pa"] += op
                t["scores"].append(mp)
                res = "W" if mp > op else "L" if mp < op else "T"
                t["results"].append(res)
                t[{"W": "w", "L": "l", "T": "t"}[res]] += 1

    # playoffs (winners bracket)
    bracket = load(f"{s}/winners_bracket.json", []) or []
    place = {}
    playoff_teams = set()
    for g in bracket:
        for k in ("t1", "t2"):
            if isinstance(g.get(k), int):
                playoff_teams.add(r2o.get(g[k]))
        if g.get("w") and g.get("l") and isinstance(g.get("t1"), int) and isinstance(g.get("t2"), int):
            wk = ps + int(g.get("r", 1)) - 1
            if wk <= last_done:
                ta, tb = r2o[g["t1"]], r2o[g["t2"]]
                games.append({
                    "season": s, "week": wk, "a": ta, "b": tb,
                    "pa": r2(week_scores.get((wk, g["t1"]), 0)), "pb": r2(week_scores.get((wk, g["t2"]), 0)),
                    "playoff": True, "winner": r2o[g["w"]],
                })
        if g.get("p") == 1 and g.get("w"):
            place[1], place[2] = r2o[g["w"]], r2o[g["l"]]
        if g.get("p") == 3 and g.get("w"):
            place[3] = r2o[g["w"]]

    for t in teams.values():
        t["maxpf"] = max(t["maxpf_sleeper"] or t["maxpf_calc"], t["pf"])
        g = t["w"] + t["l"] + t["t"]
        t["pct"] = (t["w"] + 0.5 * t["t"]) / g if g else 0
        t["eff"] = t["pf"] / t["maxpf"] if t["maxpf"] else None

    order = sorted(teams.values(), key=lambda t: (-t["pct"], -t["pf"]))
    complete = league.get("status") == "complete"
    last_place = None
    if complete and order:
        last_place = sorted(teams.values(), key=lambda t: (t["pct"], t["pf"]))[0]["owner"]

    seasons.append({
        "season": s, "name": league.get("name"), "status": league.get("status"), "complete": complete,
        "playoff_week_start": ps, "playoff_teams_n": int(st.get("playoff_teams") or 6),
        "last_done": last_done, "slots": slots, "r2o": r2o, "teams": teams, "order": order,
        "place": place, "last_place": last_place, "playoff_set": {p for p in playoff_teams if p},
        "num_teams": int(st.get("num_teams") or len(teams)), "league": league,
    })

current = seasons[-1] if seasons else None


def tname(season_obj, oid):
    t = season_obj["teams"].get(oid)
    return t["team"] if t else managers.get(oid, {}).get("name", oid)


# ---------------------------------------------------------------- per-season standings + trophies
season_out, trophies = [], []
winnings = defaultdict(int)
titles, seconds, thirds, lasts, playoff_apps = (defaultdict(int) for _ in range(5))
for so in seasons:
    rows = []
    for i, t in enumerate(so["order"], 1):
        rows.append({
            "rank": i, "owner": t["owner"], "team": t["team"], "w": t["w"], "l": t["l"], "t": t["t"],
            "pf": r2(t["pf"]), "pa": r2(t["pa"]), "maxpf": r2(t["maxpf"]),
            "eff": r2(t["eff"] * 100) if t["eff"] else None,
            "finish": next((k for k, v in so["place"].items() if v == t["owner"]), None),
            "playoffs": t["owner"] in so["playoff_set"],
        })
    season_out.append({"season": so["season"], "status": so["status"], "standings": rows})
    for o in so["playoff_set"]:
        playoff_apps[o] += 1
    if so["complete"]:
        p = so["place"]
        for k, amt in PAYOUTS.items():
            if p.get(k):
                winnings[p[k]] += amt
        if p.get(1):
            titles[p[1]] += 1
        if p.get(2):
            seconds[p[2]] += 1
        if p.get(3):
            thirds[p[3]] += 1
        if so["last_place"]:
            lasts[so["last_place"]] += 1
        top = so["order"][0] if so["order"] else None
        pf_lead = max(so["teams"].values(), key=lambda t: t["pf"]) if so["teams"] else None
        lp = so["teams"].get(so["last_place"]) if so["last_place"] else None
        trophies.append({
            "season": so["season"],
            "champion": p.get(1) and {"owner": p[1], "team": tname(so, p[1])},
            "runner_up": p.get(2) and {"owner": p[2], "team": tname(so, p[2])},
            "third": p.get(3) and {"owner": p[3], "team": tname(so, p[3])},
            "last": lp and {"owner": lp["owner"], "team": lp["team"], "record": f"{lp['w']}-{lp['l']}" + (f"-{lp['t']}" if lp["t"] else ""), "pf": r2(lp["pf"])},
            "top_seed": top and {"owner": top["owner"], "team": top["team"], "record": f"{top['w']}-{top['l']}"},
            "points_leader": pf_lead and {"owner": pf_lead["owner"], "team": pf_lead["team"], "pf": r2(pf_lead["pf"])},
        })

# ---------------------------------------------------------------- all-time table
alltime = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0, "maxpf": 0.0, "seasons": 0})
for so in seasons:
    for oid, t in so["teams"].items():
        a = alltime[oid]
        for k in ("w", "l", "t"):
            a[k] += t[k]
        a["pf"] += t["pf"]
        a["pa"] += t["pa"]
        a["maxpf"] += t["maxpf"]
        a["seasons"] += 1
alltime_rows = []
for oid, a in alltime.items():
    g = a["w"] + a["l"] + a["t"]
    alltime_rows.append({
        "owner": oid, "seasons": a["seasons"], "w": a["w"], "l": a["l"], "t": a["t"],
        "pct": r2((a["w"] + 0.5 * a["t"]) / g * 100) if g else 0,
        "pf": r2(a["pf"]), "pa": r2(a["pa"]),
        "eff": r2(a["pf"] / a["maxpf"] * 100) if a["maxpf"] else None,
        "titles": titles[oid], "seconds": seconds[oid], "thirds": thirds[oid], "lasts": lasts[oid],
        "playoffs": playoff_apps[oid], "winnings": winnings[oid],
    })
alltime_rows.sort(key=lambda r: (-r["titles"], -r["pct"]))

# ---------------------------------------------------------------- head to head
h2h_sets = {k: defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0}) for k in ("all", "reg", "po")}
for g in games:
    if g.get("palooza"):
        continue
    if g["playoff"]:
        wa = 1 if g["winner"] == g["a"] else 0
        res_a = "w" if wa else "l"
    else:
        res_a = "w" if g["pa"] > g["pb"] else "l" if g["pa"] < g["pb"] else "t"
    res_b = {"w": "l", "l": "w", "t": "t"}[res_a]
    for me, opp, mp, op, res in ((g["a"], g["b"], g["pa"], g["pb"], res_a), (g["b"], g["a"], g["pb"], g["pa"], res_b)):
        for key in ("all", "po" if g["playoff"] else "reg"):
            c = h2h_sets[key][f"{me}|{opp}"]
            c[res] += 1
            c["pf"] += mp
            c["pa"] += op
h2h_out = {name: {k: {**v, "pf": r2(v["pf"]), "pa": r2(v["pa"])} for k, v in d.items()} for name, d in h2h_sets.items()}

# ---------------------------------------------------------------- record book
season_by_id = {so["season"]: so for so in seasons}


def gteam(g, side):
    return tname(season_by_id[g["season"]], g[side])


scores = []
for g in games:
    for side, opp, pts, opts in (("a", "b", g["pa"], g["pb"]), ("b", "a", g["pb"], g["pa"])):
        scores.append({"season": g["season"], "week": g["week"], "owner": g[side], "team": gteam(g, side),
                       "opp": g[opp], "opp_team": gteam(g, opp), "pts": pts, "opp_pts": opts, "playoff": g["playoff"]})
reg_scores = [x for x in scores if not x["playoff"] and x["pts"] > 0]
margins = []
for g in games:
    if (g["pa"] == 0 and g["pb"] == 0) or g.get("palooza"):
        continue
    w, l = ("a", "b") if g["pa"] >= g["pb"] else ("b", "a")
    margins.append({"season": g["season"], "week": g["week"], "playoff": g["playoff"],
                    "winner": g[w], "winner_team": gteam(g, w), "loser": g[l], "loser_team": gteam(g, l),
                    "wpts": g["p" + w], "lpts": g["p" + l], "margin": r2(abs(g["pa"] - g["pb"]))})

streaks = []
for so in seasons:
    for oid, t in so["teams"].items():
        for kind in ("W", "L"):
            best = cur = 0
            for res in t["results"]:
                cur = cur + 1 if res == kind else 0
                best = max(best, cur)
            if best:
                streaks.append({"kind": kind, "len": best, "owner": oid, "team": t["team"], "season": so["season"]})

season_lines = []
for so in seasons:
    if not so["complete"]:
        continue
    for oid, t in so["teams"].items():
        season_lines.append({"season": so["season"], "owner": oid, "team": t["team"],
                             "w": t["w"], "l": t["l"], "t": t["t"], "pct": t["pct"], "pf": r2(t["pf"])})

N = 5
records = {
    "high_week": sorted(reg_scores, key=lambda x: -x["pts"])[:N],
    "low_week": sorted(reg_scores, key=lambda x: x["pts"])[:N],
    "blowouts": sorted(margins, key=lambda x: -x["margin"])[:N],
    "closest": sorted(margins, key=lambda x: x["margin"])[:N],
    "win_streaks": sorted([s for s in streaks if s["kind"] == "W"], key=lambda x: -x["len"])[:N],
    "loss_streaks": sorted([s for s in streaks if s["kind"] == "L"], key=lambda x: -x["len"])[:N],
    "best_seasons": sorted(season_lines, key=lambda x: (-x["pct"], -x["pf"]))[:N],
    "worst_seasons": sorted(season_lines, key=lambda x: (x["pct"], x["pf"]))[:N],
    "most_pf": sorted(season_lines, key=lambda x: -x["pf"])[:N],
    "fewest_pf": sorted(season_lines, key=lambda x: x["pf"])[:N],
}

# ---------------------------------------------------------------- transactions
txns = []
for so in seasons:
    for t in load(f"{so['season']}/transactions.json", []) or []:
        if t.get("status") != "complete":
            continue
        t["_season"] = so["season"]
        t["_so"] = so
        txns.append(t)
txns.sort(key=lambda t: (int(t["_season"]), int(t.get("leg") or 0), int(t.get("status_updated") or t.get("created") or 0)))

# ownership-ending events per player, in order
leave_events = defaultdict(list)  # (pid, owner) -> [(season, leg)]
for t in txns:
    r2o = t["_so"]["r2o"]
    for pid, rid in (t.get("drops") or {}).items():
        leave_events[(pid, r2o.get(rid))].append((int(t["_season"]), int(t.get("leg") or 0)))
    for pid, rid in (t.get("adds") or {}).items():
        # if someone else acquires the player, every other owner has lost him
        leave_events[("__add__", pid)].append((int(t["_season"]), int(t.get("leg") or 0), r2o.get(rid)))

starter_weeks = sorted(weekly_starters.keys(), key=lambda k: (int(k[0]), k[1]))


def end_of_tenure(pid, owner, start):
    ends = [e for e in leave_events.get((pid, owner), []) if e > start]
    # any later add of this player ends the tenure: by someone else (he left), or by the same owner (a new tenure starts)
    ends += [(e[0], e[1]) for e in leave_events.get(("__add__", pid), []) if (e[0], e[1]) > start]
    return min(ends) if ends else (9999, 99)


waivers = []
for t in txns:
    if t.get("type") not in ("waiver", "free_agent"):
        continue
    so = t["_so"]
    for pid, rid in (t.get("adds") or {}).items():
        owner = so["r2o"].get(rid)
        start = (int(t["_season"]), int(t.get("leg") or 0))
        end = end_of_tenure(pid, owner, start)
        pts, started = 0.0, 0
        for (s, w) in starter_weeks:
            key = (int(s), w)
            if start <= key < end:
                v = weekly_starters[(s, w)].get(owner, {}).get(pid)
                if v is not None:
                    pts += v
                    started += 1
        waivers.append({
            "season": t["_season"], "week": t.get("leg"), "owner": owner, "team": tname(so, owner),
            "player": pname(pid), "pos": "/".join(sorted(ppos(pid))) or "?", "type": t["type"],
            "bid": (t.get("settings") or {}).get("waiver_bid"), "pts": r2(pts), "starts": started,
        })
waivers.sort(key=lambda x: -x["pts"])
waivers = [w for w in waivers if w["pts"] > 0][:30]


def pick_label(dp, so):
    orig = so["r2o"].get(dp.get("roster_id"))
    return f"{dp['season']} {ordinal(int(dp['round']))} ({managers.get(orig, {}).get('name', '?')})"


trades = []
pairs = defaultdict(int)
for t in txns:
    if t.get("type") != "trade":
        continue
    so = t["_so"]
    r2o = so["r2o"]
    sides = {r2o.get(rid): {"players": [], "picks": [], "faab": 0} for rid in t.get("roster_ids") or []}
    for pid, rid in (t.get("adds") or {}).items():
        sides.setdefault(r2o.get(rid), {"players": [], "picks": [], "faab": 0})["players"].append(
            {"id": pid, "name": pname(pid), "pos": "/".join(sorted(ppos(pid)))})
    for dp in t.get("draft_picks") or []:
        sides.setdefault(r2o.get(dp.get("owner_id")), {"players": [], "picks": [], "faab": 0})["picks"].append(
            {"season": dp["season"], "round": dp["round"], "label": pick_label(dp, so), "orig_roster": dp.get("roster_id")})
    for wb in t.get("waiver_budget") or []:
        sides.setdefault(r2o.get(wb.get("receiver")), {"players": [], "picks": [], "faab": 0})["faab"] += wb.get("amount", 0)
    owners = [o for o in sides if o]
    for i in range(len(owners)):
        for j in range(i + 1, len(owners)):
            pairs["|".join(sorted((owners[i], owners[j])))] += 1
    ts = int(t.get("status_updated") or t.get("created") or 0) / 1000
    trades.append({
        "id": t["transaction_id"], "season": t["_season"], "week": t.get("leg"),
        "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else None,
        "sides": [{"owner": o, "team": tname(so, o), **v} for o, v in sides.items() if o],
    })
trades.sort(key=lambda x: x["date"] or "", reverse=True)

trade_counts = defaultdict(int)
for k, v in pairs.items():
    a, b = k.split("|")
    trade_counts[a] += v
    trade_counts[b] += v

# ---------------------------------------------------------------- deposits (traded future 1sts)
deposits = []
if current:
    cur_season = int(current["season"])
    tp = load(f"{current['season']}/traded_picks.json", []) or []
    r2o = current["r2o"]
    for dp in tp:
        if int(dp["round"]) != 1 or int(dp["season"]) <= cur_season:
            continue
        if dp.get("owner_id") == dp.get("roster_id"):
            continue
        orig, holder = r2o.get(dp["roster_id"]), r2o.get(dp["owner_id"])
        deposits.append({"season": dp["season"], "owes": orig, "owes_team": tname(current, orig),
                         "holder": holder, "holder_team": tname(current, holder), "amount": DEPOSIT})
    deposits.sort(key=lambda d: (d["season"], d["owes_team"]))

# ---------------------------------------------------------------- playoff sim inputs (current season)
sim = None
if current and current["status"] == "in_season":
    s = current["season"]
    ps = current["playoff_week_start"]
    first = current["last_done"] + 1
    slots = current["slots"]
    teams_in = []
    for oid, t in current["teams"].items():
        sd = statistics.pstdev(t["scores"]) if len(t["scores"]) >= 3 else 25.0
        teams_in.append({
            "owner": oid, "roster_id": t["roster_id"], "team": t["team"], "w": t["w"], "l": t["l"], "t": t["t"],
            "pf": r2(t["pf"]), "maxpf": r2(t["maxpf"]), "sd": r2(max(sd, 15.0)),
            "avg": r2(sum(t["scores"]) / len(t["scores"])) if t["scores"] else None,
        })
    weeks = []
    for w in range(first, ps):
        proj_rows = load(f"projections/{s}_{w}.json", []) or []
        proj = {}
        for row in proj_rows:
            pid = row.get("player_id")
            pts = (row.get("stats") or {}).get("pts_half_ppr")
            if pid and pts is not None:
                proj[pid] = float(pts)
        rows = load(f"{s}/matchups_{w}.json", []) or []
        by_mid = defaultdict(list)
        projected = {}
        for t in current["teams"].values():
            pool = {}
            for pid in set(t["players"]) - set(t["reserve"]):
                inj = (players.get(pid) or {}).get("injury_status")
                if inj in OUT_ALL_WEEKS or (w == first and inj in OUT_THIS_WEEK):
                    continue
                pool[pid] = proj.get(pid, 0.0)
            projected[t["owner"]] = r2(best_lineup(pool, {p: ppos(p) for p in pool}, slots)) if proj else None
        for m in rows:
            if m.get("matchup_id") is not None:
                by_mid[m["matchup_id"]].append(current["r2o"].get(m["roster_id"]))
        weeks.append({"week": w, "games": [p for p in by_mid.values() if len(p) == 2], "proj": projected})
    sim = {"season": s, "first_week": first, "playoff_week_start": ps,
           "playoff_teams": current["playoff_teams_n"], "num_teams": current["num_teams"],
           "teams": teams_in, "weeks": weeks}

# ---------------------------------------------------------------- KeepTradeCut values
import bisect  # noqa: E402
import re  # noqa: E402

KTC = ROOT / "data" / "ktc"
daily_files = sorted((KTC / "daily").glob("*.json")) if (KTC / "daily").exists() else []
ktc_today = json.loads(daily_files[-1].read_text()) if daily_files else {}
ktc_date = daily_files[-1].stem if daily_files else None
ROUND_ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def knorm(name):
    n = re.sub(r"[^a-z ]", "", (name or "").lower().replace("-", " "))
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


ktc_all = json.loads((KTC / "all.json").read_text()) if (KTC / "all.json").exists() else {}
is_pick = lambda e: e.get("pos") == "RDP" or (e.get("name") or "")[:2] == "20"  # noqa: E731
ktc_key, ktc_name_count, ktc_name = {}, defaultdict(int), {}
for src in (ktc_today, ktc_all):  # current top 500 first, then everyone else KTC knows (retired, low-ranked)
    for slug, e in src.items():
        if is_pick(e) or (knorm(e["name"]), e["pos"]) in ktc_key:
            continue
        ktc_key[(knorm(e["name"]), e["pos"])] = slug
        ktc_name_count[knorm(e["name"])] += 1
        ktc_name[knorm(e["name"])] = slug
pick_slug = {e["name"]: slug for slug, e in ktc_today.items() if e["pos"] == "RDP"}
pick_slug_hist = {**{e["name"]: slug for slug, e in ktc_all.items() if is_pick(e)}, **pick_slug}


def slug_for(pid):
    pl = players.get(pid) or {}
    nm = knorm(pl.get("full_name") or f"{pl.get('first_name', '')} {pl.get('last_name', '')}")
    s = ktc_key.get((nm, pl.get("position")))
    if not s and ktc_name_count.get(nm) == 1:
        s = ktc_name[nm]
    return s


def now_val(slug):
    if not slug:
        return 0
    if slug in ktc_today:
        return ktc_today[slug].get("value", 0)
    return (ktc_all.get(slug) or {}).get("value", 0)


_hist = {}
_daily_vals = None


def history(slug):
    """Sorted [(yymmdd, value)] from the one-time page history plus every daily snapshot."""
    global _daily_vals
    if slug in _hist:
        return _hist[slug]
    if _daily_vals is None:
        _daily_vals = defaultdict(dict)
        for f in daily_files:
            d = f.stem[2:4] + f.stem[5:7] + f.stem[8:10]
            for s, e in json.loads(f.read_text()).items():
                _daily_vals[s][d] = e["value"]
    h = {}
    p = KTC / "hist" / f"{slug}.json"
    if p.exists():
        h.update(json.loads(p.read_text()))
    h.update(_daily_vals.get(slug, {}))
    _hist[slug] = sorted(h.items())
    return _hist[slug]


def val_at(slug, yymmdd):
    h = history(slug) if slug else []
    if not h:
        return None
    i = bisect.bisect_right([d for d, _ in h], yymmdd)
    if i:
        return h[i - 1][1]
    first_d, first_v = h[0]
    return first_v if int(first_d) - int(yymmdd) < 300 else None  # within ~3 months after


# drafted pick -> player
_draft_cache = {}


def drafted_player(season, rnd, orig_roster):
    key = (str(season), int(rnd), orig_roster)
    if key in _draft_cache:
        return _draft_cache[key]
    res = None
    so = season_by_id.get(str(season))
    if so:
        owner = so["r2o"].get(orig_roster)
        for dr in load(f"{season}/drafts.json", []) or []:
            if dr.get("status") != "complete":
                continue
            slot = (dr.get("draft_order") or {}).get(owner)
            for pk in load(f"{season}/draft_{dr['draft_id']}_picks.json", []) or []:
                if pk.get("round") == int(rnd) and pk.get("draft_slot") == slot:
                    res = pk.get("player_id")
    _draft_cache[key] = res
    return res


future_pick_seasons = sorted({int(n.split()[0]) for n in pick_slug})
next_draft = future_pick_seasons[0] if future_pick_seasons else None


def tier_for(orig_roster, season):
    """Early/Mid/Late for next year's picks from current standings; Mid for later years."""
    if not current or int(season) != next_draft:
        return "Mid"
    order = [t["roster_id"] for t in current["order"]]
    if orig_roster not in order:
        return "Mid"
    i, n = order.index(orig_roster), len(order)
    return "Late" if i < n / 3 else "Mid" if i < 2 * n / 3 else "Early"


def pick_then(season, rnd, yymmdd):
    nm = f"{season} Mid {ROUND_ORD.get(int(rnd), '')}"
    if nm in pick_slug_hist:
        v = val_at(pick_slug_hist[nm], yymmdd)
        if v is not None:
            return v, False
    for s in sorted({int(n.split()[0]) for n in pick_slug_hist if n.split()[0].isdigit()}):  # proxy: same round, nearest season KTC still tracks
        v = val_at(pick_slug_hist.get(f"{s} Mid {ROUND_ORD.get(int(rnd), '')}"), yymmdd)
        if v is not None:
            return v, True
    # trade predates every pick history KTC has: use the oldest value KTC has for this round
    oldest = [history(sl)[0] for n, sl in pick_slug_hist.items()
              if n.endswith(f" Mid {ROUND_ORD.get(int(rnd), '')}") and history(sl)]
    return (min(oldest)[1], True) if oldest else (None, True)


def pick_now(season, rnd, orig_roster):
    pid = drafted_player(season, rnd, orig_roster)
    if pid:
        return now_val(slug_for(pid)), pname(pid)
    nm = f"{season} {tier_for(orig_roster, season)} {ROUND_ORD.get(int(rnd), '')}"
    return now_val(pick_slug.get(nm)), None


ktc_out = None
if ktc_today:
    # ---- trade values then vs now
    scorecard = defaultdict(lambda: {"trades": 0, "then": 0, "now": 0})
    for tr in trades:
        yymmdd = tr["date"][2:4] + tr["date"][5:7] + tr["date"][8:10] if tr["date"] else None
        for side in tr["sides"]:
            then_t = now_t = 0
            est = False
            for p in side["players"]:
                slug = slug_for(p["id"])
                p["then"] = val_at(slug, yymmdd) if yymmdd else None
                p["now"] = now_val(slug)
                then_t += p["then"] or 0
                now_t += p["now"]
            for pk in side["picks"]:
                pk["then"], pk["est"] = pick_then(pk["season"], pk["round"], yymmdd) if yymmdd else (None, True)
                pk["now"], pk["became"] = pick_now(pk["season"], pk["round"], pk.get("orig_roster"))
                est = est or pk["est"]
                then_t += pk["then"] or 0
                now_t += pk["now"]
            side["then"], side["now"], side["est"] = then_t, now_t, est
        n = len(tr["sides"])
        for side in tr["sides"]:
            others = [s for s in tr["sides"] if s is not side]
            gave_then = sum(s["then"] for s in others) / max(n - 1, 1)
            gave_now = sum(s["now"] for s in others) / max(n - 1, 1)
            side["net_then"], side["net_now"] = round(side["then"] - gave_then), round(side["now"] - gave_now)
            sc = scorecard[side["owner"]]
            sc["trades"] += 1
            sc["then"] += side["net_then"]
            sc["now"] += side["net_now"]
        best = max(tr["sides"], key=lambda s: s["net_now"]) if tr["sides"] else None
        tr["winner_now"] = best["owner"] if best and best["net_now"] > 0 else None
        tr["swing"] = max((abs(s["net_now"] - s["net_then"]) for s in tr["sides"]), default=0)

    # ---- dynasty rankings
    rankings = []
    if current:
        traded = {(int(p["season"]), int(p["round"]), p["roster_id"]): p["owner_id"]
                  for p in load(f"{current['season']}/traded_picks.json", []) or []}
        rounds = int(current["league"].get("settings", {}).get("draft_rounds") or 4)
        owned = defaultdict(list)
        for s in future_pick_seasons:
            if s <= int(current["season"]):
                continue
            for r in range(1, rounds + 1):
                for t in current["teams"].values():
                    orig = t["roster_id"]
                    holder = traded.get((s, r, orig), orig)
                    owned[holder].append((s, r, orig))
        proj_avg = {}
        if sim and sim["weeks"]:
            for t in sim["teams"]:
                vals = [w["proj"].get(t["owner"]) for w in sim["weeks"] if w["proj"].get(t["owner"]) is not None]
                proj_avg[t["owner"]] = r2(sum(vals) / len(vals)) if vals else t["avg"]
        for oid, t in current["teams"].items():
            vals = {pid: now_val(slug_for(pid)) for pid in t["players"]}
            lineup = best_lineup_detail(vals, {p: ppos(p) for p in vals}, current["slots"])
            starters = sum(v for _, _, v in lineup)
            slot_label = {"SUPER_FLEX": "SF", "FLEX": "FLEX", "WRRB_FLEX": "W/R", "REC_FLEX": "W/T"}
            picks = []
            for (s, r, orig) in sorted(owned.get(t["roster_id"], [])):
                tier = tier_for(orig, s)
                v = now_val(pick_slug.get(f"{s} {tier} {ROUND_ORD[r]}"))
                own = "" if orig == t["roster_id"] else f" ({managers.get(current['r2o'].get(orig), {}).get('name', '?')})"
                picks.append({"label": f"{s} {tier} {ROUND_ORD[r]}{own}", "value": v})
            top = sorted(((pname(p), "/".join(sorted(ppos(p))), v) for p, v in vals.items() if v), key=lambda x: -x[2])
            pv, kv = sum(vals.values()), sum(p["value"] for p in picks)
            rankings.append({
                "owner": oid, "team": t["team"], "total": pv + kv, "players": pv, "starters": round(starters),
                "picks_value": kv, "picks": picks, "top": top[:8],
                "lineup": [[slot_label.get(sl, sl), pname(pid), "/".join(sorted(ppos(pid))), v] for sl, pid, v in lineup], "proj": proj_avg.get(oid) or (r2(sum(t["scores"]) / len(t["scores"])) if t["scores"] else None),
                "pf": r2(t["pf"]), "record": f"{t['w']}-{t['l']}" + (f"-{t['t']}" if t["t"] else ""),
            })
        rankings.sort(key=lambda x: -x["total"])

    # ---- daily team-value history (kept in git)
    tv_path = KTC / "team_values.json"
    tv = json.loads(tv_path.read_text()) if tv_path.exists() else {}
    tv[ktc_date] = {r["owner"]: r["total"] for r in rankings}
    tv_path.write_text(json.dumps(tv, separators=(",", ":"), sort_keys=True))

    ktc_out = {
        "date": ktc_date, "rankings": rankings, "team_history": tv,
        "scorecard": sorted(({"owner": o, **v} for o, v in scorecard.items()), key=lambda x: -x["now"]),
    }

# ---------------------------------------------------------------- write
out = {
    "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
    "league": {"name": current["name"] if current else "League", "seasons": [so["season"] for so in seasons],
               "current": current["season"] if current else None},
    "managers": managers,
    "seasons": season_out,
    "trophies": trophies,
    "alltime": alltime_rows,
    "h2h": h2h_out,
    "records": records,
    "waivers": waivers,
    "trades": trades,
    "trade_pairs": dict(pairs),
    "deposits": deposits,
    "sim": sim,
    "ktc": ktc_out,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, separators=(",", ":")))
print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(seasons)} seasons, {len(games)} games, "
      f"{len(trades)} trades, {len(waivers)} waiver entries")
