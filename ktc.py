#!/usr/bin/env python3
"""Pull KeepTradeCut superflex values.

- data/ktc/daily/YYYY-MM-DD.json : today's value for every ranked player and pick (kept in git, builds trend history)
- data/ktc/hist/<slug>.json      : full daily history for players/picks that appear in league trades
                                   (fetched once per slug, then daily snapshots take over)
KTC has no API, so this reads the JSON embedded in its pages. Requests are spaced out and cached.
"""
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
KTC = ROOT / "data" / "ktc"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
TRADE_DB = "https://keeptradecut.com/dynasty/trade-database?format=2"
RANKINGS = "https://keeptradecut.com/dynasty-rankings?page=0&filters=QB|WR|RB|TE|RDP&format=2"
PLAYER_URL = "https://keeptradecut.com/dynasty-rankings/players/{}"
MAX_NEW_HISTORIES = 250


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def script_json(html, sid):
    m = re.search(rf'<script[^>]*id="{sid}"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def norm(name):
    n = re.sub(r"[^a-z ]", "", (name or "").lower().replace("-", " "))
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def main():
    print("Fetching KTC superflex rankings")
    arr = script_json(get(RANKINGS), "ktc-players")
    if not arr:
        sys.exit("KTC page layout changed: ktc-players not found")
    today = {}
    for p in arr:
        sv = p.get("superflexValues") or {}
        today[p["slug"]] = {"name": p["playerName"], "pos": p["position"], "team": p.get("team"),
                            "value": sv.get("value", 0), "rank": sv.get("rank")}
    (KTC / "daily").mkdir(parents=True, exist_ok=True)
    out = KTC / "daily" / f"{date.today().isoformat()}.json"
    out.write_text(json.dumps(today, separators=(",", ":"), sort_keys=True))
    print(f"  {len(today)} entries -> {out.name}")

    # full player list (includes retired / low-ranked players and possibly past picks) for slug lookups
    print("Fetching KTC player search list")
    allp = {}
    try:
        html = get(TRADE_DB)
        m = re.search(r"var\s+allPlayerSearchValues\s*=\s*(\[.*?\]);\s*\n", html, re.S)
        if m:
            for p in json.loads(m.group(1)):
                allp[p["slug"]] = {"name": p["playerName"], "pos": p.get("position"), "value": p.get("superflexValue") or 0}
    except Exception as e:  # noqa: BLE001
        print("  search list failed:", e)
    if allp:
        (KTC / "all.json").write_text(json.dumps(allp, separators=(",", ":"), sort_keys=True))
    picks_all = sorted(e["name"] for e in allp.values() if (e["name"] or "")[:2] == "20")
    print(f"  {len(allp)} entries; pick-like names: {len(picks_all)} e.g. {picks_all[:12]}")

    # which slugs need full history: every player who moved in a league trade, plus Mid-tier picks
    players = json.loads((RAW / "players.json").read_text())
    by_key = {}
    for src in (today, allp):
        for slug, e in src.items():
            if e["pos"] != "RDP" and (e["name"] or "")[:2] != "20":
                by_key.setdefault((norm(e["name"]), e["pos"]), slug)
    need = {slug for src in (today, allp) for slug, e in src.items()
            if (e["name"] or "")[:2] == "20" and " Mid " in e["name"]}
    seasons = json.loads((RAW / "seasons.json").read_text())
    for s in seasons:
        for t in json.loads((RAW / s / "transactions.json").read_text()):
            if t.get("type") != "trade" or t.get("status") != "complete":
                continue
            for pid in (t.get("adds") or {}):
                pl = players.get(pid) or {}
                slug = by_key.get((norm(pl.get("full_name")), pl.get("position")))
                if slug:
                    need.add(slug)
    (KTC / "hist").mkdir(parents=True, exist_ok=True)
    missing = sorted(s for s in need if not (KTC / "hist" / f"{s}.json").exists())
    print(f"Histories: {len(need)} needed, {len(missing)} to fetch")
    for i, slug in enumerate(missing[:MAX_NEW_HISTORIES]):
        try:
            sf = script_json(get(PLAYER_URL.format(slug)), "pd-superflex") or {}
            hist = {h["d"]: h["v"] for h in sf.get("overallValue") or []}
            (KTC / "hist" / f"{slug}.json").write_text(json.dumps(hist, separators=(",", ":")))
        except Exception as e:  # noqa: BLE001
            print(f"  {slug}: {e}")
        time.sleep(1.0)
        if i % 25 == 24:
            print(f"  {i + 1}/{len(missing)}")
    print("Done")


if __name__ == "__main__":
    main()
