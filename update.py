#!/usr/bin/env python3
import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import urllib.request

UTILITIES = "https://www.cityofwalhalla.com/departments/public-utilities/"
NEWS = "https://www.cityofwalhalla.com/news/"
NEWS_RELEASE = "https://www.cityofwalhalla.com/about-walhalla/news-release/"
FB_WATER = "https://www.facebook.com/p/City-of-Walhalla-Water-Department-100066363410273/"

STATE = Path("status.json")
HTML = Path("index.html")
RECENT_AFTER = timedelta(hours=8)
UA = "WalhallaWaterMonitor/2.0 (+https://github.com/mapkar/WalhallaWaterWoes)"

WOE = [
    r"boil water advisory",
    r"water service disruption",
    r"water service notice",
    r"low water pressure",
    r"no water",
    r"pump station",
    r"mandatory water restriction",
    r"loss of water service",
    r"water outage",
    r"water line has been hit",
    r"line has been hit",
    r"hit and damaged by a contractor",
    r"contractor hit line",
    r"damaged by a contractor",
    r"water line break",
    r"line break",
    r"crews were dispatched",
    r"crews are currently on site",
    r"holding tanks",
    r"storage tanks",
]

LIFTED = [
    r"advisory has (officially )?been lifted",
    r"boil water advisory.{0,40}lifted",
    r"\blifted\b.{0,40}boil water",
    r"water service restored",
    r"service has been restored",
    r"safe for (normal use|consumption|drinking)",
]

LABELS = {
    "active": ("Active issue", "An interruption or advisory appears to be in effect."),
    "recent": ("Recent issue", "A problem was detected earlier. It has not been confirmed as still active."),
    "cleared": ("Cleared", "No current advisory or outage is indicated."),
}

