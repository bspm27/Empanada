import json
from pathlib import Path
d = json.loads(Path("site/data.json").read_text())
M = d["managers"]; nm = {v["name"]: k for k, v in M.items()}
me = nm["bspm27"]
for s in d["seasons"]:
    print(s["season"], "teams:", sorted(M[r["owner"]]["name"] for r in s["standings"]))
for opp in ("awillis7", "AudiHari"):
    for k in ("all", "reg", "po"):
        print(opp, k, d["h2h"][k].get(f"{me}|{nm[opp]}"))
