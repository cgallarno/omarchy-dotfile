#!/usr/bin/env python3
"""Waybar Codex usage module.

Codex rate limits are account-wide, but the OpenAI token that reads them
stays fresh on the box where Codex actually runs: the `hermes` LXC (153)
on `pathfinder`. So we SSH there and invoke hermes's own usage fetcher
(`agent.account_usage._fetch_codex_account_usage`), which refreshes the
token and calls the live `chatgpt.com/backend-api/wham/usage` endpoint —
the same data hermes's `/usage` shows.

Falls back to the last cached result (marked stale) when pathfinder is
unreachable (laptop off-network / VPN down).
"""
import json, os, base64, subprocess, datetime

CACHE = os.path.expanduser("~/.cache/waybar-codex-usage.json")
ICON = "\U000f09d1"  # nf-md-brain 󰧑
SSH_HOST = "pathfinder"
CID = "153"
REMOTE_PY = "/var/lib/hermes/.hermes/hermes-agent/venv/bin/python"

REMOTE_SCRIPT = r"""
import json
try:
    from agent.account_usage import _fetch_codex_account_usage
    snap = _fetch_codex_account_usage()
    out = {"plan": snap.plan, "windows": {}}
    for w in snap.windows:
        out["windows"][w.label] = {
            "used_percent": w.used_percent,
            "reset_at": w.reset_at.isoformat() if w.reset_at else None,
        }
    print(json.dumps(out))
except Exception as e:
    print(json.dumps({"error": type(e).__name__ + ": " + str(e)[:200]}))
"""


def fetch_remote():
    b64 = base64.b64encode(REMOTE_SCRIPT.encode()).decode()
    remote = (f"pct exec {CID} -- /usr/local/bin/as_hermes {REMOTE_PY} "
              f"-c \"import base64;exec(base64.b64decode('{b64}').decode())\"")
    out = subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         "-o", "StrictHostKeyChecking=accept-new", SSH_HOST, remote],
        text=True, timeout=25, stderr=subprocess.DEVNULL).strip()
    data = json.loads(out.splitlines()[-1])
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def fmt_reset(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso).astimezone()
        return dt.strftime("%a %H:%M")
    except Exception:
        return "?"


stale = False
try:
    data = fetch_remote()
    data["_ts"] = datetime.datetime.now().timestamp()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(data, open(CACHE, "w"))
except Exception:
    try:
        data = json.load(open(CACHE))
        stale = True
    except Exception:
        print(json.dumps({"text": f"{ICON} —",
                          "tooltip": "Codex usage unavailable\n(hermes/pathfinder unreachable)",
                          "class": "unavailable"}))
        raise SystemExit

win = data.get("windows") or {}


def used(label):
    w = win.get(label) or {}
    u = w.get("used_percent")
    return float(u) if u is not None else None


su, wu = used("Session"), used("Weekly")
sl = 100 - su if su is not None else None
wl = 100 - wu if wu is not None else None
lefts = [x for x in (sl, wl) if x is not None]
worst = min(lefts) if lefts else 100

cls = "normal"
if worst <= 10:
    cls = "critical"
elif worst <= 25:
    cls = "warning"
if stale:
    cls = "stale"

plan = data.get("plan") or "unknown plan"
sr = fmt_reset((win.get("Session") or {}).get("reset_at", ""))
wr = fmt_reset((win.get("Weekly") or {}).get("reset_at", ""))
tip = f"Codex — {plan}\n"
tip += f"Session (5h):  {sl:.0f}% left  ({su:.0f}% used)\n   resets {sr}\n" if sl is not None else "Session: unavailable\n"
tip += f"Week:  {wl:.0f}% left  ({wu:.0f}% used)\n   resets {wr}" if wl is not None else "Week: unavailable"
if stale:
    age = data.get("_ts")
    when = datetime.datetime.fromtimestamp(age).strftime("%a %H:%M") if age else "?"
    tip += f"\n(cached — hermes unreachable, as of {when})"

s_txt = f"{sl:.0f}" if sl is not None else "—"
w_txt = f"{wl:.0f}" if wl is not None else "—"
print(json.dumps({"text": f"{ICON} {s_txt}/{w_txt}",
                  "tooltip": tip, "class": cls, "percentage": int(worst)}))
