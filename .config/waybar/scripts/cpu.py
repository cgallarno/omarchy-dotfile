#!/usr/bin/env python3
"""Waybar CPU module.

Computes aggregate CPU usage from /proc/stat deltas (previous sample
persisted between polls) and renders an nvtop-style utilization
sparkline plus the current percentage.
"""
import os, json, time

STATE = os.path.expanduser("~/.cache/waybar-cpu-stat")
HIST = os.path.expanduser("~/.cache/waybar-cpu-hist")
BLOCKS = "▁▂▃▄▅▆▇█"
N = 10


def read_stat():
    with open("/proc/stat") as f:
        v = list(map(int, f.readline().split()[1:]))
    idle = v[3] + (v[4] if len(v) > 4 else 0)  # idle + iowait
    return sum(v), idle


def spark(vals):
    return "".join(BLOCKS[min(7, max(0, round(v / 100 * 7)))] for v in vals)


try:
    total, idle = read_stat()
    prev = None
    try:
        pt, pi = open(STATE).read().split()
        prev = (int(pt), int(pi))
    except Exception:
        pass

    if prev:
        dt, di = total - prev[0], idle - prev[1]
        usage = 100.0 * (dt - di) / dt if dt > 0 else 0.0
    else:
        # first run: take a short in-process sample so we show a real value now
        time.sleep(0.2)
        total2, idle2 = read_stat()
        dt, di = total2 - total, idle2 - idle
        usage = 100.0 * (dt - di) / dt if dt > 0 else 0.0
        total, idle = total2, idle2

    usage = max(0.0, min(100.0, usage))
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        open(STATE, "w").write(f"{total} {idle}")
    except Exception:
        pass

    hist = []
    try:
        hist = [int(float(x)) for x in open(HIST).read().split()][-(N - 1):]
    except Exception:
        pass
    hist.append(round(usage))
    try:
        open(HIST, "w").write(" ".join(map(str, hist)))
    except Exception:
        pass

    cls = "normal"
    if usage >= 90:
        cls = "critical"
    elif usage >= 70:
        cls = "warning"

    print(json.dumps({"text": f"{spark(hist)} {usage:.0f}%",
                      "tooltip": f"CPU usage: {usage:.0f}%",
                      "class": cls, "percentage": round(usage)}))
except Exception as e:
    print(json.dumps({"text": "n/a", "tooltip": f"CPU unavailable: {e}", "class": "unavailable"}))
