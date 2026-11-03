"""Job kinds for devkit. Each kind is a function(ctx) that runs commands through ctx.run (argv lists, no shell).

Common params (job "params" object):
  workspace | project   path to .xcworkspace / .xcodeproj, relative to the checkout
  scheme, configuration (default Release for archive/release, Debug otherwise)
  team_id               development team for export options
  extra                 list of extra xcodebuild arguments
  from_job              id of an earlier succeeded job on this host whose artifacts are used as input, e.g. a
                        unity job's Xcode export: {"from_job": "<id>", "project": "iOS/Unity-iPhone.xcodeproj"}
Unity params: project_dir (repo-relative, default root), collect (repo-relative outputs copied by basename),
  args (conservative project-specific argv). Host config unity_env supplies Editor environment variables.
aab-sign params: from_job, aab (relative artifact path), keystore_path (host file outside checkout),
  alias, keychain_service, keychain_account. Passwords are read from Keychain only at execution time.
Targets (job "target"): ios (device), ios-sim, macos; android for aab-sign.
"""
import glob, hashlib, json, math, os, plistlib, re, shutil, stat, subprocess, time, zipfile
import xml.etree.ElementTree as ET

XCODE_TARGETS = ("ios", "ios-sim", "macos")
TARGETS = XCODE_TARGETS + ("android",)
UNITY_EDITORS = "/Applications/Unity/Hub/Editor"
DEFAULT_TEMPLATE = "Time Profiler"
DEFAULT_PROFILE_SECONDS = 30
DEFAULT_LAUNCH_SECONDS = 60
UNITY_MAX_TIMEOUT = 4 * 3600
# Fixed runner/kind outputs must never be supplied by collect, even before they exist.
RESERVED_ARTIFACT_NAMES = frozenset(name.casefold() for name in (
    "job.log", "job.json", "TestResults.xml", "test-summary.json", "echo.txt",
    "profile-summary.json", "aab-sign.json"))
UNITY_PARAMS = {
    "project_dir": {"type": "string", "description": "Repo-relative Unity directory containing ProjectSettings/ProjectVersion.txt; defaults to repo root."},
    "collect": {"type": "array", "items": {"type": "string"}, "description": "Repo-relative outputs copied into artifacts by last path component after success."},
    "args": {"type": "array", "items": {"type": "string"}, "description": "Project-specific argv, e.g. -gameVersion 1.0.0. Conservative characters only; managed flags and credentials rejected."},
    "mode": {"type": "string", "enum": ["executeMethod", "test"], "default": "executeMethod"},
    "method": {"type": "string", "pattern": r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$", "description": "Static Editor method for executeMethod builds or compile gates."},
    "build_target": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9]*$", "description": "Optional Unity -buildTarget; omitted for the project's active target."},
    "unity_version": {"type": "string", "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+[abfp][0-9]+$", "description": "Defaults to the checkout's ProjectSettings/ProjectVersion.txt."},
    "quit": {"type": "boolean", "description": "executeMethod only; default true. False for gates that exit themselves."},
    "nographics": {"type": "boolean", "default": False, "description": "Optional -nographics. Leave false for graphics-dependent PlayMode tests."},
    "test_platform": {"type": "string", "enum": ["EditMode", "PlayMode"]},
    "timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": UNITY_MAX_TIMEOUT, "default": UNITY_MAX_TIMEOUT,
                "description": "Hard limit in seconds, including waiting for the host's Unity slot."},
    "extra": {"type": "array", "items": {"type": "string"}, "description": "Allow-list: -accept-apiupdate, -force-metal, -force-glcore; tests also -testFilter VALUE, -testCategory VALUE, -assemblyNames VALUE, and EditMode-only -runSynchronously. Managed flags and credentials rejected."},
}
UNITY_EXTRA_SWITCHES = {"-accept-apiupdate", "-force-metal", "-force-glcore"}
UNITY_TEST_SWITCHES = {"-runSynchronously"}
UNITY_TEST_VALUES = {"-testFilter", "-testCategory", "-assemblyNames"}
SECRET_KEY = re.compile(r"pass|secret|token|credential|username|serial|license|key|auth|bearer", re.I)
UNITY_MANAGED = {x.lower() for x in ("-projectPath", "-logFile", "-batchmode", "-quit", "-executeMethod", "-buildTarget", "-nographics", "-runTests", "-testPlatform", "-testResults", "-username", "-password", "-serial")}


