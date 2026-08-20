#!/usr/bin/env python3
import json, re
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

def now_utc():
    return datetime.now(timezone.utc)

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "WalhallaWaterMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")

def parse(html: str):
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
    days = days_without(state)
    labels = {
        "active": ("Active issue", "An interruption or advisory appears to be in effect."),
        "recent": ("Recent issue", "A problem was detected earlier. It has not been confirmed as still active."),
        "cleared": ("Cleared", "No current advisory or outage is indicated."),
    }
    title, blurb = labels[status]
    HTML.write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Days without Walhalla Water woes</title>
<style>
  :root {{
    --bg: #f6f5f2;
    --ink: #161616;
    --muted: #5c5c5c;
    --line: #e4e1db;
    --ok: #1f6b3