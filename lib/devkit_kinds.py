"""Job kinds for devkit. Each kind is a function(ctx) that runs commands through ctx.run (argv lists, no shell).

Common params (job "params" object):
  workspace | project   path to .xcworkspace / .xcodeproj, relative to the checkout
  scheme, configuration (default Release for archive/release, Debug otherwise)
  team_id               development team for export options
  extra                 list of extra xcodebuild arguments
  from_job              id of an earlier succeeded job on this host whose artifacts are used as input, e.g. a
                        unity job's Xcode export: {"from_job": "<id>", "project": "iOS/Unity-iPhone.xcodeproj"}
Targets (job "target"): ios (device), ios-sim, macos.
"""
import glob, os, plistlib, re

TARGETS = ("ios", "ios-sim", "macos")
UNITY_EDITORS = "/Applications/Unity/Hub/Editor"
DEFAULT_TEMPLATE = "Time Profiler"
DEFAULT_PROFILE_SECONDS = 30
DEFAULT_LAUNCH_SECONDS = 60
EXPORT_METHODS = ("development", "release-testing", "app-store-connect", "developer-id", "debugging", "enterprise")


def need(ctx, *keys):
    missing = [k for k in keys if not ctx.p.get(k)]
    if missing:
        raise ctx.Fail("missing params: " + ", ".join(missing))


def need_target(ctx, allowed=TARGETS):
    if ctx.target not in allowed:
        raise ctx.Fail("target must be one of: " + ", ".join(allowed))


def need_device(ctx):
    if ctx.target in ("ios", "ios-sim") and not ctx.device:
        raise ctx.Fail("this kind needs --device for target " + ctx.target)


def inside(ctx, rel):
    """Resolve a params path inside from_job's artifacts, the checkout, artifacts or derived data; never outside."""
    for base in [b for b in (ctx.inputs, ctx.work, ctx.art, ctx.derived) if b]:
        p = os.path.realpath(os.path.join(base, rel))
        if p.startswith(os.path.realpath(base) + os.sep) and os.path.exists(p):
            return p
    raise ctx.Fail("path not found in %scheckout or artifacts: %s" % ("from_job artifacts, " if ctx.inputs else "", rel))


def config_name(ctx, default):
    return ctx.p.get("configuration") or default


def xcodebuild(ctx, *action, configuration="Debug", destination=None, auth=True):
    need(ctx, "scheme")
    cmd = ["xcodebuild"]
    if ctx.p.get("workspace"):
        cmd += ["-workspace", inside(ctx, ctx.p["workspace"])]
    elif ctx.p.get("project"):
        cmd += ["-project", inside(ctx, ctx.p["project"])]
    cmd += ["-scheme", ctx.p["scheme"], "-configuration", config_name(ctx, configuration),
            "-derivedDataPath", ctx.derived]
    if destination:
        cmd += ["-destination", destination]
    if auth:
        cmd += ctx.auth_args()
    cmd += [str(x) for x in ctx.p.get("extra") or []]
    ctx.run(cmd + list(action))


def destination(ctx, generic=False):
    if ctx.target == "macos":
        return "generic/platform=macOS" if generic else "platform=macOS"
    if ctx.target == "ios-sim":
        return "generic/platform=iOS Simulator" if generic or not ctx.device else "platform=iOS Simulator,id=" + ctx.device
    return "generic/platform=iOS" if generic or not ctx.device else "id=" + ctx.device


def built_app(ctx, configuration):
    sdk = {"ios": "iphoneos", "ios-sim": "iphonesimulator"}.get(ctx.target)
    folder = configuration + ("-" + sdk if sdk else "")
    apps = sorted(glob.glob(os.path.join(ctx.derived, "Build", "Products", folder, "*.app")), key=os.path.getmtime)
    if not apps:
        raise ctx.Fail("no .app found in Build/Products/" + folder)
    return apps[-1]


def app_info(app):
    plist = os.path.join(app, "Contents", "Info.plist") if os.path.isdir(os.path.join(app, "Contents")) else os.path.join(app, "Info.plist")
    with open(plist, "rb") as f:
        return plistlib.load(f)


def mac_binary(app):
    return os.path.join(app, "Contents", "MacOS", app_info(app)["CFBundleExecutable"])


