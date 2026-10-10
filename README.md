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
`unity`, `unity-test`, `shell`, `echo`. `GET /api/kinds` documents their parameters.

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

`extra` is an argv list, with these accepted flags only:

- All Unity modes: `-accept-apiupdate`, `-force-metal`, `-force-glcore` (one graphics API).
- Tests: `-testFilter VALUE`, `-testCategory VALUE`, `-assemblyNames VALUE`.
- EditMode only: `-runSynchronously`, which excludes multi-frame tests; omit it for full coverage.

Unknown params, managed flags (project path, log path, results path, quit, batchmode), credential flags and malformed
argv are rejected before queueing. Arbitrary project-specific flags require a reviewed extension of the host allow-list.
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

### Tests

```sh
python3 -m unittest discover -s tests -v
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
python3 -m unittest discover -s tests -v
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
