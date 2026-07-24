# Staleness Audit — Spec for a Recurring Health Check

**Status:** Not built yet. This is a spec for a future session to implement, written after
manually running this exact audit once (2026-07-14) and finding a real, months-old problem
it would have caught immediately.

## The problem this solves

A `govbot-data/{state}-legislation` repo can look completely healthy — thousands of bill
files, a green checkmark on every scheduled workflow run — while actually having received
**zero real new data for months**. This isn't a hypothetical: on 2026-07-14, a manual audit
found **16 states plus the USA/federal repo** frozen at the exact same commit,
2025-12-14 23:31–23:41 UTC, over 7 months stale. Nobody had noticed, because:

1. Old bill counts sitting in the repo look fine at a glance — a repo with 1,794 bills
   looks "more done" than one with 50, even if the 1,794 is 7 months old and the 50 is
   current.
2. The automated pipeline is deliberately built to never hard-fail (`scrape.sh` retries,
   then falls back to a stale "nightly" tarball rather than erroring) — so a scraper
   silently getting empty/unchanged results every day still shows a green checkmark,
   forever.
3. **The most misleading trap**: `govbot-data` repos get a commit *every single day*
   regardless of whether real data changed — it's `.windycivi/last-processed-sha` getting
   bumped as a tracking file. Naively checking "when was the last commit" gives a
   meaningless answer (often "today," even for a repo that's been dead for months). You
   have to filter commits to ones that actually touched a file under
   `country:us/state:{code}/sessions/`.

## What almost went wrong doing this manually

Worth internalizing before automating this: the first manual pass over these 16 states
almost mis-diagnosed the cause. NC turned out to just need `runner: self-hosted` flipped —
but the evidence for that ("works fine when I curl it from a non-Azure IP") is
**indistinguishable** from "this state is Azure-IP-blocked and needs the same fix for a
totally different underlying reason" (which IL, WV, CT, HI, MA, and TN all turned out to
be, earlier in this same investigation). A tool that just flags staleness is safe. **A tool
that tries to auto-diagnose *why* a state is stale will get it wrong sometimes** — keep
diagnosis as a human-in-the-loop step, and don't assume one state's root cause explains the
next state's identical symptom.

## What to build

A script (start from `/tmp/audit_states_v2.sh`-style logic below — that exact script was run
once manually on 2026-07-14 and is the reference implementation; it doesn't exist in the
repo yet) that, for every `govbot-data/*-legislation` repo:

1. **Finds the real last-data-commit date** — the most recent commit whose diff actually
   touches something under `country:us/state:{code}/sessions/`, via
   `gh api repos/govbot-data/{repo}/commits?path=country:us/state:{code}/sessions&per_page=1`.
   Do **not** use the plain "last commit" — see the tracking-file trap above.
2. **Cross-references against the session calendar**
   (`actions/scrape/docs/session-dates/session-calendar-2026.md`, itself sourced from
   LegiScan and needing its own periodic refresh — see that file's "Source: ... updated"
   line) to know which states *should* currently have active legislative business.
3. **Flags anomalies**, roughly:
   - Any state marked "in session" per the calendar with no real data commit in the last
     ~3 days (most active scrapers run nightly; a few days' gap is a real signal, not
     noise).
   - Any large cluster of states going stale at the *same* timestamp, regardless of session
     status — that clustering (not the staleness itself) is what points to something
     systemic rather than 16 independent per-state problems. A gradual per-state staircase
     (sessions naturally winding down at different points through the year) is normal and
     not worth flagging; a hard cliff shared by many unrelated states on the same day is
     the interesting signal.
   - Optionally: bill-count-per-session breakdown (via the git tree, grouping
     `sessions/{id}/bills/*/metadata.json` by session id) to catch the "IL pattern" —
     healthy-looking total count, but the *current* session's bucket is suspiciously small
     or absent relative to what the site itself shows.

## Suggested cadence & delivery

- Not every day — this is a slow-moving signal (staleness) and doesn't need daily polling.
  Weekly, or triggered manually, is probably right. Consider a GitHub Actions
  `schedule:` cron in this repo (`chihacknight/govbot`, not the generated per-state repos)
  so it doesn't depend on Tamara remembering to run it.
- Output should be something skimmable in under a minute — a markdown table or a GitHub
  issue that gets updated in place (similar in spirit to `check-sessions.py`'s existing
  role of flipping `chn-openstates-scrape.yml` templates based on session status — this is
  the same kind of "automation that watches automation" tool, just for data freshness
  instead of session dates).
- Whatever the output format, it should distinguish "flagged, not yet investigated" from
  "investigated, cause identified" — so a recurring run doesn't re-surface the same known
  issue every week as if it were new. `scraper-health.md` (archived 2026-07-24, no longer in
  the repo -- see docs/src/state-status-reference.md for the current per-state reference
  instead) played that role manually; the automated report could plausibly open/update a
  tracking issue that links back to the new reference doc once a state's been looked at.

## Reference: what a first pass actually found (2026-07-14)

For calibration when building/testing this — the real numbers from the one manual run so
far:

- Frozen at 2025-12-14 (7+ months stale): `usa, ak, ar, il, in, mi, nc, ne, nm, nv, ny, oh,
  pa, sc, vi, vt`
- Gradual staircase after that, tapering through Jan–June as sessions wound down normally
  (not inherently a problem — full breakdown was in the now-archived `scraper-health.md`)
- Of the frozen 16, only `nc`, `il`, `wv` (not itself in the frozen-16, but the same
  symptom), and `ar` have been individually investigated as of this writing. `nc` was a
  config gap (never set to self-hosted); `il`/`wv` were confirmed Azure IP blocks. `ar` is
  suspected Azure-blocked (FTP file confirmed to have the right data when fetched directly)
  but not yet confirmed via a live dispatch. The rest of the frozen 16 are unverified — see
  `[[project-govbot-state-specific-followups]]` (Claude memory) for current status.