def relative_path(value, allow_root=False):
    if (not isinstance(value, str) or not value or os.path.isabs(value) or
            "\\" in value or any(ord(c) < 32 for c in value) or ".." in value.split("/") or
            (not allow_root and os.path.normpath(value) == ".")):
        raise ValueError("path must be repo-relative without traversal")
    return value


def contained_path(ctx, base, rel, allow_root=False):
    try:
        relative_path(rel, allow_root)
    except ValueError as e:
        raise ctx.Fail(str(e)) from None
    root, path = os.path.realpath(base), os.path.realpath(os.path.join(base, rel))
    if os.path.commonpath([root, path]) != root:
        raise ctx.Fail("path escapes its allowed directory")
    if not os.path.exists(path):
        raise ctx.Fail("required path is missing: " + rel)
    return path


def validate_collect_tree(ctx, root, path, active=None, check=None):
    """Validate the copied tree, retaining only relative links inside this copy."""
    if check is not None:
        check()
    active = set() if active is None else active
    if os.path.islink(path) and os.path.isabs(os.readlink(path)):
        raise ctx.Fail("collect contains an absolute symlink escape")
    real = os.path.realpath(path)
    # Canonicalize the parent (e.g. system temp aliases), never a copied root link.
    boundary = os.path.join(os.path.realpath(os.path.dirname(root)), os.path.basename(root))
    if os.path.commonpath([boundary, real]) != boundary:
        raise ctx.Fail("collect contains a symlink escape")
    if os.path.isdir(real):
        if real in active:
            raise ctx.Fail("collect contains a symlink cycle")
        for name in os.listdir(real):
            validate_collect_tree(ctx, root, os.path.join(real, name), active | {real}, check)
    elif not os.path.isfile(real):
        raise ctx.Fail("collect requires existing regular files or directories")


def remove_collect_copy(path):
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


def copy_collect_entry(ctx, parent_fd, name, dest, relative, check):
    """Read only pinned descriptors; source links are data, never traversal paths."""
    check()
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(name, dir_fd=parent_fd)
        if os.path.isabs(target):
            raise ctx.Fail("collect contains an absolute symlink escape")
        resolved = os.path.normpath(os.path.join(os.path.dirname(relative), target))
        if relative == "." or resolved == ".." or resolved.startswith("../"):
            raise ctx.Fail("collect contains a symlink escape")
        os.symlink(target, dest)
        return
    # O_NONBLOCK prevents a regular-file-to-FIFO swap from blocking before fstat.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if stat.S_ISDIR(info.st_mode):
        flags |= os.O_DIRECTORY
    fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            os.mkdir(dest)
            with os.scandir(fd) as entries:
                for entry in entries:
                    copy_collect_entry(ctx, fd, entry.name, os.path.join(dest, entry.name),
                                       os.path.join(relative, entry.name), check)
            os.chmod(dest, stat.S_IMODE(info.st_mode))
        elif stat.S_ISREG(info.st_mode):
            with open(dest, "xb") as output:
                while True:
                    check()
                    chunk = os.read(fd, 1024 * 1024)
                    check()
                    if not chunk:
                        break
                    output.write(chunk)
                output.flush()
                os.fchmod(output.fileno(), stat.S_IMODE(info.st_mode))
        else:
            raise ctx.Fail("collect requires existing regular files or directories")
        check()
    finally:
        os.close(fd)