def launch_args(ctx):
    return [str(a) for a in ctx.p.get("launch_args") or []]


def launch_env(ctx):
    return {str(k): str(v) for k, v in (ctx.p.get("env") or {}).items()}


# ---------------------------------------------------------------- kinds
def k_echo(ctx):
    ctx.log("echo args: " + ctx.args)
    ctx.write("echo.txt", ctx.args + "\n")


def k_shell(ctx):
    if not ctx.args:
        raise ctx.Fail("shell jobs need args")
    ctx.run(["/bin/bash", "-c", ctx.args], log_cmd=False)


def k_build(ctx):
    """xcodebuild build for the target (and device, if given); the .app is copied to artifacts."""
    need_target(ctx)
    conf = config_name(ctx, "Debug")
    xcodebuild(ctx, "build", configuration=conf, destination=destination(ctx))
    ctx.run(["ditto", built_app(ctx, conf), os.path.join(ctx.art, os.path.basename(built_app(ctx, conf)))])


def k_test(ctx):
    """xcodebuild test; the .xcresult bundle goes to artifacts."""
    need_target(ctx)
    need_device(ctx) if ctx.target == "ios" else None
    xcodebuild(ctx, "test", "-resultBundlePath", os.path.join(ctx.art, "Tests.xcresult"),
               configuration=config_name(ctx, "Debug"), destination=destination(ctx))


def archive(ctx):
    path = os.path.join(ctx.art, "App.xcarchive")
    xcodebuild(ctx, "archive", "-archivePath", path, configuration=config_name(ctx, "Release"),
               destination=destination(ctx, generic=True))
    return path


def export(ctx, archive_path, method, upload=False):
    if method not in EXPORT_METHODS:
        raise ctx.Fail("export_method must be one of: " + ", ".join(EXPORT_METHODS))
    opts = {"method": method, "signingStyle": "automatic", "destination": "upload" if upload else "export"}
    if ctx.p.get("team_id"):
        opts["teamID"] = ctx.p["team_id"]
    plist = os.path.join(ctx.art, "ExportOptions.plist")
    with open(plist, "wb") as f:
        plistlib.dump(opts, f)
    out = os.path.join(ctx.art, "export")
    ctx.run(["xcodebuild", "-exportArchive", "-archivePath", archive_path, "-exportPath", out,
             "-exportOptionsPlist", plist] + ctx.auth_args())
    return out


def k_archive(ctx):
    """Archive (signed, Release); optional params.export_method exports an .ipa / .app."""
    need_target(ctx, ("ios", "macos"))
    path = archive(ctx)
    if ctx.p.get("export_method"):
        export(ctx, path, ctx.p["export_method"])


def notarize(ctx, path):
    profile = ctx.cfg.get("notary_profile")
    if not profile:
        raise ctx.Fail("config.json has no notary_profile (create one with: xcrun notarytool store-credentials)")
    zipped = path + ".zip"
    ctx.run(["ditto", "-c", "-k", "--keepParent", path, zipped])
    ctx.run(["xcrun", "notarytool", "submit", zipped, "--keychain-profile", profile, "--wait"])
    ctx.run(["xcrun", "stapler", "staple", path])
    os.remove(zipped)
    ctx.run(["ditto", "-c", "-k", "--keepParent", path, zipped])  # stapled, ready to ship


def k_release(ctx):
    """iOS: archive, export and upload to App Store Connect / TestFlight.
    macOS: archive, export Developer ID, notarize, staple, zip (params.export_method=app-store-connect uploads instead)."""
    need_target(ctx, ("ios", "macos"))
    path = archive(ctx)
    if ctx.target == "ios" or ctx.p.get("export_method") == "app-store-connect":
        export(ctx, path, "app-store-connect", upload=True)
        return
    out = export(ctx, path, "developer-id")
    for item in glob.glob(os.path.join(out, "*.app")) + glob.glob(os.path.join(out, "*.pkg")):
        notarize(ctx, item)


def k_notarize(ctx):
    """Notarize and staple an existing .app/.pkg/.dmg from the checkout (params.path)."""
    need(ctx, "path")
    notarize(ctx, inside(ctx, ctx.p["path"]))


