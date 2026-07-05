#!/usr/bin/env python3
"""Ship this machine's health + AI-usage metrics to Home Assistant via MQTT.

Publishes Home Assistant MQTT-discovery configs (retained) so the sensors
auto-register under one "Omarchy" device, plus a JSON state payload. Uses a
tiny built-in MQTT 3.1.1 client so it has no third-party dependencies.

Run headless on a timer (see hass-reporter.timer). Config/secrets come from
~/.config/hass-reporter/env (MQTT_HOST/PORT/USER/PASS). System metrics are
gathered every run; the heavier AI-usage lookups are cached for AI_TTL secs.
"""
import os, json, socket, glob, time, subprocess, base64, urllib.request, datetime

CFG_DIR = os.path.expanduser("~/.config/hass-reporter")
ENV = os.path.join(CFG_DIR, "env")
CPU_STATE = os.path.expanduser("~/.cache/hass-reporter-cpu")
AI_CACHE = os.path.expanduser("~/.cache/hass-reporter-ai.json")
INTERVAL = 30
EXPIRE = 120           # HA marks sensor unavailable if not updated within this
AI_TTL = 300           # re-fetch Claude/Codex at most every 5 min
DEVICE_ID = "terra"
DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC = "terra/metrics"
AVAIL_TOPIC = "terra/status"


# ---------- config ----------
def load_env():
    env = {}
    with open(ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# ---------- minimal MQTT 3.1.1 client (publish only) ----------
def _rl(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        out.append(b)
        if n == 0:
            return bytes(out)


def _s(x):
    b = x.encode()
    return len(b).to_bytes(2, "big") + b


class MQTT:
    def __init__(self, host, port, user, pw, client_id="terra-reporter"):
        self.sock = socket.create_connection((host, int(port)), timeout=10)
        # CONNECT with will (availability): flags user|pass|will|clean = 0xC6
        will_topic, will_msg = AVAIL_TOPIC, b"offline"
        flags = 0x80 | 0x40 | 0x04 | 0x02  # user, pass, will, clean
        will_qos_retain = 0x20             # will retain
        vh = _s("MQTT") + bytes([4, flags | will_qos_retain]) + (60).to_bytes(2, "big")
        payload = _s(client_id) + _s(will_topic) + _s(will_msg.decode()) + _s(user) + _s(pw)
        pkt = bytes([0x10]) + _rl(len(vh) + len(payload)) + vh + payload
        self.sock.sendall(pkt)
        resp = self.sock.recv(4)
        if len(resp) < 4 or resp[0] != 0x20 or resp[3] != 0:
            raise RuntimeError(f"CONNACK failed: {resp!r}")

    def publish(self, topic, payload, retain=False):
        if not isinstance(payload, (bytes, bytearray)):
            payload = str(payload).encode()
        body = _s(topic) + payload
        self.sock.sendall(bytes([0x30 | (1 if retain else 0)]) + _rl(len(body)) + body)

    def close(self):
        try:
            self.sock.sendall(b"\xe0\x00")
            self.sock.close()
        except Exception:
            pass


# ---------- metric gatherers ----------
def cpu_usage():
    def read():
        with open("/proc/stat") as f:
            v = list(map(int, f.readline().split()[1:]))
        return sum(v), v[3] + (v[4] if len(v) > 4 else 0)
    total, idle = read()
    prev = None
    try:
        pt, pi = open(CPU_STATE).read().split()
        prev = (int(pt), int(pi))
    except Exception:
        pass
    if prev:
        dt, di = total - prev[0], idle - prev[1]
    else:
        time.sleep(0.2)
        t2, i2 = read()
        dt, di = t2 - total, i2 - idle
        total, idle = t2, i2
    try:
        os.makedirs(os.path.dirname(CPU_STATE), exist_ok=True)
        open(CPU_STATE, "w").write(f"{total} {idle}")
    except Exception:
        pass
    return round(100.0 * (dt - di) / dt, 1) if dt > 0 else 0.0


def cpu_temp():
    names = {}
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            names[open(os.path.join(d, "name")).read().strip()] = d
        except Exception:
            pass
    d = names.get("k10temp")
    if d:
        for lbl in glob.glob(os.path.join(d, "temp*_label")):
            if open(lbl).read().strip() == "Tctl":
                return round(int(open(lbl.replace("_label", "_input")).read()) / 1000.0, 1)
        return round(int(open(os.path.join(d, "temp1_input")).read()) / 1000.0, 1)
    for nm in ("coretemp", "acpitz"):
        d = names.get(nm)
        if d:
            return round(int(open(os.path.join(d, "temp1_input")).read()) / 1000.0, 1)
    return None


def memory_usage():
    mi = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        mi[k] = int(v.split()[0])
    total, avail = mi["MemTotal"], mi.get("MemAvailable", mi["MemFree"])
    return round(100.0 * (total - avail) / total, 1)


def gpu_metrics():
    out = subprocess.check_output(
        ["nvidia-smi",
         "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
         "--format=csv,noheader,nounits"], text=True, timeout=6).strip().splitlines()[0]
    util, temp, used, tot = [float(x) for x in out.split(",")]
    return {"gpu_usage": round(util), "gpu_temp": round(temp),
            "gpu_vram_used": round(used / 1024, 2),
            "gpu_vram_percent": round(100.0 * used / tot, 1)}


def claude_usage():
    d = json.load(open(os.path.expanduser("~/.claude/.credentials.json")))
    o = d.get("claudeAiOauth", d)
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {o['accessToken']}",
                 "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-cli"})
    data = json.load(urllib.request.urlopen(req, timeout=8))
    s = (data.get("five_hour") or {}).get("utilization") or 0
    w = (data.get("seven_day") or {}).get("utilization") or 0
    return {"claude_session_remaining": round(100 - s),
            "claude_week_remaining": round(100 - w)}


