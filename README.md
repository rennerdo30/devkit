# Devkit

A remote build, deploy, release and profiling host for games and apps. Agents and people drive it over HTTP,
MCP or a web UI; several devkit servers can be connected and reached through any one of them.

v1 runs on macOS (Xcode, iOS devices and simulators, Instruments, Unity). Windows and Linux hosts follow in v2 and v3.

## Install (macOS)

Build the menu bar app and install it:

```sh
app/build.sh --dmg        # dist/Devkit.app and dist/Devkit.dmg
```

Open `Devkit.dmg`, drag Devkit to Applications and start it. Devkit lives in the menu bar and runs the server; from
its menu:

- **Start at Login** registers it as a login item.
- **Allow Screen Viewing…** grants the screen recording permission the web UI's live screen needs. macOS asks for
  "Devkit", not for Python.
- **Copy Owner Token** copies the admin token for the first sign-in to the web UI; **Open Devkit** opens it.

The app keeps its data (tokens, projects, jobs, files) in `~/Library/Application Support/Devkit`. It needs Xcode
(which provides `/usr/bin/python3`) and macOS 14 or later.

`build.sh` signs with the first Developer ID or Apple Development identity in your keychain (override with
`DEVKIT_SIGN_IDENTITY`). An ad-hoc signature works too, but macOS then forgets the screen recording permission after
every rebuild.

### Without the app

```sh
bin/devkit-server                    # web UI, API and MCP on http://<host>:7420; data next to the code
bin/install-launchagent              # optional: start at login as a LaunchAgent (--uninstall to remove)
```

The first start writes `config.json` with an owner token (admin). Create further tokens in the web UI under
Settings → Access tokens.

Jobs keep the Mac awake with `caffeinate` while they run (and the display, for launch and profiling jobs); an idle
devkit lets the Mac sleep as usual.

### Build identity and maintenance

`GET /api/ping` returns `version`, `build` (Git commit, dirty flag, source SHA-256), `disk`, and host `capabilities`.
The Hosts page displays the build identity. `app/build.sh` embeds `build-info.json` so the installed app identifies
its source even outside a Git checkout. Comparing only the version is insufficient: multiple builds may share it.

New jobs are refused when free space in the data volume is below `min_free_bytes` in the existing host config
(default 2 GiB). The worker rechecks before checkout/execution. This is a reserve, not an estimate of build size.

On server startup and while work is pending, the watcher wakes an idle worker. With the exclusive worker lock held,
the worker reconciles interrupted `running` jobs to `failed`, preserving artifacts and recording an interruption reason.
It never automatically replays a job, upload, or release. If a recorded PID/process group is still present or cannot
be checked, recovery stops and the queue stays blocked rather than signalling it. Job processes inherit the worker
lock, including checkout commands. Existing workers from an older app should finish before upgrading.

Artifact retention is manual and defaults to a preview:

```sh
bin/devkit cleanup --keep-last 50 --older-than-days 30
bin/devkit cleanup --keep-last 50 --older-than-days 30 --apply
```

The same operation is available to admin tokens through `POST /api/cleanup` with optional `keep_last`,
`older_than_days`, and boolean `apply` (default false). Cleanup requires an idle worker and drained queue; admission
and deletion are serialized. It removes only canonical artifact directories for terminal jobs older than the age
limit, retaining the newest N terminal jobs and every artifact source referenced by another recorded job's
`params.from_job`. Job metadata records `artifacts_expired`; checkout/import caches, credentials, configuration,
job logs, and project data are retained. There is no scheduled deletion.

## Claude Code plugin

The `plugin/` directory is a Claude Code plugin: it connects the devkit MCP server and adds a skill that teaches Claude
how to build, install, profile and release through it, plus `/devkit:status` and `/devkit:profile`.

1. In the devkit web UI, open Settings → Access tokens and create an Operator token for the agent. Settings also
   shows the address to use.