def install_app(ctx, app):
    if ctx.target == "ios":
        ctx.run(["xcrun", "devicectl", "device", "install", "app", "--device", ctx.device, app])
    elif ctx.target == "ios-sim":
        ctx.run(["xcrun", "simctl", "boot", ctx.device], check=False)
        ctx.run(["xcrun", "simctl", "install", ctx.device, app])
    else:
        ctx.run(["ditto", app, os.path.join(ctx.art, os.path.basename(app))])


def k_deploy(ctx):
    """Build for the device (or simulator) and install it; params.launch=true launches it afterwards."""
    need_target(ctx)
    need_device(ctx)
    conf = config_name(ctx, "Debug")
    if ctx.p.get("app"):
        app = inside(ctx, ctx.p["app"])
    else:
        xcodebuild(ctx, "build", configuration=conf, destination=destination(ctx))
        app = built_app(ctx, conf)
    install_app(ctx, app)
    if ctx.p.get("launch"):
        ctx.p.setdefault("bundle_id", app_info(app)["CFBundleIdentifier"])
        ctx.p.setdefault("app", app)
        k_launch(ctx)


def start_app(ctx, wait_seconds=None, console=True):
    """Launch the app; with wait_seconds, stream its console for that long, then stop it.
    Without console, returns the launched process id (or None if it could not be determined)."""
    args, env = launch_args(ctx), launch_env(ctx)
    if ctx.target == "macos":
        need(ctx, "app")
        return ctx.run([mac_binary(inside(ctx, ctx.p["app"]))] + args, env=env, timeout=wait_seconds, timeout_ok=True)
    need(ctx, "bundle_id")
    need_device(ctx)
    if ctx.target == "ios-sim":
        cmd = ["xcrun", "simctl", "launch", "--terminate-running-process"] + (["--console-pty"] if console else [])
        cmd += [ctx.device, ctx.p["bundle_id"]] + args
        out = []
        ctx.run(cmd, env={"SIMCTL_CHILD_" + k: v for k, v in env.items()}, timeout=wait_seconds, timeout_ok=True, out=out)
        m = re.search(r":\s*(\d+)\s*$", "".join(out[:1]))
        return int(m.group(1)) if m and not console else None
    cmd = ["xcrun", "devicectl", "device", "process", "launch", "--device", ctx.device, "--terminate-existing"]
    if env:
        cmd += ["--environment-variables", ctx.json(env)]
    if console:
        cmd.append("--console")
        return ctx.run(cmd + [ctx.p["bundle_id"]] + args, timeout=wait_seconds, timeout_ok=True)
    result = os.path.join(ctx.art, "launch.json")
    ctx.run(cmd + ["--json-output", result, ctx.p["bundle_id"]] + args)
    with open(result) as f:
        return (ctx.json_load(f).get("result", {}).get("process") or {}).get("processIdentifier")


def k_launch(ctx):
    """Launch an installed app with params.launch_args / env and stream its console for params.duration seconds."""
    need_target(ctx)
    start_app(ctx, wait_seconds=int(ctx.p.get("duration") or DEFAULT_LAUNCH_SECONDS))


def k_profile(ctx):
    """Record an Instruments trace (params.template, default Time Profiler) for params.duration seconds.
    iOS/simulator: launches params.bundle_id (with launch_args/env), then attaches to the new process
    (params.process name as a fallback).
    macOS: launches params.app under xctrace. params.all_processes=true records the whole system instead."""
    need_target(ctx)
    seconds = int(ctx.p.get("duration") or DEFAULT_PROFILE_SECONDS)
    trace = os.path.join(ctx.art, "profile.trace")
    cmd = ["xcrun", "xctrace", "record", "--no-prompt", "--template", ctx.p.get("template") or DEFAULT_TEMPLATE,
           "--time-limit", "%ds" % seconds, "--output", trace]
    if ctx.target != "macos":
        need_device(ctx)
        cmd += ["--device", ctx.device]
    if ctx.p.get("all_processes"):
        cmd.append("--all-processes")
    elif ctx.target == "macos":
        need(ctx, "app")
        for k, v in launch_env(ctx).items():
            cmd += ["--env", "%s=%s" % (k, v)]
        cmd += ["--launch", "--", mac_binary(inside(ctx, ctx.p["app"]))] + launch_args(ctx)
    else:
        pid = start_app(ctx, console=False)
        if not pid:
            need(ctx, "process")
        cmd += ["--attach", str(pid or ctx.p["process"])]
    ctx.run(cmd, timeout=seconds + 300)
    ctx.run(["xcrun", "xctrace", "export", "--input", trace, "--toc", "--output", os.path.join(ctx.art, "toc.xml")], check=False)
    summarize_time_profile(ctx, trace, seconds)


