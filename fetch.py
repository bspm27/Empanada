#!/usr/bin/env python3
"""Pull everything the league site needs from the Sleeper API into data/raw/.

Completed seasons are cached forever. The current season, NFL state, the
player database and projections are refreshed on every run.
Standard library only, so it runs on a stock Mac.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

LEAGUE_ID = "1382898036849528832"
BASE = "https://api.sleeper.app/v1"
PROJ_BASE = "https://api.sleeper.app/projections/nfl"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
MAX_WEEK = 18


def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "league-site/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8") or "null")
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise RuntimeError(f"GET {url} failed: {e}") from e
            time.sleep(1.5 * (attempt + 1))
    return None


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)


def fetch_season(league_id, force):
    league = get(f"{BASE}/league/{league_id}")
    season = league["season"]
    d = RAW / season
    complete = league.get("status") == "complete"
    marker = d / "_complete"
    if complete and marker.exists() and not force:
        print(f"  {season}: cached")
        return league
    print(f"  {season}: fetching ({league.get('status')})")
    save(d / "league.json", league)
    save(d / "users.json", get(f"{BASE}/league/{league_id}/users"))
    save(d / "rosters.json", get(f"{BASE}/league/{league_id}/rosters"))
    for w in range(1, MAX_WEEK + 1):
        save(d / f"matchups_{w}.json", get(f"{BASE}/league/{league_id}/matchups/{w}") or [])
    txns = {}
    for w in range(0, MAX_WEEK + 1):
        for t in get(f"{BASE}/league/{league_id}/transactions/{w}") or []:
            txns[t["transaction_id"]] = t
    save(d / "transactions.json", list(txns.values()))
    save(d / "winners_bracket.json", get(f"{BASE}/league/{league_id}/winners_bracket") or [])
    save(d / "losers_bracket.json", get(f"{BASE}/league/{league_id}/losers_bracket") or [])
    save(d / "traded_picks.json", get(f"{BASE}/league/{league_id}/traded_picks") or [])
    drafts = get(f"{BASE}/league/{league_id}/drafts") or []
    save(d / "drafts.json", drafts)
    for dr in drafts:
        save(d / f"draft_{dr['draft_id']}_picks.json", get(f"{BASE}/draft/{dr['draft_id']}/picks") or [])
    if complete:
        marker.write_text("1")
    return league


def fetch_projections(season, weeks):
    pos = "&".join(f"position%5B%5D={p}" for p in ("QB", "RB", "WR", "TE"))
    for w in weeks:
        url = f"{PROJ_BASE}/{season}/{w}?season_type=regular&{pos}"
        try:
            save(RAW / "projections" / f"{season}_{w}.json", get(url) or [])
        except RuntimeError as e:
            print(f"  projections week {w} unavailable: {e}")


def main():
    force = "--force" in sys.argv
    print("Fetching NFL state")
    state = get(f"{BASE}/state/nfl")
    save(RAW / "state.json", state)

    print("Fetching seasons")
    seasons = []
    lid = LEAGUE_ID
    while lid and lid != "0":
        league = fetch_season(lid, force)
        seasons.append(league["season"])
        lid = league.get("previous_league_id")
    save(RAW / "seasons.json", sorted(seasons))

    players_path = RAW / "players.json"
    if force or not players_path.exists() or time.time() - players_path.stat().st_mtime > 20 * 3600:
        print("Fetching player database (~5 MB)")
        save(players_path, get(f"{BASE}/players/nfl"))

    current = json.loads((RAW / max(seasons) / "league.json").read_text())
    if current.get("status") == "in_season" and state.get("season") == current["season"]:
        start = int(current["settings"].get("playoff_week_start", 15))
        week = max(int(state.get("week") or 1), 1)
        print(f"Fetching projections weeks {week}-{start - 1}")
        fetch_projections(current["season"], range(week, start))
    print("Done")


if __name__ == "__main__":
    main()
