import json
from collections import Counter
d = json.loads(open("site/data.json").read())
M = d["managers"]; me = [k for k, v in M.items() if v["name"] == "bspm27"][0]
reg = d["h2h"]["reg"]
print("bspm27 regular-season games by opponent:", sorted((M[k.split("|")[1]]["name"], v["w"] + v["l"] + v["t"]) for k, v in reg.items() if k.startswith(me + "|")))
print("distribution of games per pair (all pairs):", Counter(v["w"] + v["l"] + v["t"] for v in reg.values()))