CODEX_REMOTE = (
    "import json\n"
    "from agent.account_usage import _fetch_codex_account_usage\n"
    "s=_fetch_codex_account_usage()\n"
    "o={w.label:w.used_percent for w in s.windows}\n"
    "print(json.dumps(o))\n")


def codex_usage():
    b64 = base64.b64encode(CODEX_REMOTE.encode()).decode()
    remote = ("pct exec 153 -- /usr/local/bin/as_hermes "
              "/var/lib/hermes/.hermes/hermes-agent/venv/bin/python "
              f"-c \"import base64;exec(base64.b64decode('{b64}').decode())\"")
    out = subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "pathfinder", remote],
        text=True, timeout=25, stderr=subprocess.DEVNULL).strip().splitlines()[-1]
    o = json.loads(out)
    res = {}
    if o.get("Session") is not None:
        res["codex_session_remaining"] = round(100 - float(o["Session"]))
    if o.get("Weekly") is not None:
        res["codex_week_remaining"] = round(100 - float(o["Weekly"]))
    return res


def ai_metrics():
    """Claude + Codex, cached for AI_TTL seconds (each fetched independently)."""
    cache = {}
    try:
        cache = json.load(open(AI_CACHE))
    except Exception:
        pass
    now = time.time()
    for key, fn in (("claude", claude_usage), ("codex", codex_usage)):
        if now - cache.get(f"_{key}_ts", 0) > AI_TTL:
            try:
                vals = fn()
                cache.update(vals)
                cache[f"_{key}_ts"] = now
            except Exception:
                pass  # keep previous cached values if any
    try:
        os.makedirs(os.path.dirname(AI_CACHE), exist_ok=True)
        json.dump(cache, open(AI_CACHE, "w"))
    except Exception:
        pass
    return {k: v for k, v in cache.items() if not k.startswith("_")}


# ---------- HA discovery ----------
DEVICE = {"identifiers": [DEVICE_ID], "name": "Terra",
          "manufacturer": "Gallarno Technology", "model": "Desktop · Ryzen + RTX 4070"}

# key: (friendly name, unit, device_class|None, icon|None)
SENSORS = {
    "cpu_usage": ("CPU Usage", "%", None, "mdi:cpu-64-bit"),
    "cpu_temp": ("CPU Temperature", "°C", "temperature", None),
    "memory_usage": ("Memory Usage", "%", None, "mdi:memory"),
    "gpu_usage": ("GPU Usage", "%", None, "mdi:expansion-card-variant"),
    "gpu_temp": ("GPU Temperature", "°C", "temperature", None),
    "gpu_vram_used": ("GPU VRAM Used", "GiB", None, "mdi:memory"),
    "gpu_vram_percent": ("GPU VRAM Usage", "%", None, "mdi:memory"),
    "claude_session_remaining": ("Claude Session Remaining", "%", None, "mdi:robot-outline"),
    "claude_week_remaining": ("Claude Week Remaining", "%", None, "mdi:robot-outline"),
    "codex_session_remaining": ("Codex Session Remaining", "%", None, "mdi:brain"),
    "codex_week_remaining": ("Codex Week Remaining", "%", None, "mdi:brain"),
}


def discovery_msgs():
    for key, (name, unit, dclass, icon) in SENSORS.items():
        cfg = {
            "name": name,
            "unique_id": f"{DEVICE_ID}_{key}",
            "object_id": f"{DEVICE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "unit_of_measurement": unit,
            "state_class": "measurement",
            "availability_topic": AVAIL_TOPIC,
            "expire_after": EXPIRE,
            "device": DEVICE,
        }
        if dclass:
            cfg["device_class"] = dclass
        if icon:
            cfg["icon"] = icon
        topic = f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/{key}/config"
        yield topic, json.dumps(cfg), True


# ---------- main ----------
def main():
    env = load_env()
    metrics = {}
    for fn in (lambda: {"cpu_usage": cpu_usage()},
               lambda: {"cpu_temp": cpu_temp()},
               lambda: {"memory_usage": memory_usage()},
               gpu_metrics, ai_metrics):
        try:
            metrics.update({k: v for k, v in fn().items() if v is not None})
        except Exception:
            pass

    m = MQTT(env["MQTT_HOST"], env.get("MQTT_PORT", 1883), env["MQTT_USER"], env["MQTT_PASS"])
    try:
        for topic, payload, retain in discovery_msgs():
            m.publish(topic, payload, retain=True)
        m.publish(AVAIL_TOPIC, "online", retain=True)
        m.publish(STATE_TOPIC, json.dumps(metrics), retain=True)
    finally:
        m.close()
    print(f"{datetime.datetime.now():%H:%M:%S} published {len(metrics)} metrics: "
          + ", ".join(sorted(metrics)))


if __name__ == "__main__":
    main()
