# Devkit

A remote build, deploy, release and profiling host for games and apps. Agents and people drive it over HTTP,
MCP or a web UI; several devkit servers can be connected and reached through any one of them.

v1 runs on macOS (Xcode, iOS devices and simulators, Instruments, Unity). Windows and Linux hosts follow in v2 and v3.

## Run

```sh
bin/devkit-server            # web UI, API and MCP on http://<host>:7420
```

The first start writes `config.json` with an owner token (admin). Create further tokens in the web UI under
Settings → Access tokens. Requirements: `/usr/bin/python3` (stdlib only), Xcode, optionally Unity Hub.

Start at login (macOS):

```sh
bin/install-launchagent              # writes ~/Library/LaunchAgents/dev.devkit.server.plist and loads it
bin/install-launchagent --uninstall
```

Jobs keep the Mac awake with `caffeinate` while they run (and the display, for launch and profiling jobs); an idle
devkit lets the Mac sleep as usual.

## Claude Code plugin

The `plugin/` directory is a Claude Code plugin: it connects the devkit MCP server and adds a skill that teaches Claude
how to build, install, profile and release through it, plus `/devkit:status` and `/devkit:profile`.

1. Create a token for the agent in the web UI (Settings → Access tokens, role Operator).
2. Make the address and token available to Claude Code, e.g. in `~/.zshrc`, then restart Claude Code:

   ```sh
   export DEVKIT_URL="http://<host>:7420"   # defaults to http://localhost:7420
   export DEVKIT_TOKEN="<token>"
   ```

3. Install the plugin from this repository:

   ```sh
   claude plugin marketplace add rennerdo30/devkit
   claude plugin install devkit@devkit
   ```

   or inside a session: `/plugin marketplace add rennerdo30/devkit`, then `/plugin install devkit@devkit`.

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
launchd/            LaunchAgent template for macOS (installed by bin/install-launchagent)
plugin/             Claude Code plugin (MCP connection, skills)
.claude-plugin/     plugin marketplace manifest
```

Data (`config.json`, `tokens.json`, `projects.json`, `jobs/`, `artifacts/`, ...) lives next to the code, or in
`$DEVKIT_DATA` if set. `DEVKIT_PORT` overrides the port.