def collect_unity(ctx):
    paths = ctx.p.get("collect", [])
    if not paths:
        return
    deadline = getattr(ctx, "unity_deadline", None)
    if deadline is None:
        deadline = time.monotonic() + unity_timeout(ctx.p)
    def check():
        if os.path.exists(getattr(ctx, "cancel_file", "")):
            raise ctx.Cancelled()
        if time.monotonic() >= deadline:
            raise ctx.Fail("Unity job timed out during collect")
    work_fd = os.open(ctx.work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for rel in paths:
            check()
            contained_path(ctx, ctx.work, rel)
            parts = os.path.normpath(rel).split(os.sep)
            dest = os.path.join(ctx.art, parts[-1])
            if parts[-1].casefold() in RESERVED_ARTIFACT_NAMES:
                raise ctx.Fail("collect artifact name is reserved: " + parts[-1])
            if any(name.casefold() == parts[-1].casefold() for name in os.listdir(ctx.art)):
                raise ctx.Fail("collect artifact name already exists: " + parts[-1])
            parent_fd = os.dup(work_fd)
            try:
                for name in parts[:-1]:
                    check()
                    child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
                    os.close(parent_fd)
                    parent_fd = child_fd
                copy_collect_entry(ctx, parent_fd, parts[-1], dest, ".", check)
                # Resolve only the private copy to reject dangling links and cycles,
                # including escapes through chains of otherwise relative links.
                validate_collect_tree(ctx, dest, dest, check=check)
                check()
            except BaseException as e:
                remove_collect_copy(dest)
                if isinstance(e, OSError):
                    raise ctx.Fail("collect source changed or could not be copied") from None
                raise
            finally:
                os.close(parent_fd)
    finally:
        os.close(work_fd)


def unity_env(ctx):
    env = getattr(ctx, "cfg", {}).get("unity_env", {})
    if not isinstance(env, dict) or any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or
                                        not isinstance(v, str) or any(ord(c) < 32 for c in v) or len(v) > 4096 for k, v in env.items()):
        raise ctx.Fail("host unity_env must map environment names to string values")
    return dict(env)


def unity_timeout(params):
    value = params.get("timeout", UNITY_MAX_TIMEOUT)
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= UNITY_MAX_TIMEOUT:
        raise ValueError("Unity timeout must be greater than 0 and at most 14400 seconds")
    return value


def validate_unity_params(params, test_only=False):
    """Validate before admission and again in the worker; return normalized mode and extra argv."""
    if not isinstance(params, dict):
        raise ValueError("Unity params must be an object")
    unknown = set(params) - set(UNITY_PARAMS)
    if unknown:
        raise ValueError("unknown Unity params: " + ", ".join(sorted(unknown)))
    if "project_dir" in params:
        relative_path(params["project_dir"], allow_root=True)
    collect = params.get("collect", [])
    if not isinstance(collect, list):
        raise ValueError("Unity collect must be a list of relative paths")
    for path in collect:
        relative_path(path)
        if os.path.basename(os.path.normpath(path)).casefold() in RESERVED_ARTIFACT_NAMES:
            raise ValueError("collect artifact name is reserved")
    args = params.get("args", [])
    if not isinstance(args, list):
        raise ValueError("Unity args must be a list of strings")
    for arg in args:
        if (not isinstance(arg, str) or len(arg) > 128 or not re.fullmatch(r"-?[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", arg) or
                arg.lower() in UNITY_MANAGED or SECRET_KEY.search(arg) or
                (not arg.startswith("-") and len(arg) >= 32 and re.fullmatch(r"[A-Za-z0-9_.-]+", arg))):
            raise ValueError("Unity args contains an unsafe argument or credential")
    mode = params.get("mode", "test" if test_only else "executeMethod")
    if mode not in ("executeMethod", "test") or (test_only and mode != "test"):
        raise ValueError("Unity mode must be executeMethod or test (unity-test requires test)")
    for key in ("quit", "nographics"):
        if key in params and type(params[key]) is not bool:
            raise ValueError("Unity " + key + " must be boolean")
    for key in ("method", "build_target", "unity_version", "test_platform"):
        if key in params and (not isinstance(params[key], str) or not params[key]):
            raise ValueError("Unity " + key + " must be a non-empty string")
    if mode == "executeMethod":
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", params.get("method", ""), re.ASCII):
            raise ValueError("Unity executeMethod requires a qualified static method")
        if "test_platform" in params:
            raise ValueError("test_platform is only valid for Unity test mode")
    else:
        if params.get("test_platform") not in ("EditMode", "PlayMode"):
            raise ValueError("Unity tests require test_platform EditMode or PlayMode")
        if "method" in params or "quit" in params:
            raise ValueError("Unity tests manage their own exit; method and quit are executeMethod-only")
    if "build_target" in params and not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", params["build_target"]):
        raise ValueError("invalid Unity build_target")
    if "unity_version" in params and not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+[abfp][0-9]+", params["unity_version"]):
        raise ValueError("invalid Unity unity_version")
    unity_timeout(params)
    extra = params.get("extra", [])
    if not isinstance(extra, list) or any(not isinstance(x, str) or not x or "\x00" in x for x in extra):
        raise ValueError("Unity extra must be a list of non-empty strings")
    switches = UNITY_EXTRA_SWITCHES | (UNITY_TEST_SWITCHES if mode == "test" else set())
    values = UNITY_TEST_VALUES if mode == "test" else set()
    seen, i = set(), 0
    while i < len(extra):
        flag = extra[i]
        if flag in seen:
            raise ValueError("duplicate Unity extra flag: " + flag)
        seen.add(flag)
        if flag in switches:
            i += 1
        elif flag in values:
            if i + 1 >= len(extra) or extra[i + 1].startswith("-"):
                raise ValueError("Unity extra flag requires a value: " + flag)
            i += 2
        else:
            # Do not reflect rejected values: callers may accidentally submit credentials.
            raise ValueError("Unity extra contains an argument outside the allow-list")
    if "-force-metal" in seen and "-force-glcore" in seen:
        raise ValueError("Unity extra must select only one graphics API")
    if "-runSynchronously" in seen and params.get("test_platform") != "EditMode":
        raise ValueError("runSynchronously is only supported for EditMode")
    return mode, extra
