# State auditor, version 1: the build plan

Written 2026-11-26 by the reviewing chat, after the session-status re-audit. For the chat that
builds it, and for Tamara. **Draft: Tamara reviews it before any building starts.**

> **What version 1 is:** one daily job that reads the newest raw scrapes, GitHub's run history and
> the session calendar, and keeps four short lists in one GitHub issue: **needs you**,
> **heads-up**, **ready to turn off**, **turn back on**. It never changes a scraper or a data repo.
> The rules are the ones the 2026 replay settled on (`session-status-brief.md`, Progress,
> "three-list replay, revised" and after). The target is about 2 new "needs you" items in a
> normal week.

## Why this shape

- **Tamara is the only person maintaining this data, in her free time.** The job must run with
  nobody watching, and should only ask for her attention when something is real and actionable.
- **It must not depend on her laptop or the home runner,** so it runs on GitHub-hosted Actions.
- **The rules are already written and tested** as replay code in
  `actions/openstates-scrape-audits/sessions/` (`status.py`, `lists.py`) and `history/`
  (`scan.py`'s checks). Version 1 runs the same rules forward, one day at a time. It doesn't
  invent new ones.

## What it reads

| Input | How | Size |
|---|---|---|
| The newest raw scrape per state | A shallow fetch of each `govbot-openstates-scrapers/<st>-legislation` (public, no token) | Today's trees total about 2 GB of JSON for all 56 states (measured 2026-11-26: NY 156 MB, USA 82 MB, most a few MB) |
| What it knew yesterday | A small state database (per state: the last scrape read, each bill's content hash and fields, open items), kept between runs | Tens of MB |
| Run history | GitHub's Actions API for each raw repo | A few calls per state |
| Session calendar | `sessions.csv` + the "accepted" file (both hand-correctable) | Small |
| MultiState (weekly) | The PDF linked from `multistate.us/resources/<year>-legislative-session-dates`, after checking their terms | 60 KB |
| Congress | congress.gov API (`/v3/congress/<n>`), with a free api.data.gov key as a secret | One call |

**The one real technical risk: keeping yesterday's state.** `scan.py` re-reads a state's whole
history, which takes hours. Version 1 needs an incremental mode: read only the scrapes after the
saved cursor (`runs.cursor_sha`, already in the schema "for incremental runs later"), comparing
against the stored hashes. Keep the state database in `actions/cache`. A daily job keeps it from
being evicted; save a weekly artifact as a backup. **If the cache is lost,** rebuild from the last
120 days of history (a slower run), never start blank, and say so in the issue.

## Timing: running while scrapes are still going

Measured from 2026's successful scheduled runs (`session-status/runs/`): scrapes are scheduled for
06:00 UTC but GitHub starts them later, at a median of about 09:00 UTC. 37 of 56 states usually
finish in under an hour. The long ones (90th percentile): FL 4.9 h, MA 4.6 h (worst 23 h), GA 3.4,
NE 3.1, NY 3.0, USA 2.5. Across all runs, half end by 10:00 UTC, 90% by 12:30, 99% by 18:00.

- **No clash.** The audit only reads. A git commit lands all at once, so the audit sees either the
  previous scrape or the new one, never half of one. It runs in `chihacknight/govbot` on GitHub's
  servers, so it doesn't compete with the scrapers for runners or the home runner.
- **The real risk is judging too early,** for example calling MA "no scrape today" while its
  20-hour scrape is still running. **Rule:** a state is judged only on completed runs. A day whose
  run is still queued or in progress counts as "still running": like an off day, it neither counts
  toward a limit nor resets one. A run queued or in progress for more than 24 hours counts as a
  failed day (the 2026 FL and MA runs cancelled waiting for the home runner).
- **When:** daily at 20:00 UTC (2 pm Chicago in winter), after almost every scrape and well before
  the next day's. The issue is ready when Tamara gets home from school.

## Never reading the same scrape twice

- **A scrape is its raw commit** (sha + commit time), never a date or the audit's run time.
- **Per state, the audit keeps a cursor:** the last scrape commit it read. Each run reads only the
  scrape commits after the cursor, oldest first, then moves the cursor. A commit is never read
  twice.
- **Two cases stay apart:**
  - no new scrape commit since the cursor: the scraper was off, failed or is still running (run
    history says which);
  - a new commit with the same content, compared without `scraped_at` / `_id`, as `scan.py` does:
    the scraper ran and found nothing new (the freeze case).
- **The cursor and state are saved only at the end of a run, all at once.** A crashed run saves
  nothing; the next run redoes it.
- **A re-run of the audit** starts from the same cursor and gets the same answer.
- **Lost or older saved state:** an older cursor just means reading more commits.
- **Two scrape commits in one day** (a manual re-run): each is its own scrape, compared with the
  one before it.
- **The cursor's commit missing from history** (it shouldn't be: history is never rewritten):
  report it under "health" and rebuild from the last 120 days.
- **Test:** run the audit twice on the same inputs and get the same issue; run it with a cursor
  from 3 days back and get the same result as three daily runs.

## What it writes

**One GitHub issue, rewritten every run.** Editing an issue's body sends no notifications, so it
stays quiet. Layout:

1. **Needs you:** one line per item: state, what's wrong, since when ("day N"), and a link to the
   evidence (the commit, the run, the source PDF). New items first.
2. **Known ongoing:** items open more than 30 days, once a week, with their day count.
3. **Ready to turn off** and **turn back on:** one line each, with the evidence.
4. **Heads-up:** what may need her next week, plus the one-line digest of out-of-session quiet
   states.
5. **Health of the auditor itself:** last successful run, any input it couldn't read, and the age
   of the newest LegiScan PDF and MultiState fetch.

**Optional, Tamara's call:** one comment a week listing only the new "needs you" items, which does
notify. Everything else lives in the issue body and the job log.

**The "accepted" file** (next to `sessions.csv`): one line per item Tamara has decided to live
with (state, kind, reason, date). Accepted items move to the log.

## Build order

Each step has offline tests on small snapshots (`__snapshots__/`), as the repo expects.

1. **A home for the code.** A new action, `actions/state-auditor/`, with its own `action.yml`
   (repo rule: actions must work as GitHub Actions). Move in what it needs from `sessions/` and
   `history/`; leave the history tools where they are. `sessions.csv`, the PDFs and the "accepted"
   file move with it, since CI must read them.
2. **Incremental scan.** Read only the scrapes after the cursor, and produce the same per-scrape
   facts `scan.py` produces. **Test: feeding the scrapes one at a time ends with the same database
   as a full scan.**
3. **Live lists.** `lists.py`'s rules, computed for "today" from the state database plus run
   history, instead of replayed over a year. **Test: run the live path day by day over
   2026-09-01 to 09-29 and get exactly the lists the replay gives for those days.**
4. **The issue writer,** with a dry-run mode that prints the markdown instead of posting it.
5. **The workflow:** daily at 20:00 UTC (see "Timing"); weekly, the
   MultiState fetch and the Congress call, each rebuilding `sessions.csv` and reporting changed
   rows. Least access: read-only for contents, `issues: write` only for the one issue.
6. **Fail-soft everywhere.** A state that can't be read is listed under "health" and skipped; the
   rest still run. A source that fails keeps its last good copy and says so.
7. **Dry run until the scrapers come back:** post to the job summary, not the issue, while the
   scrapers are paused. Switch to the issue when the first states unpause.
8. **Retire what it replaces,** once it has run cleanly for 2 weeks: `weekly-scraper-audit.py` /
   `.yml`, `daily-scraper-error-digest.py` / `.yml`, `check-sessions.yml`, `close-session.yml` and
   the paused template, each in its own small PR, each Tamara's call. (Repo rule: no dead code
   left behind.)

