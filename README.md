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
`unity`, `shell`, `echo`. `GET /api/kinds` documents their parameters.

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
