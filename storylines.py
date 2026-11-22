#!/usr/bin/env python3
"""Weekly storylines fact sheet for the Sunday lineup check.

Reads site/data.json (run fetch.py and build.py first) and prints the facts
behind this week's storylines: playoff picture, the matchups with the biggest
playoff swing, clinch/elimination scenarios, and records within reach.
The lineup-check agent turns this into a short blurb. Standard library only.
"""
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
N = 20000


def rec(t):
    return f"{t['w']}-{t['l']}" + (f"-{t['t']}" if t.get("t") else "")


def streak(results):
    if not results:
        return "", 0
    k, n = results[-1], 0
    for r in reversed(results):
        if r != k:
            break
        n += 1
    return k, n


def simulate(S, rng):
    """Monte Carlo of the rest of the regular season, mirroring the site's odds table."""
    T = S["teams"]
    idx = {t["owner"]: i for i, t in enumerate(T)}
    P = S["playoff_teams"]
    byes = 2 if P == 6 else 0
    n = len(T)
    this_week = S["weeks"][0]["games"] if S["weeks"] else []
    made = [0] * n
    bye = [0] * n
    seed1 = [0] * n
    # cond[(game_index, winner_owner)][team] = (playoff count, sims)
    cond = defaultdict(lambda: [0] * n)
    cond_n = defaultdict(int)

    def mean(wk, o):
        p = (wk.get("proj") or {}).get(o)
        return p if p and p > 0 else (T[idx[o]]["avg"] or 100)

    for _ in range(N):
        W = [t["w"] + 0.5 * t["t"] for t in T]
        PF = [t["pf"] for t in T]
        first = []
        for wi, wk in enumerate(S["weeks"]):
            for a, b in wk["games"]:
                ia, ib = idx[a], idx[b]
                sa = max(0, mean(wk, a) + T[ia]["sd"] * rng.gauss(0, 1))
                sb = max(0, mean(wk, b) + T[ib]["sd"] * rng.gauss(0, 1))
                PF[ia] += sa
                PF[ib] += sb
                if sa > sb:
                    W[ia] += 1
                elif sb > sa:
                    W[ib] += 1
                else:
                    W[ia] += 0.5
                    W[ib] += 0.5
                if wi == 0:
                    first.append(a if sa >= sb else b)
        order = sorted(range(n), key=lambda i: (-W[i], -PF[i]))
        inn = set(order[:P])
        for r, i in enumerate(order):
            if r < P:
                made[i] += 1
            if r < byes:
                bye[i] += 1
            if r == 0:
                seed1[i] += 1
        for gi, w in enumerate(first):
            cond_n[(gi, w)] += 1
            row = cond[(gi, w)]
            for i in inn:
                row[i] += 1

    odds = {t["owner"]: made[i] / N for i, t in enumerate(T)}
    byeo = {t["owner"]: bye[i] / N for i, t in enumerate(T)}
    top = {t["owner"]: seed1[i] / N for i, t in enumerate(T)}
    swings = []
    for gi, (a, b) in enumerate(this_week):
        res = {}
        for w in (a, b):
            c = cond_n[(gi, w)] or 1
            res[w] = {o: cond[(gi, w)][idx[o]] / c for o in idx}
        swing = {o: res[a][o] - res[b][o] for o in idx}
        total = sum(abs(v) for v in swing.values())
        swings.append({"a": a, "b": b, "if_a": res[a], "if_b": res[b], "swing": swing, "total": total})
    return odds, byeo, top, swings


def pct(x):
    if x >= 0.995:
        return "100%" if x == 1 else ">99%"
    if x <= 0.005:
        return "0%" if x == 0 else "<1%"
    return f"{round(x * 100)}%"