PAGE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Days without Walhalla Water woes</title>
<style>
  :root { --bg:#f6f5f2; --ink:#161616; --muted:#5c5c5c; --line:#e4e1db; --ok:#1f6b3a; --warn:#8a5a00; --bad:#9b1c1c; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; font-family:ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--ink); display:grid; place-items:center; }
  main { width:min(38rem, calc(100% - 2.5rem)); text-align:center; }
  .kicker { font-size:.78rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); margin-bottom:1.5rem; }
  h1 { font-size:clamp(1.15rem,3vw,1.35rem); font-weight:550; margin:0 0 1.25rem; }
  .days { font-size:clamp(5rem,20vw,7.5rem); font-weight:620; letter-spacing:-.04em; line-height:.9; margin:0 0 .9rem; }
  .pill { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:.35rem .8rem; font-size:.8rem; letter-spacing:.04em; text-transform:uppercase; }
  .active { color:var(--bad); } .recent { color:var(--warn); } .cleared { color:var(--ok); }
  .blurb { color:var(--muted); font-size:.98rem; line-height:1.5; margin:1.15rem 0 1.2rem; }
  .excerpt { text-align:left; background:#fff; border:1px solid var(--line); border-radius:12px; padding:.9rem 1rem; font-size:.9rem; line-height:1.45; margin:0 0 1.4rem; }
  .excerpt .when { color:var(--muted); font-size:.78rem; letter-spacing:.04em; text-transform:uppercase; margin-bottom:.45rem; }
  .meta { border-top:1px solid var(--line); padding-top:1.1rem; color:var(--muted); font-size:.86rem; line-height:1.7; }
  a { color: inherit; }
</style>
</head>
<body>
<main>
  <div class=\"kicker\">Walhalla Water</div>
  <h1>Days without water woes</h1>
  <div class=\"days STATUS\">DAYS</div>
  <div class=\"pill STATUS\">TITLE</div>
  <p class=\"blurb\">BLURB</p>
  EXCERPT
  <div class=\"meta\">
    Last incident: LAST<br>
    CLEARED_LINE
    Last checked: CHECKED<br>
    Source: SOURCE<br>
    <a href=\"UTILITIES\">Official Public Utilities page</a><br>
    <a href=\"FBWATER\">Water Department Facebook</a>
  </div>
</main>
</body>
</html>
"""


def now_utc():
    return datetime.now(timezone.utc)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def strip_html(html):
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def parse_mdy(m, d, y):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def has_any(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


def announcement_blocks(text):
    blocks = []
    for m in re.finditer(
        r"(\d{1,2}/\d{1,2}/\d{4})\s*[~\u2013-]\s*(.+?)(?=\d{1,2}/\d{1,2}/\d{4}\s*[~\u2013-]|$)",
        text,
        re.S,
    ):
        raw_date, body = m.group(1), m.group(2).strip()
        mm, dd, yy = raw_date.split("/")
        dt = parse_mdy(mm, dd, yy)
        if dt:
            blocks.append((dt, body[:900]))
    return blocks


def analyze(html, url):
    text = strip_html(html)
    hits = []
    for dt, body in announcement_blocks(text):
        body_l = body.lower()
        woe = has_any(WOE, body_l)
        lifted = has_any(LIFTED, body_l)
        excerpt = re.sub(r"^(WATER SERVICE NOTICE|FOR IMMEDIATE RELEASE)\s+", "", body, flags=re.I)
        excerpt = re.sub(r"\s+", " ", excerpt).strip()
        hits.append({
            "date": dt,
            "woe": woe,
            "lifted": lifted and not (woe and "currently on site" in body_l),
            "excerpt": excerpt,
            "url": url,
        })
    return hits


def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decide(state, hits):
    last_detected = parse_dt(state.get("last_detected_at"))
    status = state.get("status") or ("active" if state.get("active") else "cleared")
    today = date.today()
    fresh = [h for h in hits if h["date"] >= today - timedelta(days=1)]
    active_hits = [h for h in fresh if h["woe"] and not h["lifted"]]
    lifted_hits = [h for h in fresh if h["lifted"]]

    if active_hits:
        return "active", now_utc(), max(active_hits, key=lambda h: h["date"])
    if lifted_hits:
        return "cleared", last_detected, max(lifted_hits, key=lambda h: h["date"])
    if status == "active":
        return "recent", last_detected, None
    if status == "recent":
        return "cleared", last_detected, None
    return "cleared", last_detected, None


def days_without(state):
    if state.get("status") in ("active", "recent"):
        return 0
    last = state.get("cleared_on") or state.get("last_woe")
    if not last:
        return 0
    return max(0, (date.today() - date.fromisoformat(last)).days)


def excerpt_html(state):
    ex = (state.get("excerpt") or "").strip()
    if not ex:
        return ""
    when = state.get("excerpt_date") or ""
    src = state.get("excerpt_source") or ""
    label = " / ".join(p for p in (when, src) if p)
    safe = ex.replace("&", "&").replace("<", "<").replace(">", ">")
    return f'<div class="excerpt"><div class="when">{label}</div>{safe}</div>'


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
        .replace("EXCERPT", excerpt_html(state))
        .replace("LAST", state.get("last_woe") or "none recorded")
        .replace("CLEARED_LINE", cleared_line)
        .replace("CHECKED", state.get("last_checked") or "-")
        .replace("SOURCE", state.get("source") or "city site")
        .replace("UTILITIES", UTILITIES)
        .replace("FBWATER", FB_WATER)
    )
    HTML.write_text(page, encoding="utf-8")


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    prev = json.dumps(state, sort_keys=True)
    notes = []
    hits = []
    for url in (UTILITIES, NEWS, NEWS_RELEASE):
        try:
            hits.extend(analyze(fetch(url), url))
        except Exception as e:
            notes.append(f"{url} failed: {e}")

    old_status = state.get("status") or ("active" if state.get("active") else "cleared")
    status, last_detected, best = decide(state, hits)

    if status == "active" and old_status != "active":
        state["last_woe"] = date.today().isoformat()
        state["cleared_on"] = None
        last_detected = now_utc()
    if status == "cleared" and old_status != "cleared":
        state["cleared_on"] = date.today().isoformat()

    if best:
        excerpt = re.sub(r"\s+", " ", best["excerpt"]).strip()
        if len(excerpt) > 420:
            excerpt = excerpt[:417] + "..."
        state["excerpt"] = excerpt
        state["excerpt_date"] = best["date"].isoformat()
        if "public-utilities" in best["url"]:
            state["excerpt_source"] = "Public Utilities announcements"
            state["source"] = "city utilities announcements + news pages"
        elif "news-release" in best["url"]:
            state["excerpt_source"] = "City news releases"
            state["source"] = "city news releases"
        else:
            state["excerpt_source"] = "City news"
            state["source"] = "city news"
    elif status == "cleared":
        state["excerpt"] = ""
        state["excerpt_date"] = None
        state["excerpt_source"] = None
        state["source"] = "city utilities announcements + news pages"

    state["status"] = status
    state["active"] = status == "active"
    state["last_detected_at"] = last_detected.isoformat() if last_detected else None
    state["last_checked"] = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    state["note"] = "; ".join(notes)
    state["facebook"] = FB_WATER
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    write_page(state)
    Path(".changed").write_text("1" if json.dumps(state, sort_keys=True) != prev else "0")
    print(status, json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