2. Install the plugin from this repository, in a Claude Code session:

   ```
   /plugin marketplace add rennerdo30/devkit
   /plugin install devkit@devkit
   ```

   Claude Code asks for the devkit address (e.g. `http://192.168.1.50:7420`) and the token. The token is kept in
   Claude Code's credential store, not in settings files.

   From a shell instead:

   ```sh
   claude plugin marketplace add rennerdo30/devkit
   claude plugin install devkit@devkit --config devkit_url=http://192.168.1.50:7420
   claude plugin configure devkit@devkit      # shows what is still missing; set the token in a session (below)
   ```

3. Change the address or token later with `/plugin configure devkit@devkit` (or `/plugin` → Installed → devkit →
   Configure).
4. Check with `/mcp`: the server shows up as `plugin:devkit:devkit`. Try `/devkit:status`.

Other MCP clients can use the endpoint directly: `POST <host>:7420/mcp` with `Authorization: Bearer <token>`.

## Interfaces

| | |
|---|---|
| Web UI | `http://<host>:7420/` |
| MCP | `POST /mcp` (streamable HTTP, JSON responses), `Authorization: Bearer <token>` |
| HTTP API | `/api/ping`, `/api/kinds`, `/api/jobs`, `/api/jobs/<id>[/log\|/artifacts\|/cancel]`, `/api/projects`, `/api/devices`, `/api/simulators`, `/api/system`, `/api/hosts`, `/api/hosts/<name>/<path>` |
| CLI | `bin/devkit <verb>` (`ping`, `queue`, `status`, `list`, `log`, `cancel`, `artifacts`, `devices`, `simulators`, `signing`, `kinds`) |

Job kinds: `build`, `test`, `archive`, `release`, `notarize`, `deploy`, `launch`, `profile`, `screenshot`, `crashlogs`,
`unity`, `unity-test`, `aab-sign`, `shell`, `echo`. `GET /api/kinds` documents their parameters.

## Unity builds, compile gates and tests (0.6.0)

`unity` defaults to `params.mode: "executeMethod"`. Existing build requests continue to work. `method` is a qualified
static Editor method; `build_target` is optional. `quit` defaults to true; set it to false for asynchronous gates that
call `EditorApplication.Exit` themselves. Return a nonzero exit code or throw on compile/gate failure. Project methods
write their output under the `DEVKIT_ARTIFACTS` environment variable.

Example `devkit_queue` arguments (also the JSON body for `POST /api/jobs`):

```json
{"project":"game","repo":"https://github.com/OWNER/GAME.git","commit":"EXACT_SHA","kind":"unity",
 "params":{"method":"CompileGate.Run","quit":false,"nographics":true,"timeout":1800}}
```

For Unity Test Framework, use `kind: "unity", params.mode: "test"`, or the equivalent `unity-test` kind:

```json
{"project":"game","repo":"https://github.com/OWNER/GAME.git","commit":"EXACT_SHA","kind":"unity-test",
 "params":{"test_platform":"EditMode","nographics":true,"timeout":1800,
           "extra":["-testFilter","Game.Tests","-assemblyNames","Game.Editor.Tests"]}}
```

Use `test_platform: "PlayMode"` for tests running in the Editor. Test jobs invoke `-runTests -testPlatform ...
-testResults <artifacts>/TestResults.xml`; they exit through the test runner and reject `quit` and `method`.
Leave `nographics` false (the default) for graphics-dependent tests. Unity always receives `-batchmode`, preventing
interactive Editor windows; callers cannot override it. Editor version comes from `ProjectSettings/ProjectVersion.txt`
unless `unity_version` is supplied. The pinned editor must already be installed in Unity Hub's standard Mac location.
The project must contain the Unity Test Framework package and test assemblies.

In the web UI, open a project → Unity build → Unity action. Choose **Build or compile gate** and an Editor method,
or **Run tests** and EditMode/PlayMode. Set **Method exits itself** for an asynchronous gate. Build target is optional;
graphics stays enabled by default. Test filters and assembly names become separate allow-listed argv values.
Xcode defaults on the saved project are not sent as Unity parameters.

`extra` is an argv list, with these accepted flags only:

- All Unity modes: `-accept-apiupdate`, `-force-metal`, `-force-glcore` (one graphics API).
- Tests: `-testFilter VALUE`, `-testCategory VALUE`, `-assemblyNames VALUE`.
- EditMode only: `-runSynchronously`, which excludes multi-frame tests; omit it for full coverage.

