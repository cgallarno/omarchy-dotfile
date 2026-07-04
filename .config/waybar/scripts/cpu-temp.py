#!/usr/bin/env python3
"""Waybar CPU temperature module.

Resolves the CPU hwmon device by name at runtime (hwmon indices are not
stable across reboots). Prefers AMD k10temp/Tctl, falls back to Intel
coretemp package temp, then acpitz.
"""
import glob, os, json


def read_temp():
    hwmons = {}
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            hwmons[open(os.path.join(d, "name")).read().strip()] = d
        except Exception:
            pass

    # AMD: k10temp Tctl (temp with label "Tctl", else temp1)
    d = hwmons.get("k10temp")
    if d:
        for lbl in glob.glob(os.path.join(d, "temp*_label")):
            if open(lbl).read().strip() == "Tctl":
                inp = lbl.replace("_label", "_input")
                return int(open(inp).read()) / 1000.0
        try:
            return int(open(os.path.join(d, "temp1_input")).read()) / 1000.0
        except Exception:
            pass

    # Intel: coretemp "Package id 0"
    d = hwmons.get("coretemp")
    if d:
        for lbl in glob.glob(os.path.join(d, "temp*_label")):
            if open(lbl).read().strip().startswith("Package"):
                return int(open(lbl.replace("_label", "_input")).read()) / 1000.0

    # Fallback: acpitz
    d = hwmons.get("acpitz")
    if d:
        try:
            return int(open(os.path.join(d, "temp1_input")).read()) / 1000.0
        except Exception:
            pass
    return None


try:
    t = read_temp()
    if t is None:
        raise RuntimeError("no CPU temp sensor")
    t = round(t)
    cls = "normal"
    if t >= 90:
        cls = "critical"
    elif t >= 80:
        cls = "warning"
    print(json.dumps({"text": f"{t}°C", "tooltip": f"CPU temperature: {t}°C",
                      "class": cls, "percentage": t}))
except Exception as e:
    print(json.dumps({"text": "—", "tooltip": f"CPU temp unavailable: {e}", "class": "unavailable"}))
