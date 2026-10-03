---
name: wi
description: WI's last run before pausing was killed by GitHub-hosted runners' 6-hour execution cap, after actually starting (unlike FL/MA's queue-wait cancellations) -- likely needs the same self-hosted + longer-timeout fix FL already got. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Wisconsin

## Status: 🟡 Unresolved — likely needs FL's fix, not yet confirmed

**Paused state** as of this writing. Last run before pausing:
[36558777664](https://github.com/govbot-openstates-scrapers/wi-legislation/actions/runs/36558777664)
(2026-09-29).

## What's wrong

```
The job has exceeded the maximum execution time of 6h0m0s
```

Cancelled — the job actually **started and ran for the full 6 hours** before GitHub-hosted
runners' hard execution cap killed it. No `audit-summary.json` was produced at all, meaning
the run likely has nothing recoverable from it.

**This is a different failure shape than FL/MA's "awaiting a runner for 24h0m0s"**
(see `fl.md`) — those jobs never started at all (a runner-queue wait timeout); WI's job did
start and simply ran out of time mid-scrape. Different root cause, same symptom class
(a scrape that needs more time than its current infra allows).

## Root cause

Not yet confirmed whether WI's workload genuinely needs more than 6 hours, or this was a
one-off slow run (e.g., target site slowness that day). FL hit the same general class of
problem and was moved to `runner: self-hosted` + a raised `scrape_timeout_minutes` (see
`fl.md`'s 2026-07-13/14 and 07-21 entries) — WI may need the identical treatment, but this
hasn't been confirmed by checking WI's actual historical scrape duration/data volume.

## What would actually fix this

If confirmed WI genuinely needs more time: the same fix FL got — `runner: self-hosted` in
`chn-openstates-scrape.yml` plus a per-locale `scrape_timeout_minutes` override. Not applied
yet; needs the duration check first.

## Timeline

- **2026-09-29**: hit on WI's last run before being paused for session-end.
- **2026-10-03**: found during the 47-paused-state audit.

## Related

- `fl.md` — same general class of problem (runner can't accommodate scrape duration),
  already has a confirmed fix pattern to potentially reuse.
- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