Unknown params, managed flags (project path, log path, results path, quit, batchmode), credential flags and malformed
argv are rejected before queueing. For project-specific arguments use `params.args`, for example
`["-gameVersion", "1.0.0"]`. Each string permits only letters, digits, underscores, dots and hyphens (128 characters
maximum, one optional leading dash). Managed flags and arguments resembling credentials are rejected. Never submit
secrets in a job: params and argv are visible in job records and logs. `extra` retains its existing allow-list.
See the official [Editor command-line reference](https://docs.unity3d.com/6000.0/Documentation/Manual/EditorCommandLineArguments.html)
and [Test Framework command-line reference](https://docs.unity3d.com/Packages/com.unity.test-framework@1.4/manual/reference-command-line.html).

The existing worker drains FIFO, one job at a time. Unity also holds `~/.local/state/devkit/unity.lock` across all
`DEVKIT_DATA` directories on the host, before checkout and until its process group is stopped and logs are captured.
Run all devkit instances under the supported single host owner account. Other user accounts and manually launched
Editors do not participate in this lock. A child inherits the lock, so worker termination cannot admit another Unity
while that child remains alive. Do not delete the lock file while a runner may be using it.

`timeout` is a positive number of seconds, capped at 14400 (four hours, the default). The deadline includes slot wait,
checkout and execution. Timeout and cancellation terminate only the job's own process group, escalating to kill after
one second; log draining is bounded. `job.log` is an artifact for every completed Unity job, including failures and
cancellations. Tests add `TestResults.xml` and `test-summary.json` when produced. Missing/malformed XML, an empty test
run, failed results or a nonzero Editor exit fail the job. Partial results remain fetchable after failure/timeout.

Use `devkit_artifacts` or `GET /api/jobs/<id>/artifacts` for sizes and SHA-256. Use `devkit_read_artifact` for XML,
summary and logs, or download `GET /api/jobs/<id>/artifacts/<path>` (streaming and byte ranges supported).
`devkit_log` and the existing log API retain live output. Pass the returned host to MCP queries for a forwarded job.

### Nested projects and exported builds

Set `params.project_dir` for a Unity project below the repository root. It must be a relative directory containing
`ProjectSettings/ProjectVersion.txt`, even if `unity_version` is specified. Absolute paths, `..` components and symlinks
escaping the checkout are rejected. Omitting it preserves the existing root-project behavior.

For build methods that write outside `DEVKIT_ARTIFACTS`, `params.collect` copies repo-relative files or directories
after a successful Editor run (and passing results for test jobs). Each output keeps its last path component.
Missing paths, traversal, absolute or escaping copied symlinks, cycles and artifact-name collisions fail clearly.
Runner outputs (including job.log, job.json and test results) are reserved. Copies preserve symlinks and use APFS
clones where available, with a normal-copy fallback; both obey cancellation and the Unity deadline. The copied tree
is validated before acceptance. Paths are relative to the repo, including when project_dir is set.

```json
{"project":"game","repo":"https://github.com/OWNER/GAME.git","commit":"EXACT_SHA","kind":"unity",
 "params":{"project_dir":"unity","method":"Build.ExportIOS","build_target":"iOS",
           "args":["-gameVersion","1.0.0"],"collect":["unity/Builds/iOS"]}}
```

Queue `archive` with `target: "ios"` and params such as
`{"from_job":"SOURCE_JOB_ID","project":"iOS/Unity-iPhone.xcodeproj","scheme":"Unity-iPhone","export_method":"app-store-connect"}`
to produce an IPA. Automatic provisioning and the configured `asc_api_key` authentication continue to work as before.

An owner can allow environment values for all Unity Editor runs in host `config.json`:

```json
{"unity_env":{"UNITY_TOOLS_PYTHON":"/path/to/venv/bin/python"}}
```

Only host configuration supplies this allow-list; jobs cannot submit `env`. Values must be strings without control
characters (maximum 4096 characters). Values whose variable names resemble secrets are masked in Editor output.
The interpreter and its environment must already exist on the build host.

### Signed Android bundles

Use a Unity Android build method with `collect` to retain its unsigned or previously signed AAB, then queue:

```json
{"project":"game","commit":"none","kind":"aab-sign","target":"android",
 "params":{"from_job":"SOURCE_JOB_ID","aab":"Android/game.aab",
           "keystore_path":"/path/to/signing.keystore","alias":"upload",
           "keychain_service":"example-signing","keychain_account":"upload"}}
```

The source job must have succeeded on the same host. `aab` stays inside its artifacts; the keystore must be a regular
host file outside the job checkout. No checkout or Xcode is needed. A JDK is located using `JAVA_HOME`, then
`/usr/libexec/java_home` (or tools on PATH when no Java home is available). The key's store and key passwords must
match the generic password already provisioned in Keychain under the given service/account.

The job rewrites a copy, stripping `META-INF/*.SF`, `*.RSA`, `*.EC`, `*.DSA` while retaining `MANIFEST.MF`, signs with
SHA256withRSA/SHA-256, then runs `jarsigner -verify -strict -certs`, requiring a verified result without warnings.
The signed bundle's certificate must report at least RSA 2048 or EC 256. The password is captured in memory, supplied only through
the signing child's environment and masked from its output; it is never added to argv, job params or artifacts.
The resulting `aab-sign.json` records the signed AAB's artifact-relative `path`, lowercase SHA-256, byte `size`
and lowercase `signer_cert_sha256` from `keytool` (without colons). After signature verification, manifest metadata
comes from `bundletool` on PATH when present, otherwise from Android SDK `aapt2`. SDK discovery checks
`ANDROID_HOME`/`ANDROID_SDK_ROOT`, or the standard macOS Android SDK location, selecting the highest executable
build-tools version, then falls back to PATH. The aapt2 fallback wraps the bundle's protobuf base manifest in a
temporary ZIP for `dump xmltree`; it does not dump the AAB directly. The report always includes `package`,
`versionCode` (a positive JSON integer), `versionName` and `manifest_source` (`"bundletool"`, `"aapt2"` or null).
Unavailable or invalid identity fields stay null with a `manifest_note`; parsed `minSdk`/`targetSdk` integers are
also included when available. If neither tool is available, identity fields and `manifest_source` remain null
with a skip note. This kind signs locally and does not upload to a store.

### Tests

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_ui.cjs
node --check web/app.js
```

Schema tests validate every advertised tool against JSON Schema draft 2020-12 and require all 16 tools, including
`devkit_queue`, for every role. Tool input schemas use a plain object at the root: Claude's API rejects top-level
`allOf`, `oneOf` and `anyOf` even though they are valid JSON Schema. Unity's conditional rules are enforced by the
server before a job is saved or a worker starts; the queue schema documents them without root combinators.

The runner-only checks can also run without the schema-test dependency:

```sh
python3 -m unittest discover -s tests -p test_unity.py -v
python3 -m unittest discover -s tests -p test_runner.py -v
python3 -m unittest discover -s tests -p test_mcp.py -v
```

Tests use disposable editor executables and temporary job stores; no credentials, Unity license, Mac, or network
are required. POSIX tests exercise real process groups, TERM-resistant processes, deadlines under continuous output,
host slot exclusion and the MCP queue → status → artifacts → read flow. Windows runs the argument/result tests and
skips POSIX host tests. Native Unity EditMode/PlayMode acceptance must be run on the Mac after the owner updates it.

### Update the Mac host (owner-operated)

This change is source-only; no running Mac checkout or service has been changed. Before updating, stop submissions
and let all queued/running jobs become terminal in the web UI. Existing detached workers must finish before restarting.
Keep the same OS account, data directory, existing credentials and service start method. Do not print configuration
or credential files. In the Mac's `~/Development/devkit` checkout:

```sh
cd ~/Development/devkit
git status --short                    # stop and preserve any source changes
git fetch origin feature/unity-gates-tests
git log -1 --oneline origin/feature/unity-gates-tests
git branch backup/before-unity-gates HEAD
git switch -c update/unity-gates-tests --track origin/feature/unity-gates-tests
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
```

Choose the restart procedure matching the current installation:

- Source LaunchAgent: `bin/install-launchagent` reinstalls/restarts `dev.devkit.server` from this checkout.
  If a custom LaunchAgent supplies `DEVKIT_DATA` or other settings, preserve that plist and instead run
  `launchctl kickstart -k gui/$(id -u)/dev.devkit.server`.
- Manual source server: stop the existing server in its terminal and start `bin/devkit-server` with the same
  `DEVKIT_DATA`, port and environment as before.
- Menu bar app: Quit Devkit from its menu; the app bundles its own Python sources, so a source checkout update alone
  is insufficient. Preserve the installed app, run `app/build.sh`, then install and start the rebuilt app:

  ```sh
  backup_dir="$HOME/Devkit-backups/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$backup_dir"
  ditto /Applications/Devkit.app "$backup_dir/Devkit.app"
  app/build.sh
  ditto dist/Devkit.app /Applications/Devkit.app
  open /Applications/Devkit.app
  ```

  Use the existing signing identity; an ad-hoc rebuild can reset screen recording permission. App data stays at
  `~/Library/Application Support/Devkit`; do not replace or erase it. Run only one installation at a time.

Reconnect/reload MCP so callers receive the new tool schema; `initialize` must report version `0.6.0` and
`devkit_kinds` must include `unity-test`. Verify a self-exiting compile gate without `build_target`, then one EditMode
and one PlayMode job on exact commits. Fetch XML and `job.log`; compare artifact checksums. Finally verify a short
timeout and two queued Unity requests. Retain native acceptance evidence separately from the fixture test results.
Rollback source code to `backup/before-unity-gates` and restart the same installation if needed; retain all runtime data.

## Access

Tokens have one of three roles: viewer (read), operator (run and cancel jobs, edit projects, view the screen),
admin (also manage tokens and connected hosts). Only SHA-256 hashes of tokens are stored. Traffic is plain HTTP, so
use it on a trusted network or put TLS in front of it; an operator token can run arbitrary shell jobs.

## Connected hosts

On host B, create an operator token named after host A. On host A, open Hosts → Connect a host and enter B's address
and that token. Jobs can then target B explicitly or use `host: "auto"`, which picks an online host running the
target's platform with the shortest queue. Requests are forwarded at most one hop.

Automatic routing also requires the advertised job kind/target, disk readiness, any explicitly requested Unity
editor version, and the device/simulator ID. For additional constraints, send e.g.
`"requires":{"xcode":"26.0","sdk":"iphoneos26.0","simulator_runtime":"iOS-26-0"}` with `host:"auto"`.
These strings must match advertised `capabilities`; `unity_version` is also accepted in `requires`. Hosts missing
required facts are excluded. Supply `params.unity_version` or `requires.unity_version` when automatic placement
must match an exact editor; the router does not fetch a project's pinned commit to discover its editor version.
Requirements filter automatic placement; they do not switch Xcode installations or install SDKs/editors.

CI runs Python regressions and JavaScript checks on GitHub-hosted Linux and macOS runners for this public repository,
plus a Swift compilation on macOS. The workflow uses pinned action releases verified on 2026-10-22:
[checkout 7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and
[setup-python 7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0), both published 2026-07-20.
Tests use temporary stores and command fixtures; native device, signing, Unity acceptance and installed-app updates
remain separate checks. Windows and Linux execution hosts remain outside the macOS v1 implementation.

## Layout

```
bin/devkit          job queue, worker and CLI
bin/devkit-server   HTTP server: web UI, API, MCP, peers
lib/                job kinds, host facts, tokens, peers
web/                web UI (plain HTML, CSS, JS; English and German)
app/                macOS menu bar app (Swift) and its build script
launchd/            LaunchAgent template for running without the app
plugin/             Claude Code plugin (MCP connection, skills)
.claude-plugin/     plugin marketplace manifest
```

Data (`config.json`, `tokens.json`, `projects.json`, `jobs/`, `artifacts/`, ...) lives in `$DEVKIT_DATA` if set
(the app sets it to `~/Library/Application Support/Devkit`), otherwise next to the code. `DEVKIT_PORT` overrides the port.