EXPORT_METHODS = ("development", "release-testing", "app-store-connect", "developer-id", "debugging", "enterprise")


def need(ctx, *keys):
    missing = [k for k in keys if not ctx.p.get(k)]
    if missing:
        raise ctx.Fail("missing params: " + ", ".join(missing))


def need_target(ctx, allowed=XCODE_TARGETS):
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
    """Hidden Unity batch jobs. mode=executeMethod (default): method required; build_target optional;
    quit=true by default, false for self-exiting compile gates. mode=test: test_platform=EditMode|PlayMode
    required; no method/quit. Both support nographics=false, unity_version, timeout (0 < seconds <= 14400)
    and allow-listed extra argv (-accept-apiupdate, -force-metal, -force-glcore; tests also -testFilter,
    -testCategory, -assemblyNames and EditMode-only -runSynchronously). Editor version defaults to
    ProjectSettings/ProjectVersion.txt. $DEVKIT_ARTIFACTS holds outputs, TestResults.xml, test-summary.json
    and job.log. project_dir selects a contained repo subdirectory; collect copies repo outputs by basename
    after success; args passes conservative project flags. Host unity_env supplies environment variables.
    FIFO with one Unity slot per host owner account, shared across data directories."""
    unity(ctx)


def k_unity_test(ctx):
    """Alias for unity with mode=test: test_platform=EditMode|PlayMode required. Hidden batchmode,
    optional build_target/nographics/unity_version/allow-listed extra/timeout; results and job.log are artifacts.
    project_dir, collect, args and host unity_env work as for unity. The test runner exits itself;
    method and quit are rejected. Uses the same host Unity slot."""
    unity(ctx, test_only=True)