def main():
    D = json.loads((ROOT / "site" / "data.json").read_text())
    S = D.get("sim")
    R = D.get("records") or {}
    if not S or not S.get("weeks"):
        print("STORYLINES: regular season is over or not started; no playoff-race sim this week.")
        cur = next((s for s in D.get("seasons", []) if s["season"] == D["league"].get("current")), None)
        if cur:
            print("Final regular-season standings (top 8):")
            for i, r in enumerate(cur["standings"][:8], 1):
                print(f"  {i}. {r.get('team')} {r.get('record', '')}")
        return

    T = {t["owner"]: t for t in S["teams"]}
    name = lambda o: T[o]["team"] if o in T else o  # noqa: E731
    wk = S["weeks"][0]
    week = wk["week"]
    weeks_left = len(S["weeks"])
    total_weeks = S["playoff_week_start"] - 1
    P = S["playoff_teams"]
    odds, byeo, top, swings = simulate(S, random.Random(week))

    print(f"STORYLINES WEEK {week} ({weeks_left} regular-season week(s) left incl. this one; top {P} make playoffs, "
          f"{'top 2 get byes' if P == 6 else 'no byes'})")

    order = sorted(S["teams"], key=lambda t: (-(t["w"] + 0.5 * t["t"]), -t["pf"]))
    print("\nSTANDINGS (record, PF, playoff odds / bye odds / #1 seed odds, current streak):")
    for i, t in enumerate(order, 1):
        k, n = streak(t.get("results", ""))
        o = t["owner"]
        tag = " (lock in every sim)" if odds[o] == 1 else " (out in every sim)" if odds[o] == 0 else ""
        line = "  -- playoff line --" if i == P + 1 else None
        if line:
            print(line)
        print(f"  {i}. {t['team']} {rec(t)}, {t['pf']:.1f} PF, odds {pct(odds[o])} / {pct(byeo[o])} / {pct(top[o])}, "
              f"{k}{n}{tag}")

    print("\nTHIS WEEK'S MATCHUPS, ranked by total playoff-odds swing:")
    for s in sorted(swings, key=lambda x: -x["total"]):
        a, b = s["a"], s["b"]
        pa, pb = (wk.get("proj") or {}).get(a), (wk.get("proj") or {}).get(b)
        proj = f" (proj {pa:.1f}-{pb:.1f})" if pa and pb else ""
        print(f"  {name(a)} {rec(T[a])} vs {name(b)} {rec(T[b])}{proj}: total swing {s['total'] * 100:.0f} pts")
        for o in (a, b):
            print(f"     {name(o)}: {pct(s['if_a'][o])} if {name(a)} wins, {pct(s['if_b'][o])} if {name(b)} wins")
        others = sorted(((abs(v), o) for o, v in s["swing"].items() if o not in (a, b) and abs(v) >= 0.05), reverse=True)[:2]
        for _, o in others:
            print(f"     also moves {name(o)}: {pct(s['if_a'][o])} vs {pct(s['if_b'][o])}")

    print("\nCLINCH / ELIMINATION SCENARIOS THIS WEEK:")
    found = False
    for s in swings:
        for o in (s["a"], s["b"]):
            win = s["if_a"][o] if o == s["a"] else s["if_b"][o]
            loss = s["if_b"][o] if o == s["a"] else s["if_a"][o]
            if 0 < odds[o] < 1 and win >= 0.999:
                print(f"  {name(o)} clinches a playoff spot with a win (sim {pct(win)})")
                found = True
            if 0 < odds[o] < 1 and loss <= 0.001:
                print(f"  {name(o)} is eliminated with a loss")
                found = True
    if not found:
        print("  none")

    print("\nRECORD WATCH (league history; Points Palooza weeks count for records):")
    found = False
    hw = (R.get("high_week") or [None])[0]
    if hw and wk.get("proj"):
        best = max(wk["proj"].items(), key=lambda kv: kv[1] or 0)
        if best[1] and best[1] >= 0.8 * hw["pts"]:
            print(f"  Single-week high is {hw['pts']} ({hw['team']}, {hw['season']} wk {hw['week']}); "
                  f"top projection this week is {name(best[0])} at {best[1]:.1f}")
            found = True
    for kind, key, label in (("W", "win_streaks", "win"), ("L", "loss_streaks", "losing")):
        rec_s = (R.get(key) or [None])[0]
        if not rec_s:
            continue
        for t in S["teams"]:
            k, n = streak(t.get("results", ""))
            if k == kind and n >= max(3, rec_s["len"] - 1):
                status = "would set" if n + 1 > rec_s["len"] else "would tie" if n + 1 == rec_s["len"] else "extends"
                print(f"  {t['team']} on a {n}-game {label} streak; league record is {rec_s['len']} "
                      f"({rec_s['team']}, {rec_s['season']}); another {'W' if kind == 'W' else 'L'} {status} the record")
                found = True
    played = [t for t in S["teams"] if t["w"] + t["l"] + t["t"]]
    pace = {t["owner"]: t["pf"] / (t["w"] + t["l"] + t["t"]) * total_weeks for t in played}
    for key, pick, cmp, label in (("most_pf", max, 1, "most points in a season"),
                                  ("fewest_pf", min, -1, "fewest points in a season")):
        rs = (R.get(key) or [None])[0]
        if not rs or not pace:
            continue
        o = pick(pace, key=pace.get)
        if (pace[o] - rs["pf"]) * cmp > 0:
            print(f"  {name(o)} on pace for {pace[o]:.0f} PF vs the {label} record {rs['pf']} ({rs['team']}, {rs['season']})")
            found = True
    bs = (R.get("best_seasons") or [None])[0]
    if bs and played:
        t = max(played, key=lambda t: ((t["w"] + 0.5 * t["t"]) / (t["w"] + t["l"] + t["t"]), t["pf"]))
        if t["l"] < bs["l"] or (t["l"] == bs["l"] and t["w"] + weeks_left > bs["w"]):
            print(f"  {t['team']} ({rec(t)}) can still beat the best-record mark {bs['w']}-{bs['l']} "
                  f"({bs['team']}, {bs['season']})")
            found = True
    if not found:
        print("  none")


if __name__ == "__main__":
    main()