def summarize_time_profile(ctx, trace, seconds):
    """Aggregate self time per leaf function from the trace's time-profile table into profile-summary.json."""
    xml_path = os.path.join(ctx.art, "time-profile.xml")
    xpath = '/trace-toc/run[@number="1"]/data/table[@schema="time-profile"]'
    if ctx.run(["xcrun", "xctrace", "export", "--input", trace, "--xpath", xpath, "--output", xml_path], check=False):
        return
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError):
        return
    ids = {el.get("id"): el for el in root.iter() if el.get("id")}
    deref = lambda el: ids.get(el.get("ref"), el) if el is not None and el.get("ref") else el
    totals, total = {}, 0
    for row in root.iter("row"):
        weight = deref(row.find("weight"))
        bt = deref(row.find("tagged-backtrace"))
        if bt is None:
            bt = deref(row.find("backtrace"))
        if weight is None or bt is None:
            continue
        frame = deref(bt.find(".//frame"))  # leaf frame; tagged backtraces may nest a <backtrace>
        if frame is None:
            continue
        w = int(weight.text or 0)
        name = frame.get("name") or "?"
        binary = deref(frame.find("binary"))
        key = (name, binary.get("name") if binary is not None else "")
        totals[key] = totals.get(key, 0) + w
        total += w
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:30]
    summary = {"template": ctx.p.get("template") or DEFAULT_TEMPLATE, "seconds": seconds, "samples_ms": round(total / 1e6, 1),
               "top": [{"function": n, "binary": b, "ms": round(w / 1e6, 1), "percent": round(100.0 * w / total, 1) if total else 0}
                       for (n, b), w in top]}
    ctx.write("profile-summary.json", ctx.json(summary))
    os.remove(xml_path)


def k_screenshot(ctx):
    need_target(ctx, ("ios", "ios-sim"))
    need_device(ctx)
    out = os.path.join(ctx.art, "screenshot.png")
    if ctx.target == "ios-sim":
        ctx.run(["xcrun", "simctl", "io", ctx.device, "screenshot", out])
    else:
        ctx.run(["xcrun", "devicectl", "device", "capture", "screenshot", "--device", ctx.device, "--destination", out])


def k_crashlogs(ctx):
    """Copy the device's crash logs into artifacts."""
    need_target(ctx, ("ios",))
    need_device(ctx)
    ctx.run(["xcrun", "devicectl", "device", "copy", "from", "--device", ctx.device, "--domain-type", "systemCrashLogs",
             "--source", "/", "--destination", os.path.join(ctx.art, "crashlogs")])


def k_unity(ctx):
    """Unity batch build: params.build_target (iOS, OSXUniversal, Android, WebGL), params.method (static build method).
    Editor version from params.unity_version or ProjectSettings/ProjectVersion.txt. Output goes to $DEVKIT_ARTIFACTS."""
    need(ctx, "build_target", "method")
    version = ctx.p.get("unity_version")
    if not version:
        with open(inside(ctx, "ProjectSettings/ProjectVersion.txt")) as f:
            version = re.search(r"m_EditorVersion:\s*(\S+)", f.read()).group(1)
    editor = os.path.join(UNITY_EDITORS, version, "Unity.app", "Contents", "MacOS", "Unity")
    if not os.path.exists(editor):
        raise ctx.Fail("Unity %s is not installed (have: %s)" % (version, ", ".join(sorted(os.listdir(UNITY_EDITORS)))))
    ctx.run([editor, "-batchmode", "-quit", "-projectPath", ctx.work, "-buildTarget", ctx.p["build_target"],
             "-executeMethod", ctx.p["method"], "-logFile", "-"] + [str(x) for x in ctx.p.get("extra") or []],
            timeout=4 * 3600)


KINDS = {name[2:]: fn for name, fn in globals().items() if name.startswith("k_")}