def unity(ctx, test_only=False):
    try:
        mode, extra = validate_unity_params(ctx.p, test_only)
    except ValueError as e:
        raise ctx.Fail(str(e)) from e
    project = ctx.work
    if "project_dir" in ctx.p:
        project = contained_path(ctx, ctx.work, ctx.p["project_dir"], allow_root=True)
        if not os.path.isdir(project):
            raise ctx.Fail("Unity project_dir must be a directory")
        marker = contained_path(ctx, ctx.work, os.path.join(ctx.p["project_dir"], "ProjectSettings/ProjectVersion.txt"))
        if not os.path.isfile(marker):
            raise ctx.Fail("Unity project requires ProjectSettings/ProjectVersion.txt")
    version = ctx.p.get("unity_version")
    if not version:
        marker = contained_path(ctx, ctx.work, os.path.join(ctx.p.get("project_dir", "."), "ProjectSettings/ProjectVersion.txt"))
        with open(marker) as f:
            match = re.search(r"m_EditorVersion:\s*(\S+)", f.read())
        if not match:
            raise ctx.Fail("ProjectVersion.txt has no m_EditorVersion")
        version = match.group(1)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+[abfp][0-9]+", version):
        raise ctx.Fail("invalid Unity editor version")
    editor = os.path.join(UNITY_EDITORS, version, "Unity.app", "Contents", "MacOS", "Unity")
    if not os.path.isfile(editor):
        installed = sorted(os.listdir(UNITY_EDITORS)) if os.path.isdir(UNITY_EDITORS) else []
        raise ctx.Fail("Unity %s is not installed (have: %s)" % (version, ", ".join(installed)))
    cmd = [editor, "-batchmode", "-projectPath", project, "-logFile", "-"]
    env = unity_env(ctx)
    options = {"env": env, "redact_values": [v for k, v in env.items() if SECRET_KEY.search(k)]} if env else {}
    extra = extra + ctx.p.get("args", [])
    if ctx.p.get("nographics", False):
        cmd.append("-nographics")
    if ctx.p.get("build_target"):
        cmd += ["-buildTarget", ctx.p["build_target"]]
    if mode == "executeMethod":
        if ctx.p.get("quit", True):
            cmd.append("-quit")
        ctx.run(cmd + ["-executeMethod", ctx.p["method"]] + extra, timeout=unity_timeout(ctx.p), **options)
        collect_unity(ctx)
        return
    results = os.path.join(ctx.art, "TestResults.xml")
    code = ctx.run(cmd + ["-runTests", "-testPlatform", ctx.p["test_platform"], "-testResults", results] + extra,
                   check=False, timeout=unity_timeout(ctx.p), **options)
    summary = {"platform": ctx.p["test_platform"], "exit_code": code}
    error = None
    try:
        root = ET.parse(results).getroot()
        if root.tag != "test-run":
            raise ValueError("expected NUnit test-run root")
        summary.update(result=root.get("result"), total=int(root.get("total", "0")),
                       passed=int(root.get("passed", "0")), failed=int(root.get("failed", "0")),
                       skipped=int(root.get("skipped", "0")), inconclusive=int(root.get("inconclusive", "0")))
        counts = [summary[key] for key in ("passed", "failed", "skipped", "inconclusive")]
        if any(value < 0 for value in counts) or sum(counts) != summary["total"]:
            raise ValueError("inconsistent NUnit result counts")
        if summary["result"] != "Passed" or summary["failed"] or summary["total"] <= 0:
            error = "Unity test results are not a passing, non-empty run"
    except (OSError, ET.ParseError, ValueError) as e:
        error = "Unity test results missing or invalid: " + str(e)
    if error:
        summary["error"] = error
    ctx.write("test-summary.json", json.dumps(summary, indent=2))
    if code:
        raise ctx.Fail("Unity tests exited with code %s; inspect TestResults.xml and job.log" % code)
    if error:
        raise ctx.Fail(error)
    collect_unity(ctx)


AAB_SIGN_PARAMS = {key: {"type": "string", "description": description} for key, description in {
    "from_job": "Succeeded source job on this host.", "aab": "Relative AAB path inside source artifacts.",
    "keystore_path": "Existing host keystore file outside the job checkout.", "alias": "Signing key alias.",
    "keychain_service": "Keychain generic password service.", "keychain_account": "Keychain generic password account."
}.items()}


def validate_aab_sign_params(params):
    if not isinstance(params, dict) or set(params) != set(AAB_SIGN_PARAMS):
        raise ValueError("aab-sign requires exactly: " + ", ".join(AAB_SIGN_PARAMS))
    if any(not isinstance(v, str) or not v or v.startswith("-") or any(ord(c) < 32 for c in v) for v in params.values()):
        raise ValueError("aab-sign params must be non-empty strings without control characters or leading dashes")
    relative_path(params["aab"])
    if not params["aab"].lower().endswith(".aab"):
        raise ValueError("aab-sign requires an .aab file")


