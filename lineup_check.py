#!/usr/bin/env python3
"""Sunday lineup check: flag starters projected for zero (bye, Out, IR, empty slot) and the best bench fill-in.

Prints a plain-text report. Prints "NO GAMES" outside the fantasy season (regular season + playoffs).
Standard library only.
"""
import json
import urllib.request

LEAGUE_ID = "1350581422095622144"
BASE = "https://api.sleeper.app/v1"
PROJ = "https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular&position%5B%5D=QB&position%5B%5D=RB&position%5B%5D=WR&position%5B%5D=TE"
ELIG = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
        "FLEX": {"RB", "WR", "TE"}, "WRRB_FLEX": {"RB", "WR"}, "REC_FLEX": {"WR", "TE"},
        "SUPER_FLEX": {"QB", "RB", "WR", "TE"}}
OUT = {"Out", "IR", "PUP", "Sus", "NA", "COV"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "league-site/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "null")


def main():
    state = get(f"{BASE}/state/nfl")
    league = get(f"{BASE}/league/{LEAGUE_ID}")
    week = int(state.get("week") or 0)
    if state.get("season_type") != "regular" or state.get("season") != league["season"] or week < 1 or week > 17:
        print(f"NO GAMES (season_type={state.get('season_type')}, week={week})")
        return

    players = get(f"{BASE}/players/nfl")
    users = {u["user_id"]: u for u in get(f"{BASE}/league/{LEAGUE_ID}/users")}
    rosters = {r["roster_id"]: r for r in get(f"{BASE}/league/{LEAGUE_ID}/rosters")}
    matchups = get(f"{BASE}/league/{LEAGUE_ID}/matchups/{week}") or []
    proj = {}
    for row in get(PROJ.format(season=league["season"], week=week)) or []:
        pts = (row.get("stats") or {}).get("pts_half_ppr")
        if row.get("player_id") and pts is not None:
            proj[row["player_id"]] = float(pts)
    slots = [s for s in league["roster_positions"] if s in ELIG]

    def info(pid):
        p = players.get(pid) or {}
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or pid
        pos = set(p.get("fantasy_positions") or [p.get("position")])
        status = p.get("injury_status")
        pts = 0.0 if status in OUT else proj.get(pid, 0.0)
        return name, pos, status, pts, p.get("team")

    lines, flagged_teams = [], 0
    for m in sorted(matchups, key=lambda m: m["roster_id"]):
        r = rosters.get(m["roster_id"]) or {}
        u = users.get(r.get("owner_id"), {})
        team = (u.get("metadata") or {}).get("team_name") or u.get("display_name") or f"Roster {m['roster_id']}"
        starters = m.get("starters") or r.get("starters") or []
        locked = set(pid for pid, pts in (m.get("players_points") or {}).items() if pts)  # already played
        bench = [p for p in (r.get("players") or []) if p not in starters and p not in (r.get("reserve") or []) and p not in (r.get("taxi") or [])]
        used_bench, issues = set(), []
        for slot, pid in zip(slots, starters):
            if pid in locked:
                continue
            if pid in (None, "0", ""):
                why, name, pts = "EMPTY SLOT", "(empty)", 0.0
            else:
                name, pos, status, pts, nfl = info(pid)
                if pts > 0.5:
                    continue
                why = status if status in OUT else ("bye / no projection" if pts == 0 else f"proj {pts:.1f}")
            options = []
            for b in bench:
                if b in used_bench or b in locked:
                    continue
                bn, bpos, bstat, bpts, _ = info(b)
                if bpos & ELIG[slot] and bpts > 0.5:
                    options.append((bpts, bn, b))
            options.sort(reverse=True)
            if options:
                used_bench.add(options[0][2])
                fix = f"start {options[0][1]} (proj {options[0][0]:.1f})"
            else:
                fix = "no bench replacement; check waivers"
            issues.append(f"  - {slot.replace('SUPER_FLEX', 'SF')}: {name} ({why}) -> {fix}")
        if issues:
            flagged_teams += 1
            lines.append(f"{team} ({u.get('display_name', '?')}):")
            lines.extend(issues)
    print(f"WEEK {week} LINEUP CHECK: {flagged_teams} team(s) with zero-projection starters")
    print("\n".join(lines) if lines else "All starting lineups look set.")


if __name__ == "__main__":
    main()
