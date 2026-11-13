import json, re, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""

def jscripts(html):
    return re.findall(r'<script[^>]*id="([^"]+)"[^>]*type="application/json"', html)

for url in ["https://keeptradecut.com/trade-calculator?format=2",
            "https://keeptradecut.com/dynasty-rankings?page=1&filters=QB|WR|RB|TE|RDP&format=2",
            "https://keeptradecut.com/dynasty/trade-database?format=2"]:
    st, b = get(url)
    print(url, st, len(b), "json ids:", jscripts(b))
    for kw in ("joe-mixon", "amari-cooper", "Joe Mixon", "2024 Pick", "2024 Mid 1st", "2023 Mid 1st", "1.01"):
        i = b.find(kw)
        if i >= 0:
            print("   found", kw, ":", b[max(0, i - 150):i + 250].replace("\n", " "))
    for v in sorted(set(re.findall(r"var\s+(\w+)\s*=", b)))[:60]:
        print("   var", v)
# any api endpoints referenced in JS
st, b = get("https://keeptradecut.com/trade-calculator?format=2")
for u in sorted(set(re.findall(r'["\'](/(?:api|dynasty|trade)[^"\' ]{3,80})["\']', b)))[:60]:
    print("path", u)
for src in re.findall(r'<script[^>]+src="([^"]+)"', b)[:20]:
    print("script src", src)
