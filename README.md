# League Site

League history, records and playoff odds for our Sleeper dynasty league, built from the Sleeper API and hosted on GitHub Pages.

## How it works
- `fetch.py` pulls Sleeper data into `data/raw/` (past seasons are cached between runs)
- `build.py` turns that into `site/data.json`
- `site/index.html` is the page; playoff odds are simulated in the browser
- `.github/workflows/update.yml` runs both scripts and publishes the page every morning, Tuesday night after MNF, on every push, and on demand from the Actions tab ("Run workflow")

## One-time GitHub setup
In the repo: Settings > Pages > Source: **GitHub Actions**.

## Run locally (optional)

    python3 fetch.py && python3 build.py
    cd site && python3 -m http.server 8000

## Change settings
Payouts and buy-in are at the top of `build.py`; the league ID is at the top of `fetch.py`.