**Target:** ready, in dry-run mode, by the first week of January 2027, when most sessions start.

## Before 2027: freeze and check

- **Freeze the settings in January** (the per-state limits, the territories' 45 / 21 days, PA's
  and NE's longer waits) with a hash, as the held-out test did.
- **Score them against what actually happens in 2027.** That's the first honest test; 2026's
  numbers are "fit to 2026".
- **Re-measure in spring 2027,** once full sessions are running: how fast actions reach the data
  (lag), and how long data keeps arriving after adjournment (tail).

## Open questions (Tamara's)

- **Where the issue lives.** `chihacknight/govbot` is public, so the list of failing states would
  be public. That's probably fine, and even useful, but it's her call. The alternative is a private
  repo just for the issue.
- **The weekly notification comment:** yes or no.
- **The scraper migration.** If scraping moves to a new system, where the raw data lives may
  change. Version 1 reads scrapes through one function, so only that function would change. Worth
  asking whoever runs the migration where the raw output will be.
- **The accepted file's first entries,** for example IL's synopses, which OpenStates doesn't bring
  back.

## Not in version 1

- The completeness audit (its own project, `completeness-audit-brief.md`).
- The cache hypothesis and the 2026 "for you to confirm" list (parked in `session-status-brief.md`).
- A web page for the lists; the issue comes first.
- Anything that turns a scraper on or off by itself.
