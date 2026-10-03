---
name: ma
description: MA's last run before pausing was cancelled waiting 24h for a runner to pick it up -- same shape as FL's known issue, never actually started. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Massachusetts

## Status: 🟡 Unresolved on this specific run — but MA has a longer separate history (see below)

**Paused state** as of this writing. Last run before pausing:
[36553854027](https://github.com/govbot-openstates-scrapers/ma-legislation/actions/runs/36553854027)
(2026-09-29).

## What's wrong (most recent finding)

```
The job has exceeded the maximum execution time while awaiting a runner for 24h0m0s
```

Cancelled — the job never started at all; it sat waiting for a self-hosted runner to pick it
up for 24 hours. Identical shape to FL's same-day cancellation (see `fl.md`) — this is a
runner-availability/queue problem, not an execution-time cap (contrast with `wi.md`, which
did start and ran out of time mid-scrape).

## Root cause

Not independently re-diagnosed here — same class of problem as FL's, which traces to
self-hosted runner availability/queue depth at the time. Whether this is a one-off (both FL
and MA happening to queue at a bad moment) or a recurring capacity problem across
self-hosted-runner states generally hasn't been checked.

## Historical note

MA has older history not covered here: `self.warning("Server Error on {}")` in `ma/bills.py`
silently dropped ~210-218 bills per run for over a month (confirmed across real runs
2026-07-01 through 2026-08-07) while every run reported `success` — this was the original
motivating bug for PR #187's WARNING-level detection work (see
`actions/openstates-scrape-audits/README.md`). Not yet confirmed whether that specific bug
is still present; the warning-detection fix means it would at least now be visible if it
recurs, rather than invisible.

## Timeline

- **2026-07-01 → 2026-08-07** (approx.): the `self.warning("Server Error...")` silent-drop
  issue, pre-dating this file.
- **2026-09-29**: the runner-queue-wait cancellation documented above.
- **2026-10-03**: found during the 47-paused-state audit.

## Related

- `fl.md` — identical runner-queue-wait cancellation shape, same day.
- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
