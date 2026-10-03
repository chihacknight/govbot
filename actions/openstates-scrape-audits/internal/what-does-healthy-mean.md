# What does "healthy" mean, for the state audit?

Written 2026-10-01, closing out a design discussion that ran most of this session.
Purpose: a single reference for what the state-health audit is actually trying to
answer, now that the write-side groundwork (PR #181,
`fix/format-timestamp-tracking-accuracy`) is built. Not a finished spec — a map of
the dimensions, what's solved, and what's deliberately still open.

## The core finding

Staleness alone is not "healthy." It only answers *one* question: is the pipeline
alive and finding things. A state can be staleness-healthy and still untrustworthy
(silently undercounting real bills, or carrying a garbage date from a real source
typo), and a state can look staleness-"unhealthy" while being completely fine
(correctly out of session, nothing new to find). Any definition of "healthy" that
collapses to a single number or boolean is going to be wrong for someone.

## The five dimensions

### 1. Process liveness — "is the pipeline actually running and finding things"

Built this session: `action_log_files_created`, a months-deep daily histogram in
`.windycivi/latest_timestamp_seen.txt`, keyed by the date `actions/format` itself
ran — deliberately blind to any bill's own content, so it can't be corrupted by bad
source data. This is the one signal that's trustworthy on its own, in isolation.

### 2. Content currency — "how recent is the real activity we have on record"

The `actions` ratchet (most recent government-recorded action date across
everything logged), now protected by a future-date guardrail after finding two real
typos in `mp-legislation`'s own source (CNMI's site, cnmileg.net — one action nine
years in the future, one bill's introduction date ten years in the past). This is a
*content* signal, not a liveness signal — don't read "old `actions` date" as "broken"
without checking dimension 3 first.

### 3. Session-awareness — "should this state even be active right now"

Built earlier this session: the LegiScan-based session calendar
(`tamara-notes/session-dates/session-calendar-2026.md`) and the 46-state pause
rollout (PR #178 area / `feat/pause-out-of-session-pipelines`, merged). This is what
turns "no new data" from an alarm into an expected, correct fact for an out-of-session
state. Staleness and session-status are two separate facts that must be combined by
whoever (human or eventually an AI agent) reads them — neither signal should try to
auto-diagnose the other.

### 4. Our own signal integrity — "can bad source data corrupt what WE compute"

Built this session, in direct response to the real MP typos: `update_latest_timestamp`
(shared by all three categories — `actions`, `events`, `vote_events`) now rejects an
implausible date before it can poison the ratchet, falling back to today's date
instead of freezing silently, and recording every fallback in
`implausible_date_fallbacks: {category: {date: count}}` so a real systemic failure
(every date suddenly implausible) is visible as a spike, not swallowed. Critically:
the *raw* record is never altered — `write_action_logs()` still faithfully writes
exactly what the government published. This guard protects our derived signals only,
never the historical record itself, per the project's tamper-evident-mirror
principle.

**Why this matters more for `events`/`vote_events` than `actions`**: their watermark
doesn't just get reported, it actively *gates* whether a file gets processed at all
(`is_newer_than_latest()` in `io_utils.py`, called before a vote_event/event is even
queued). An unguarded poison there means silent, permanent data loss — not just a
wrong-looking number. This is why the guard was centralized into
`update_latest_timestamp()` itself rather than left as a one-off fix in `bill.py`.

### 5. Completeness — "are we getting ALL the real bills, not just some"

**Still unsolved.** None of the above can catch a scraper that's quietly filtering
out real bills (the known Wyoming pattern — signed/enrolled bills excluded; ID/MD/UT
suspected of the same, never confirmed). This needs an outside source to cross-check
bill counts against, which is what `legiscan-audit.py` was built for — still blocked
on the LegiScan API key (~9 weeks pending as of this session). Nothing to do here
until that unblocks, besides noting the gap plainly whenever "healthy" is reported.

## Explicitly left out of "healthy," for now, on purpose

- **Orphan rate** — `format` already computes this
  (`.windycivi/errors/orphaned_placeholders_tracking.json`: vote_events/events
  referencing bills we don't have). A real, already-available signal, just not yet
  folded into the health picture. Cheap to add later.
- **Extraction quality** (`actions/extract`) — a separate pipeline layer entirely,
  not touched by anything in this session's work.
- **`find_new_actions`'s dedup-key fragility** — theoretical false-positive/negative
  risk (see `dream-list.md` item 1), unconfirmed whether it actually occurs across
  the 56 scrapers in practice. Watch for it, don't harden preemptively.
- **Whether `events`/`vote_events` have ever actually been poisoned in production**
  — started a live scan across all 56 `govbot-data` repos this session, hit shell
  tooling friction (word-splitting corruption in a `for x in $(...)` loop over `gh
  api` output), deliberately deferred rather than debug further tonight. Worth
  finishing with a `while read` loop over a file-backed repo list next time.

## Two layers of healthy (added 2026-10-02)

Found while scoping the actual 56-state audit: this project already has a second,
independent "healthy" system, `actions/fleet-monitor` (Nate, 6 commits, live since before
this session, hourly `fleet-monitor.yml` → Grafana Cloud + Slack/email alerting). It is
**not** the same definition of healthy as the 5 dimensions above, and it shouldn't be
merged into one score with them — they operate at two genuinely different layers:

- **Infrastructure layer (fleet-monitor)**: did the GitHub Actions workflow run, did it
  succeed, how many hours since a commit landed in the repo's data path. It never reads a
  single bill's JSON content. Already correctly session-aware (alert rules filter
  `paused="false"`, matching this project's pause rollout). Maps onto dimension 1
  (process liveness) and reuses dimension 3 (session-awareness); has no visibility into
  dimensions 2, 4, or 5.
- **Content layer (this doc + PR #181 + `audit_states.py`)**: is what actually landed in
  the bill data trustworthy — real government dates, genuinely new actions, plausible
  values, (eventually) complete bill counts. Fleet-monitor cannot see any of this; a
  workflow can succeed and commit on schedule while writing data that's garbage, stale-
  looking-fresh, or missing bills entirely.

**Concrete proof these are genuinely different, found the same day**: FL's `format.yml`/
`extract-text.yml` workflows both succeeded within the last 56 hours (infrastructure
layer: green), while the underlying `openstates-scrape.yml` workflow's last *success* was
1,326 hours (~55 days) ago, latest run `cancelled` (also visible at the infrastructure
layer, just a different workflow) — and separately, the content layer's own session-
coverage check (comparing government-recorded action dates against FL's real Adjourns
date) read FL as clean, because trailing actions on already-known bills kept the date
range looking current even while fresh scraping had stopped. Neither layer alone would
have caught the full picture; reading them together did.

**Practical integration**: `audit_states.py` now pulls fleet-monitor's own poller records
live (`fetch_fleet_monitor_data.py`, reuses `actions/fleet-monitor/fleet_poller.py`
directly rather than re-deriving commit-age/workflow-status by hand) and cross-checks: for
every jurisdiction that's both `active` (pipeline-manager) and `in` session (calendar), is
the raw scrape workflow's last success older than 7 days? That's the one check that
*can't* be answered from bill content alone — format/extract can look perfectly healthy
while the raw scrape itself is stuck, exactly as FL demonstrated.

## What this means for the Dec 15 presentation

The honest story isn't "we built a health score" — it's "we figured out that
'healthy' has to be several independent things, found two real government-data bugs
while building the first piece, and designed around the fact that we can't trust any
single signal in isolation." That's a stronger, more credible story than a single
green/red status per state would have been.
