---
name: co
description: CO hit a genuine, correctly-classified rate-limit error on its last run before being paused. Low priority -- not a code bug or false positive, just needs a retry. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Colorado

## Status: 🟢 Low priority — likely transient, correctly diagnosed

**Paused state** as of this writing. Last run before pausing:
[36564841132](https://github.com/govbot-openstates-scrapers/co-legislation/actions/runs/36564841132)
(2026-09-29).

## What's wrong

Classified `H3_RATE_LIMITED` — and unlike USA's `H3_RATE_LIMITED` misclassification (a bare
"429" false-matching a logged bill number, see `usa.md`), **this one is genuinely correct**:

```
scrapelib.HTTPError: 429 while retrieving https://leg.colorado.gov/committee_meeting_hearing_items/30532/votes/44888
```

A real HTTP 429 from `leg.colorado.gov` fetching a committee vote.

## What would actually fix this

Nothing needed beyond a retry on next dispatch — this is normal rate-limiting behavior, not
a bug. Worth rechecking once CO comes off pause for its next session to confirm it isn't a
persistent pattern (unlikely based on a single occurrence, not yet confirmed either way).

## Timeline

- **2026-09-29**: hit on CO's last run before being paused for session-end.
- **2026-10-03**: found during the 47-paused-state audit (see
  `paused-states-audit-2026-10.md` in `archived_docs/` for the full audit this was part of).

## Related

- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
