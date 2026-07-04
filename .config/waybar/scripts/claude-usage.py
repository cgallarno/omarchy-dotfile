#!/usr/bin/env python3
"""Waybar Claude Code usage module.

Queries Anthropic's first-party OAuth usage endpoint (the same data the
in-app `/usage` command shows) using the local Claude Code OAuth token.
Shows % of the 5-hour session and 7-day windows remaining.
"""
import json, os, urllib.request, datetime

CRED = os.path.expanduser("~/.claude/.credentials.json")
CACHE = os.path.expanduser("~/.cache/waybar-claude-usage.json")
ICON = "\U000f06a9"  # nf-md-robot_outline 󰚩


def fmt_reset(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%a %H:%M")
    except Exception:
        return "?"


def load_live():
    d = json.load(open(CRED))
    o = d.get("claudeAiOauth", d)
    tok = o.get("accessToken")
    if not tok:
        raise RuntimeError("no accessToken")
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {tok}",
                 "anthropic-beta": "oauth-2025-04-20",
                 "User-Agent": "claude-cli"})
    data = json.load(urllib.request.urlopen(req, timeout=8))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(data, open(CACHE, "w"))
    return data


try:
    try:
        data = load_live()
    except Exception:
        data = json.load(open(CACHE))  # fall back to last good result

    s = data.get("five_hour") or {}
    w = data.get("seven_day") or {}
    su = s.get("utilization") or 0
    wu = w.get("utilization") or 0
    sl, wl = 100 - su, 100 - wu
    worst = min(sl, wl)

    cls = "normal"
    if worst <= 10:
        cls = "critical"
    elif worst <= 25:
        cls = "warning"

    tip = (f"Claude Code\n"
           f"Session (5h):  {sl:.0f}% left  ({su:.0f}% used)\n"
           f"   resets {fmt_reset(s.get('resets_at', ''))}\n"
           f"Week (7d):  {wl:.0f}% left  ({wu:.0f}% used)\n"
           f"   resets {fmt_reset(w.get('resets_at', ''))}")
    print(json.dumps({"text": f"{ICON} {sl:.0f}/{wl:.0f}",
                      "tooltip": tip, "class": cls, "percentage": int(worst)}))
except Exception:
    print(json.dumps({"text": f"{ICON} —",
                      "tooltip": "Claude usage unavailable\n(run claude once to refresh auth)",
                      "class": "unavailable"}))