def java_tools(ctx):
    home = os.environ.get("JAVA_HOME")
    if not home and os.path.isfile("/usr/libexec/java_home"):
        result = subprocess.run(["/usr/libexec/java_home"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode == 0:
            home = result.stdout.decode("utf-8", "replace").strip()
    tools = [os.path.join(home, "bin", name) if home else shutil.which(name) for name in ("jarsigner", "keytool")]
    if any(not tool or not os.path.isfile(tool) or not os.access(tool, os.X_OK) for tool in tools):
        raise ctx.Fail("aab-sign requires a JDK with jarsigner and keytool (JAVA_HOME or java_home)")
    return tools


def strip_aab_signatures(source, dest):
    """Stream entries into a new ZIP, retaining MANIFEST.MF and all non-signature entries."""
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(dest, "w") as out:
        for info in src.infolist():
            if re.fullmatch(r"META-INF/[^/]+\.(SF|RSA|EC|DSA)", info.filename, re.I):
                continue
            with src.open(info) as read, out.open(info, "w") as write:
                shutil.copyfileobj(read, write, 1 << 20)


def aab_manifest(ctx, aab):
    tool = shutil.which("bundletool")
    if not tool:
        return {"manifest_note": "Package/version metadata skipped: bundletool is not installed."}
    output = []
    code = ctx.run([tool, "dump", "manifest", "--bundle=" + aab, "--module=base"], out=output, check=False)
    try:
        if code:
            raise ValueError()
        root = ET.fromstring("".join(output))
        if root.tag != "manifest":
            raise ValueError()
        android = "{http://schemas.android.com/apk/res/android}"
        metadata = {k: v for k, v in {"package": root.get("package"), "versionCode": root.get(android + "versionCode"),
                                     "versionName": root.get(android + "versionName")}.items() if v is not None}
        if len(metadata) != 3:
            metadata["manifest_note"] = "Some package/version metadata fields were unavailable in the bundletool manifest."
        return metadata
    except (ValueError, ET.ParseError):
        return {"manifest_note": "Package/version metadata skipped: bundletool manifest unavailable or invalid."}


def verify_aab_signature(ctx, signer, aab, password):
    """Allow only the expected Android upload certificate diagnostics, failing closed."""
    allowed = {
        "self_signed": r"This jar contains entries whose signer certificate is self-signed\.",
        "chain": (r"This jar contains entries whose certificate chain is invalid\. Reason: "
                  r"PKIX path building failed: sun\.security\.provider\.certpath\.SunCertPathBuilderException: "
                  r"unable to find valid certification path to requested target"),
        "timestamp": (r"This jar contains signatures that do not include a timestamp\. Without a timestamp, "
                      r"users may not be able to validate this jar after any of the signer certificates expire "
                      r"\(as early as \d{4}-\d{2}-\d{2}\)\."),
        "attributes": (r"POSIX file permission and/or symlink attributes detected\. These attributes are ignored "
                       r"when signing and are not protected by the signature\."),
    }
    seen = set()
    state = {"verified": False, "rejected": False, "pending": False}

    def inspect(line):
        line = line.strip()
        if not line:
            return
        if re.fullmatch(r"jar verified(?:\.|, with signer errors\.)", line, re.I):
            state["verified"] = True
            return
        if re.fullmatch(r"Re-run with the -verbose and -certs options for more details\.", line, re.I):
            return
        if re.fullmatch(r"(?:Error|Warning):", line, re.I):
            state["rejected"] |= state["pending"]
            state["pending"] = True
            return
        # Some tools prefix a diagnostic instead of putting its heading on a separate line.
        line = re.sub(r"^(?:Error|Warning):\s*", "", line, flags=re.I)
        for kind, pattern in allowed.items():
            if re.fullmatch(pattern, line, re.I):
                seen.add(kind)
                state["pending"] = False
                return
        state["rejected"] = True

    code = ctx.run([signer, "-J-Duser.language=en", "-J-Duser.country=US", "-verify", "-strict", "-certs", aab],
                   parse_output=inspect, redact_values=[password], check=False)
    if (code not in (0, 4) or not state["verified"] or state["rejected"] or state["pending"] or
            ("chain" in seen and "self_signed" not in seen) or (code == 4 and not seen)):
        raise ctx.Fail("AAB signature verification failed (exit %s) or reported disallowed diagnostics" % code)


def k_aab_sign(ctx):
    """Sign an Android AAB without Xcode. Required params: from_job, aab (relative artifact path),
    keystore_path (host regular file outside checkout), alias, keychain_service, keychain_account.
    Password is read from Keychain into child environment only. Rewrites old ZIP signature entries,
    signs SHA256withRSA/SHA-256, verifies and writes aab-sign.json (hash, size, signer certificate SHA-256,
    optional bundletool package/version metadata or a clear skip note). Requires a JDK."""
    need_target(ctx, ("android",))
    try:
        validate_aab_sign_params(ctx.p)
    except ValueError as e:
        raise ctx.Fail(str(e)) from None
    if not ctx.inputs:
        raise ctx.Fail("aab-sign requires from_job artifacts")
    source = contained_path(ctx, ctx.inputs, ctx.p["aab"])
    if not os.path.isfile(source):
        raise ctx.Fail("aab must be a regular file")
    keystore = os.path.realpath(os.path.expanduser(ctx.p["keystore_path"]))
    if not os.path.isfile(keystore) or os.path.commonpath([keystore, os.path.realpath(ctx.work)]) == os.path.realpath(ctx.work):
        raise ctx.Fail("keystore_path must be a regular host file outside the job work directory")
    signer, keytool = java_tools(ctx)
    aab = os.path.join(ctx.art, os.path.basename(ctx.p["aab"]))
    if os.path.lexists(aab):
        raise ctx.Fail("AAB output already exists")
    strip_aab_signatures(source, aab)
    output = []
    ctx.run(["security", "find-generic-password", "-s", ctx.p["keychain_service"], "-a", ctx.p["keychain_account"], "-w"],
            out=output, capture_only=True, log_cmd=False)
    password = "".join(output).rstrip("\r\n")
    output.clear()
    if not password or any(ord(c) < 32 for c in password) or len(password) > 4096:
        raise ctx.Fail("Keychain returned an empty or invalid signing password")
    try:
        ctx.run([signer, "-keystore", keystore, "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256",
                 "-storepass:env", "DEVKIT_AAB_PASSWORD", "-keypass:env", "DEVKIT_AAB_PASSWORD", aab, ctx.p["alias"]],
                env={"DEVKIT_AAB_PASSWORD": password}, redact_values=[password])
        verify_aab_signature(ctx, signer, aab, password)
        fingerprints, public_keys = [], []
        def inspect_certificate(line):
            fingerprints.extend(re.findall(r"SHA256:\s*((?:[0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2})", line))
            public_keys.extend(re.findall(r"Subject Public Key Algorithm:\s*(\d+)-bit\s+(RSA|EC)\s+key\b", line))
        ctx.run([keytool, "-J-Duser.language=en", "-J-Duser.country=US", "-printcert", "-jarfile", aab],
                parse_output=inspect_certificate, redact_values=[password])
    finally:
        password = None
    if not fingerprints:
        raise ctx.Fail("keytool did not report a signer certificate SHA-256")
    if (not public_keys or len(public_keys) != len(fingerprints) or
            any(int(bits) < {"RSA": 2048, "EC": 256}[algorithm] for bits, algorithm in public_keys)):
        raise ctx.Fail("signer certificate requires at least RSA 2048 or EC 256 public key")
    digest = hashlib.sha256()
    with open(aab, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    summary = {"sha256": digest.hexdigest(), "size": os.path.getsize(aab),
               "signer_cert_sha256": fingerprints[0].replace(":", "").lower()}
    summary.update(aab_manifest(ctx, aab))
    ctx.write("aab-sign.json", json.dumps(summary, indent=2))


KINDS = {name[2:].replace("_", "-"): fn for name, fn in globals().items() if name.startswith("k_")}
