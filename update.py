#!/usr/bin/env python3
import json, re
from datetime import date, datetime, timezone
from pathlib import Path
import urllib.request

URL = "https://www.cityofwalhalla.com/departments/public-utilities/"
STATE = Path("status.json")
HTML = Path("index.html")

KEYWORDS = [
    r"boil water advisory",
    r"water service disruption",
    r"low water pressure",
    r"pump station",
    r"mandatory water restriction",
    r"loss of water service",
    r"water outage",
]

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "WalhallaWaterMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")

def detect(html: str) -> bool:
    text = re.sub(r"<[^>]+>", " ", html).lower()
    has = any(re.search(k, text) for k in KEYWORDS)
    # Recent lift at the top of announcements = not active
    head = text[:4000]
    if "lifted" in head and "boil water" in head and "august 18" in head:
        return False
    return has

def days_without(last_woe):
    if not last_woe:
        return 0
    return (date.today() - date.fromisoformat(last_woe)).days

def write_page(state):
    days = days_without(state.get("last_woe"))
    active = state.get("active", False)
    color = "#c0392b" if active else "#27ae60"
    status = "ACTIVE ISSUE" if active else "All clear"
    HTML.write_text(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Days without Walhalla Water woes</title>
<style>
body{{font-family:system-ui,sans-serif;text-align:center;padding:2rem;background:#f7f7f5}}
.days{{font-size:5rem;font-weight:700;color:{color};margin:.4rem 0}}
.status{{color:{color};font-size:1.2rem}}
.meta{{color:#555;margin-top:2rem;font-size:.95rem}}
a{{color:#1d6fa5}}
</style></head>
<body>
<h1>Days without Walhalla Water woes</h1>
<div class="days">{days}</div>
<div class="status">{status}</div>
<div class="meta">
Last incident: {state.get("last_woe") or "none recorded"}<br>
Last checked: {state.get("last_checked")}<br>
<a href="{URL}">Official Walhalla Public Utilities page</a>
</div>
</body></html>
""", encoding="utf-8")

def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    prev = json.dumps(state, sort_keys=True)
    try:
        html = fetch()
        active = detect(html)
        note = ""
    except Exception as e:
        active = state.get("active", False)
        note = f"fetch failed: {e}"

    if active and not state.get("active"):
        state["last_woe"] = date.today().isoformat()
    state["active"] = active
    state["last_checked"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    state["note"] = note

    STATE.write_text(json.dumps(state, indent=2) + "\n")
    write_page(state)

    changed = json.dumps(state, sort_keys=True) != prev
    print("changed" if changed else "unchanged", state)
    # GitHub Action uses this to decide whether to commit
    Path(".changed").write_text("1" if changed else "0")

if __name__ == "__main__":
    main()