---
description: Run builds, installs, launches, Instruments profiling, tests, screenshots and releases on remote devkit hosts (Xcode, iOS devices and simulators, macOS, Unity). Use when the user wants to build or run an app or game on a device, profile performance, get crash logs, ship to TestFlight, or check what the devkit is doing.
---

# Working with devkit

Use only the `devkit_*` MCP tools. If they are not available, the plugin is not connected: do not fall back to curl,
Bash or the HTTP API. Tell the user to run `/plugin configure devkit@devkit` (devkit address and token), then `/mcp`
to reconnect, and stop there.

Devkit hosts run jobs one at a time per host, in order. You talk to them through the `devkit_*` MCP tools of the
`devkit` server. One server can forward to every connected host, so `host` is just a parameter.

## Before queueing

1. `devkit_projects`: if the project is saved, take `repo`, `ref`, `xcode` (→ `params.project` or `params.workspace`),
   `scheme`, `bundle_id`, `target` and `device` from it instead of guessing.
2. `devkit_kinds` once per session: the parameters of each job kind.
3. For a physical device, `devkit_devices` gives ids; for a simulator, `devkit_simulators`. Use the id as `device`.
4. `devkit_hosts` when more than one host exists. Use `host: "auto"` when any matching machine will do.

## Queueing

`devkit_queue` with `project`, `kind`, `commit` (a branch, tag or SHA; `"none"` for kinds that need no checkout such as
`launch`, `profile`, `screenshot`, `crashlogs`), and `target` (`ios`, `ios-sim`, `macos`). The result contains `id` and
`host`; pass that `host` to every later call about the job.

Common jobs:

| Goal | kind | key params |
|---|---|---|
| Build | `build` | `scheme`, `project`/`workspace`, `configuration` |
| Install and start | `deploy` | as build, plus `launch: true`, `launch_args`, `duration` |
| Start an installed app | `launch` | `bundle_id`, `launch_args`, `env`, `duration` |
| Profile | `profile` | `bundle_id` (device/simulator) or `app` (macOS), `template` (default Time Profiler), `duration` |
| Tests | `test` | `scheme`; result bundle in artifacts |
| TestFlight / notarized Mac build | `release` | `scheme`, `team_id` |
| Unity batch build | `unity` | `build_target`, `method` |

To build what an earlier job produced (for example the Xcode project a `unity` job exported), pass that job's id as
`params.from_job` and give `project`/`workspace` relative to its artifacts, e.g.
`{"from_job": "<unity job id>", "project": "iOS/Unity-iPhone.xcodeproj", "scheme": "Unity-iPhone"}` with `commit: "none"`.
The earlier job must have succeeded on the same host.

Pass arguments for the game in `params.launch_args` as a list, for example `["-mute", "-autoplay"]`.

## Waiting and results

- Poll `devkit_status` every 10–30 seconds. Don't sleep for long fixed periods. It has `state`, per-step timing in `steps`
  and, when a job fails, a plain-language `error`. Report that `error` to the user rather than dumping the log.
- `devkit_log` with `tail` for the last lines only. Logs of Xcode builds are long.
- `devkit_artifacts` lists files; `devkit_read_artifact` returns a text file's contents. After `profile`,
  `profile-summary.json` holds the hottest functions with percentages; summarize the top entries. The full trace is `profile.trace.zip` for Instruments.
- `devkit_cancel` stops a job you started by mistake.

## Things that commonly fail

- "device is locked": ask the user to unlock the phone, then run the job again.
- "No Account for Team" / no provisioning profiles: the Mac needs an Apple account in Xcode → Settings → Accounts.
- Release and notarize need App Store Connect / notary credentials on the host; `devkit_signing` shows what is set up.
- A 403 means the token's role is too low (viewer can only read, operator can run jobs).

Don't run destructive shell jobs (`kind: shell`) unless the user asked for that exact command.
