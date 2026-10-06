---
description: Show what the devkit hosts are doing right now.
disable-model-invocation: true
---

Give a short status of the devkit:

1. Call `devkit_hosts`. For each host: name, platform, online or not, the running job and how long it has run, and how
   many jobs are waiting.
2. Call `devkit_list` with `limit: 10` and mention failed jobs from the last hour with their `error`.
3. Call `devkit_devices` and list connected phones (model and iOS version).

Keep it to a few lines. Don't start any jobs.
