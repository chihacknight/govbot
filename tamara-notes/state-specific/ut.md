---
name: ut
description: UT's session-list lookup failed on its last run before pausing -- CommandError, falls into the UNKNOWN bucket, not yet root-caused. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Utah

## Status: 🟡 Unresolved — not yet root-caused

**Paused state** as of this writing. Last run before pausing:
[36567835074](https://github.com/govbot-openstates-scrapers/ut-legislation/actions/runs/36567835074)
(2026-09-29).

## What's wrong

Classified `UNKNOWN`:

```
openstates.exceptions.CommandError: no sessions from Utah.get_session_list()
```

`get_session_list()` returned empty, which the openstates CLI treats as a hard error rather
than "no active sessions, nothing to do." Falls into `scrape.sh`'s catch-all bucket since
`CommandError` isn't one of the recognized patterns.

## Root cause

**Not yet traced.** Open question (noted in `paused-states-audit-2026-10.md`): is this a
real scraper defect in `scrapers/ut/__init__.py`'s session-list logic, a transient site
issue on Utah's legislature site, or an expected-but-mishandled consequence of UT being
out of session when this ran (i.e., should an empty session list out-of-session be a soft
no-op, not a crash)? Not distinguished yet.

## Historical note

UT also has a prior, separate finding: 6 consecutive days of byte-identical scrape output
in July 2026 while every run reported `success` — the original motivating case for building
`new_bills_seen` (see `actions/openstates-scrape-audits/README.md`). That was a *different*
problem (silent non-discovery) from this one (an outright crash). Worth keeping both in mind
if UT keeps coming up.

## Timeline

- **2026-09-29**: hit on UT's last run before being paused for session-end.
- **2026-10-03**: found during the 47-paused-state audit.

## Related

- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
