"""Read-only facts about the Mac: hardware, settings, live metrics, and screen frames for the web UI."""
import glob, json, os, plistlib, re, shutil, socket, subprocess, tempfile, threading, time

SETTINGS_TTL = 60
FRAME_INTERVAL = 0.2  # 5 fps
FRAME_MAX_PX = 1600
VIEWER_IDLE = 4.0     # stop capturing when nobody has asked for a frame for this long
TOP_PROCESSES = 8
_cache = {}


def sh(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def plist_value(path, key):
    try:
        with open(path, "rb") as f:
            return plistlib.load(f).get(key)
    except (OSError, plistlib.InvalidFileException):
        return None


# ---------------------------------------------------------------- hardware and software
def _info():
    hw = json.loads(sh(["system_profiler", "SPHardwareDataType", "-json"], 30) or "{}").get("SPHardwareDataType", [{}])[0]
    displays = []
    for gpu in json.loads(sh(["system_profiler", "SPDisplaysDataType", "-json"], 30) or "{}").get("SPDisplaysDataType", []):
        for d in gpu.get("spdisplays_ndrvs", []):
            displays.append({"name": d.get("_name"), "resolution": d.get("_spdisplays_resolution") or d.get("_spdisplays_pixels"),
                             "main": d.get("spdisplays_main") == "spdisplays_yes"})
    xcodes = []
    for app in sorted(glob.glob("/Applications/Xcode*.app")):
        info = os.path.join(app, "Contents", "Info.plist")
        xcodes.append({"path": app, "version": plist_value(info, "CFBundleShortVersionString")})
    runtimes = [l.split(" (")[0].strip() for l in sh(["xcrun", "simctl", "list", "runtimes"]).splitlines()[1:] if l.strip()]
    procs = re.match(r"proc (\d+):(\d+):(\d+)", hw.get("number_processors") or "")
    unity_root = "/Applications/Unity/Hub/Editor"
    unity = []
    for v in sorted(os.listdir(unity_root)) if os.path.isdir(unity_root) else []:
        engines = os.path.join(unity_root, v, "PlaybackEngines")
        unity.append({"version": v, "modules": sorted(os.listdir(engines)) if os.path.isdir(engines) else []})
    return {
        "hostname": socket.gethostname(), "computer_name": sh(["scutil", "--get", "ComputerName"]),
        "model": hw.get("machine_name"), "model_id": hw.get("machine_model"), "chip": hw.get("chip_type"),
        "cores": {"total": int(procs.group(1)), "performance": int(procs.group(2)), "efficiency": int(procs.group(3))} if procs else None, "memory": hw.get("physical_memory"), "serial_hidden": True,
        "macos": sh(["sw_vers", "-productVersion"]), "macos_build": sh(["sw_vers", "-buildVersion"]),
        "displays": displays, "xcodes": xcodes, "xcode_selected": sh(["xcode-select", "-p"]),
        "xcode_version": sh(["xcodebuild", "-version"]).replace("\n", " "), "simulator_runtimes": runtimes, "unity": unity,
        "ip": {i: sh(["ipconfig", "getifaddr", i]) for i in ("en0", "en1") if sh(["ipconfig", "getifaddr", i])},
    }


def info():
    return cached("info", 600, _info)


# ---------------------------------------------------------------- settings that matter for a devkit
def _settings(cfg):
    pm = sh(["pmset", "-g"])
    def pm_val(name):
        m = re.search(r"^\s*%s\s+(\d+)" % name, pm, re.M)
        return int(m.group(1)) if m else None
    s = socket.socket()
    s.settimeout(0.5)
    ssh_open = s.connect_ex(("127.0.0.1", 22)) == 0
    s.close()
    identities = re.findall(r'"([^"]+)"', sh(["security", "find-identity", "-v", "-p", "codesigning"]))
    profiles = glob.glob(os.path.expanduser("~/Library/Developer/Xcode/UserData/Provisioning Profiles/*"))
    return {
        "devkit": {"port": cfg.get("port"), "bind": cfg.get("bind"), "token_set": bool(cfg.get("token")),
                   "asc_api_key": bool((cfg.get("asc_api_key") or {}).get("key_path")), "notary_profile": bool(cfg.get("notary_profile"))},
        "signing": {"identities": identities, "provisioning_profiles": len(profiles),
                    "developer_id": any(i.startswith("Developer ID Application") for i in identities),
                    "distribution": any(i.startswith(("Apple Distribution", "iPhone Distribution")) for i in identities)},
        "developer_mode": "enabled" in sh(["DevToolsSecurity", "-status"]).lower(),
        "firewall": re.sub(r"\.?\s*\(State = \d+\)", "", sh(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"]).replace("Firewall is ", "")).rstrip("."),
        "filevault": sh(["fdesetup", "status"]).replace("FileVault is ", "").rstrip("."),
        "remote_login": ssh_open,
        "sleep_minutes": pm_val("sleep"), "display_sleep_minutes": pm_val("displaysleep"),
        "tailscale": bool(sh(["pgrep", "-x", "Tailscale"])) or bool(sh(["pgrep", "-x", "tailscaled"])),
        "screen_capture": screen_capture_allowed(),
    }


def settings(cfg):
    return cached("settings", SETTINGS_TTL, lambda: _settings(cfg))


# ---------------------------------------------------------------- live metrics
def metrics():
    ncpu = os.cpu_count() or 1
    procs = []
    for line in sh(["ps", "-Ao", "pid=,pcpu=,rss=,comm="]).splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            procs.append((float(parts[1]), int(parts[2]), int(parts[0]), os.path.basename(parts[3])))
    cpu = min(100.0, sum(p[0] for p in procs) / ncpu)
    vm = sh(["vm_stat"])
    page = int(re.search(r"page size of (\d+)", vm).group(1)) if "page size" in vm else 16384
    def pages(name):
        m = re.search(r"%s:\s+(\d+)" % re.escape(name), vm)
        return int(m.group(1)) if m else 0
    total = int(sh(["sysctl", "-n", "hw.memsize"]) or 0)
    used = (pages("Pages active") + pages("Pages wired down") + pages("Pages occupied by compressor")) * page
    disk = shutil.disk_usage(os.path.expanduser("~"))
    therm = sh(["pmset", "-g", "therm"])
    batt = sh(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%;\s*([^;]+);", batt)
    return {
        "time": time.time(), "cpu_percent": round(cpu, 1), "load": [round(x, 2) for x in os.getloadavg()],
        "memory_used": used, "memory_total": total, "disk_free": disk.free, "disk_total": disk.total,
        "thermal_warning": "No thermal warning" not in therm if therm else None,
        "battery": {"percent": int(m.group(1)), "state": m.group(2).strip(), "ac": "AC Power" in batt} if m else None,
        "uptime_seconds": int(time.time() - int(re.search(r"sec = (\d+)", sh(["sysctl", "-n", "kern.boottime"])).group(1))),
        "top": [{"name": n, "pid": pid, "cpu": c, "memory": r * 1024} for c, r, pid, n in sorted(procs, reverse=True)[:TOP_PROCESSES]],
    }


# ---------------------------------------------------------------- screen frames
class Screen:
    """Captures the given display at ~5 fps while someone is watching; the web UI polls the latest frame."""

    def __init__(self):
        self.frames, self.errors, self.last_view, self.lock = {}, {}, {}, threading.Lock()
        self.tmp = tempfile.mkdtemp(prefix="devkit-screen-")

    def frame(self, display):
        with self.lock:
            first = display not in self.last_view or time.time() - self.last_view[display] > VIEWER_IDLE
            self.last_view[display] = time.time()
        if first:
            threading.Thread(target=self._loop, args=(display,), daemon=True).start()
            deadline = time.time() + 3
            while display not in self.frames and display not in self.errors and time.time() < deadline:
                time.sleep(0.05)
        if display in self.errors and display not in self.frames:
            raise PermissionError(self.errors[display])
        return self.frames.get(display)

    def _loop(self, display):
        raw, small = os.path.join(self.tmp, "raw%d.jpg" % display), os.path.join(self.tmp, "f%d.jpg" % display)
        while time.time() - self.last_view.get(display, 0) < VIEWER_IDLE:
            t0 = time.time()
            r = subprocess.run(["screencapture", "-x", "-C", "-t", "jpg", "-D", str(display), raw], capture_output=True, text=True)
            if r.returncode or not os.path.exists(raw):
                self.errors[display] = (r.stderr or "screen capture failed").strip()
                self.frames.pop(display, None)
                time.sleep(2)
                continue
            subprocess.run(["sips", "-Z", str(FRAME_MAX_PX), "-s", "formatOptions", "60", raw, "--out", small], capture_output=True)
            with open(small, "rb") as f:
                self.frames[display] = f.read()
            self.errors.pop(display, None)
            time.sleep(max(0, FRAME_INTERVAL - (time.time() - t0)))
        self.last_view.pop(display, None)


def screen_capture_allowed():
    probe = os.path.join(tempfile.gettempdir(), "devkit-probe.jpg")
    ok = subprocess.run(["screencapture", "-x", "-t", "jpg", "-R", "0,0,8,8", probe], capture_output=True).returncode == 0 and os.path.exists(probe)
    if os.path.exists(probe):
        os.remove(probe)
    return ok
