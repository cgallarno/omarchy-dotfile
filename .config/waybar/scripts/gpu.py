#!/usr/bin/env python3
"""Waybar GPU module (NVIDIA).

Emits an nvtop-style utilization sparkline (rolling history persisted
between polls) plus current util%, temp and VRAM.
"""
import subprocess, json, os

HIST = os.path.expanduser("~/.cache/waybar-gpu-hist")
BLOCKS = "▁▂▃▄▅▆▇█"
N = 10  # samples of history (~N*interval seconds)


def spark(vals):
    return "".join(BLOCKS[min(7, max(0, round(v / 100 * 7)))] for v in vals)


try:
    out = subprocess.check_output(
        ["nvidia-smi",
         "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,name",
         "--format=csv,noheader,nounits"],
        text=True, timeout=5).strip().splitlines()[0]
    util, temp, mused, mtot, name = [x.strip() for x in out.split(",")]
    util, temp = int(float(util)), int(float(temp))
    mused, mtot = float(mused), float(mtot)
    gib, gtot = mused / 1024, mtot / 1024

    # rolling history for the sparkline
    hist = []
    try:
        hist = [int(x) for x in open(HIST).read().split()][-(N - 1):]
    except Exception:
        pass
    hist.append(util)
    try:
        os.makedirs(os.path.dirname(HIST), exist_ok=True)
        open(HIST, "w").write(" ".join(map(str, hist)))
    except Exception:
        pass

    cls = "normal"
    if util >= 90 or temp >= 80:
        cls = "critical"
    elif util >= 60 or temp >= 70:
        cls = "warning"

    text = f"{spark(hist)} {util}% {temp}° {gib:.1f}G"
    tip = (f"{name}\n"
           f"Utilization: {util}%\n"
           f"Temp: {temp}°C\n"
           f"VRAM: {gib:.1f} / {gtot:.1f} GiB ({mused / mtot * 100:.0f}%)")
    print(json.dumps({"text": text, "tooltip": tip, "class": cls, "percentage": util}))
except Exception as e:
    print(json.dumps({"text": "n/a", "tooltip": f"GPU unavailable: {e}", "class": "unavailable"}))
