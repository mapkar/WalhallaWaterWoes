#!/usr/bin/env python3
import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import urllib.request

URL = "https://www.cityofwalhalla.com/departments/public-utilities/"
STATE = Path("status.json")
HTML = Path("index.html")
RECENT_AFTER = timedelta(hours=6)

WOE = [
    r"boil water advisory",
    r"water service disruption",
    r"low water pressure",
    r"pump station",
    r"mandatory water restriction",
    r"loss of water service",
    r"water outage",
]

LABELS = {
    "active": ("Active issue", "An interruption or advisory appears to be in effect."),
    "recent": ("Recent issue", "A problem was detected earlier. It has not been confirmed as still active."),
    "cleared": ("Cleared", "No current advisory or outage is indicated."),
}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Days without Walhalla Water woes</title>
<style>
  :root {
    --bg: #f6f5f2;
    --ink: #161616;
    --muted: #5c5c5c;
    --line: #e4e1db;
    --ok: #1f6b3a;
    --warn: #8a5a00;
    --bad: #9b1c1c;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    font-family: ui-sans-serif, system-ui, sans-serif;
    background: var(--bg);
    color: var(--ink);
    display: grid;
    place-items: center;
  }
  main {
    width: min(34rem, calc(100% - 2.5rem));
    text-align: center;
  }
  .kicker {
    font-size: .78rem;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 1.5rem;
  }
  h1 {
    font-size: clamp(1.15rem, 3vw, 1.35rem);
    font-weight: 550;
    margin: 0 0 1.25rem;
  }
  .days {
    font-size: clamp(5rem, 20vw, 7.5rem);
    font-weight: 620;
    letter-spacing: -.04em;
    line-height: .9;
    margin: 0 0 .9rem;
  }
  .pill {
    display: inline-block;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: .35rem .8rem;
    font-size: .8rem;
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .active { color: var(--bad); }
  .recent { color: var(--warn); }
  .cleared { color: var(--ok); }
  .blurb {
    color: var(--muted);
    font-size: .98rem;
    line-height: 1.5;
    margin: 1.15rem 0 2rem;
  }
  .meta {
    border-top: 1px solid var(--line);
    padding-top: 1.1rem;
    color: var(--muted);
    font-size: .86rem;
    line-height: 1.7;
  }
  a { color: inherit; }
</style>
</head>
<body>
<main>
  <div class="kicker">Walhalla Water</div>
  <h1>Days without water woes</h1>
  <div class="days STATUS">DAYS</div>
  <div class="pill STATUS">TITLE</div>
  <p class="blurb">BLURB</p>
  <div class="meta">
    Last incident: LAST<br>
    CLEARED_LINE
    Last checked: CHECKED<br>
    <a href="OFFICIAL">Official Public Utilities page</a>
  </div>
</main>
</body>
</html>
"""


def now_utc():
    return datetime.now(timezone.utc)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "WalhallaWaterMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def parse(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip().lower()
    head = text[:5000]
    has_woe = any(re.search(k, head) for k in WOE)
    lifted = bool(re.search(r"\blifted\b", head)) and "boil water" in head
    today = date.today()
    fresh_date = (
        today.strftime("%B").lower() in head
        and str(today.day) in head
        and str(today.year) in head
    )
    return has_woe, lifted, fresh_date


def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decide(state, has_woe, lifted, fresh_date):
    last_detected = parse_dt(state.get("last_detected_at"))
    status = state.get("status") or ("active" if state.get("active") else "cleared")

    if lifted and not (has_woe and fresh_date and not lifted):
        return "cleared", last_detected

    if has_woe and fresh_date and not lifted:
        return "active", now_utc()

    if status == "active":
        if last_detected and now_utc() - last_detected >= RECENT_AFTER:
            return "recent", last_detected
        if has_woe and not lifted:
            return "active", last_detected or now_utc()
        return "recent", last_detected

    if status == "recent":
        if has_woe and not lifted:
            return "recent", last_detected
        return "cleared", last_detected

    if has_woe and not lifted:
        return "recent", last_detected or now_utc()
    return "cleared", last_detected


def days_without(state):
    if state.get("status") in ("active", "recent"):
        return 0
    last = state.get("cleared_on") or state.get("last_woe")
    if not last:
        return 0
    return max(0, (date.today() - date.fromisoformat(last)).days)


def write_page(state):
    status = state.get("status", "cleared")
    title, blurb = LABELS[status]
    cleared = state.get("cleared_on")
    cleared_line = ("Cleared: " + cleared + "<br>") if cleared else ""
    page = (
        PAGE.replace("STATUS", status)
        .replace("DAYS", str(days_without(state)))
        .replace("TITLE", title)
        .replace("BLURB", blurb)
        .replace("LAST", state.get("last_woe") or "none recorded")
        .replace("CLEARED_LINE", cleared_line)
        .replace("CHECKED", state.get("last_checked") or "-")
        .replace("OFFICIAL", URL)
    )
    HTML.write_text(page, encoding="utf-8")


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    prev = json.dumps(state, sort_keys=True)
    note = ""
    try:
        has_woe, lifted, fresh_date = parse(fetch())
    except Exception as e:
        has_woe, lifted, fresh_date = False, False, False
        note = "fetch failed: " + str(e)

    old_status = state.get("status") or ("active" if state.get("active") else "cleared")
    status, last_detected = decide(state, has_woe, lifted, fresh_date)

    if status == "active" and old_status != "active":
        state["last_woe"] = date.today().isoformat()
        state["cleared_on"] = None
        last_detected = now_utc()

    if status == "cleared" and old_status != "cleared":
        state["cleared_on"] = date.today().isoformat()

    state["status"] = status
    state["active"] = status == "active"
    state["last_detected_at"] = last_detected.isoformat() if last_detected else None
    state["last_checked"] = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    state["note"] = note

    STATE.write_text(json.dumps(state, indent=2) + "\n")
    write_page(state)
    changed = json.dumps(state, sort_keys=True) != prev
    Path(".changed").write_text("1" if changed else "0")
    print(status, state)


if __name__ == "__main__":
    main()