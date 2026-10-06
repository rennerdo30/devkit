---
description: Profile an app or game on a devkit device and summarize where the time goes.
argument-hint: "[project or bundle id] [seconds] [Instruments template]"
disable-model-invocation: true
---

Profile on the devkit: $ARGUMENTS

1. Resolve what to profile. Look the first argument up in `devkit_projects` (by name) for `bundle_id`, `target` and
   `device`; otherwise treat it as a bundle id. If no device is known, ask which one from `devkit_devices` or
   `devkit_simulators`.
2. Queue `kind: "profile"`, `commit: "none"`, with `params.bundle_id`, `params.duration` (default 30) and
   `params.template` (default "Time Profiler"). Use the project's `launch_args` if the user gave any.
3. Poll `devkit_status` until it finishes. If it fails, report `error` and stop.
4. Read `profile-summary.json` with `devkit_read_artifact` (same `host` as the job) and summarize the top 10 functions: what dominates, which belong to the game versus system
   frameworks, and one or two concrete things worth looking at.
5. Mention that `profile.trace.zip` can be opened in Instruments for detail.
