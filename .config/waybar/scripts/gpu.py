#!/usr/bin/env python3
"""Waybar GPU module (NVIDIA). Emits util%, temp, VRAM as JSON."""
import subprocess, json

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

    cls = "normal"
    if util >= 90 or temp >= 80:
        cls = "critical"
    elif util >= 60 or temp >= 70:
        cls = "warning"

    text = f"{util}% {temp}° {gib:.1f}G"
    tip = (f"{name}\n"
           f"Utilization: {util}%\n"
           f"Temp: {temp}°C\n"
           f"VRAM: {gib:.1f} / {gtot:.1f} GiB ({mused / mtot * 100:.0f}%)")
    print(json.dumps({"text": text, "tooltip": tip, "class": cls, "percentage": util}))
except Exception as e:
    print(json.dumps({"text": "n/a", "tooltip": f"GPU unavailable: {e}", "class": "unavailable"}))
