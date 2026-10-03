# 56-state scraper audit — plan

Started 2026-07-27/28. This is a scoping doc, not a status doc — it exists so we don't lose
the shape of a multi-day project while we're heads-down on step 1. Update it as decisions
get made; it should stay accurate to "where we are," not read as a finished spec.

## The goal

For every one of the 56 states/jurisdictions, answer two questions with actual confidence
(not just "the pipeline didn't error"):

1. **Is the scraper running as expected?**
2. **Is the state currently in session or out of session?**

Then route each state into one of three outcomes:

### A. Out of session + healthy
Criteria (current draft, still being refined):
- Distinct bill-identifier count for the session is **stable/complete** — i.e. re-scraping
  doesn't change the count, so we're not catching it mid-backfill or missing a late-filed
  bill.
- We can point to that specific number and say "this is what a complete session looks like"
  (not just "the last run succeeded").
- Text extraction is a **separate, later audit pass** — noted per-state but not blocking this
  pass. Don't hold up moving a state to "done" waiting on extraction verification.

Action: move to `working-out-of-session.md`, but into a **new section**, since the states
already listed there predate this audit and haven't been through this bar — don't conflate
"already on the list" with "passed this audit."

Deferred (not solved this round, just flagged): some mechanism to **reopen** the state
(resume scraping / re-check) when its next session starts. No design yet — placeholder only,
so we don't lose track that it needs to exist eventually.

### B. In session + healthy
Action: move to `working-in-session.md`.

Deferred (not solved this round): some mechanism to flag the state for **closure** review
once its session ends. Same as above — placeholder, not designed yet.

### C. Broken
Hope is that most of these are already resolved based on the fix streak from the last
session (AZ, MP, NH, MI, FL, the shrink-guard saga, etc. — see `not-working.md` and
`pending-branches.md`). Whatever's left after re-checking against current reality gets
worked as its own thing, same as before.

## Then: repo-tag / config update

Once a state's true status is known, `chn-openstates-scrape.yml` (via `pipeline-manager`)
needs to reflect it — active vs. `openstates-scrape-paused` template — so downstream
automation (scheduling, format, extract) is actually pulling from/running against the right
set of repos instead of a stale config. Mechanics deferred until we're actually doing this
step — noted here so it's not forgotten as part of the full loop, not just "figure out
health and stop."

## Why this is a multi-day project, not a single audit pass

Step 1 alone — "confirm from an outside source that what we have is legit" — is its own
open discussion, not a solved checklist. `session-dates-comparison.md` already shows
OpenStates' own API can't be blindly trusted as that outside source (10 states show it a
full year+ stale despite being labeled current; `check-sessions.py`'s automated version of
this was disabled 2026-07-14 for exactly this reason). LegiScan is the more-trusted source
so far, but "trust LegiScan" and "have we actually cross-checked bill *counts/completeness*
against an outside source, not just session *dates*" are different questions — the latter
is still open.

## Open questions (being worked through, most pressing first)

1. **What counts as "confirmed legit" for a given state's data?** Session dates from
   LegiScan tell us *whether* a state should have bills right now — they don't independently
   confirm *how many* bills we should have, or that we're not silently missing some (see:
   Wyoming's own scraper filtering out signed/enrolled bills, ID/MD/UT suspected same pattern
   but unconfirmed, both still open per `not-working.md`). Need to decide, state by state or
   as a general method, what "an outside source agrees with our count" actually looks like.
   **This is the next thing to dig into.**
2. Where's the line between "worth chasing" and "close enough" when LegiScan and OpenStates
   disagree on dates? `session-dates-comparison.md`'s triage buckets are a first pass at this
   but weren't written with this audit's bar in mind specifically.
3. What's the actual mechanism for the two "tag for later" ideas (reopen-on-next-session,
   flag-for-closure)? Not needed to start the audit, but worth having an answer before we've
   moved 56 states through the pipeline and have nowhere to put the reminder.
4. Exact mechanics of the `chn-openstates-scrape.yml` update step (per-state, batched,
   automated from audit output, or manual) — deferred until we're there.

## Status

Not started yet at the per-state level — this doc exists to hold the shape of the project
while step 1's methodology gets worked out first. See conversation/session notes for the
live discussion; this doc should get updated once step 1 has an actual answer.

## Outstanding work (as of 2026-10-02)

Picking this back up — focus is now on actually auditing the state data we have. Gathered
here from across several sessions' worth of threads so nothing gets lost going back in.

**New since this doc was written, relevant to step 1's methodology:**
- `tamara-notes/processes/what-does-healthy-mean.md` — a first real answer to "what counts
  as confirmed legit," split into 5 independent dimensions (process liveness, content
  currency, session-awareness, our-own-signal-integrity, completeness). Completeness is
  still explicitly unsolved there too (same LegiScan-API-key block as below).
- `.windycivi/latest_timestamp_seen.txt` now carries `action_log_files_created` (daily
  activity histogram) and `implausible_date_fallbacks` (guards against source-data typos
  poisoning the staleness signal) alongside the existing ratchet — see PR #181, merged.
  Means a per-state staleness check can read one small committed file instead of needing
  git history or the GitHub tree API (which truncates on large repos).
- GitHub topics are now live on every scraper + data repo: `govbot-scraper-active` /
  `govbot-scraper-paused` (from `chn-openstates-scrape.yml`'s template) and
  `govbot-session-in` / `govbot-session-out` (from the LegiScan session calendar) — lets
  you filter to e.g. "paused states" or "in-session states" directly on GitHub or via
  `gh search repos --topic`, without reading config by hand. Existing health tags
  (`broken`/`chronic`/`regression`/`needs-verification`/`workflow-disabled` on
  az/mt/va/vi) were preserved, not touched.
- The 46-state pause rollout (session dates vs. active pipelines) is done and merged (PR
  #180), plus a follow-up pausing PR for being out-of-session-but-still-marked-active
  (PR #185).

**Blocking full data access, not yet resolved:**
- `govbot clone` can't reach **az, ct, dc, tx, va** at all — not a scrape/pause issue, the
  CLI's compiled-in locale list was simply missing these 5 (traced to a missing `labels:
  [working]` entry in `chn-openstates-files.yml`). Config fix is open on PR #186; the
  binary itself still needs rebuilding from the fixed config, which needs a local Rust
  toolchain (none currently installed). Until that lands, any per-state audit covers at
  most 51/56.
- `chn-openstates-scrape.yml` has its own, larger `labels` gap (19 states missing
  `working`) — confirmed unrelated to the CLI issue above (the generator only reads the
  files config), but flagged as worth understanding since `labels` presumably means
  something there too. Not investigated.
- Local audit copy: 51/56 states currently downloaded — 27 on the external HD (from
  before the HDD/Spotlight slowness was diagnosed), 24 more on the internal SSD
  (`~/govbot_data_local/repos`, cloned in under 2 minutes once moved off the HDD).
  One-time for this audit per Tamara; a future repeat would go through whatever
  automated system gets built, not this manual process.

**Deferred mid-session, explicitly not forgotten:**
- Live scan of all 56 `govbot-data` repos for existing `events`/`vote_events`
  watermark poisoning (the failure mode the PR #181 guard now prevents going forward,
  but never checked for past occurrences) — started, hit a shell word-splitting bug
  mid-scan, deliberately deferred ("we don't have to do this tonight").
- Files/-split architecture (separate raw PDFs from lean metadata) — fully planned
  (`/Users/tamara/.claude/plans/soft-popping-meadow.md`, Phases 1-4) but not started.
  Phase 4 specifically would give `govbot query coverage` a real staleness field, which
  is the most likely shape of "the automated system" for future audits.
- LegiScan API key still pending (~9+ weeks as of last check) — blocks
  `legiscan-audit.py` and any real bill-*count* completeness cross-check. Everything
  above answers "is the pipeline alive," nothing yet answers "are we missing bills the
  state actually published" (the known Wyoming signed/enrolled-bill-filtering pattern;
  ID/MD/UT suspected of the same, unconfirmed).

**Separate audit thread already in progress, worth folding in:**
- `tamara-notes/pdf-only-bill-detail-audit.md` (script: `pdf-only-bill-detail-audit.py`,
  re-runnable, ~30s) — answers a different question than this doc (what structured detail
  exists *without* opening the PDF) across the 28 PDF-only states. Concrete next step
  already identified there: build short-summary extraction for the 10 Tier-1 states
  (real `abstracts` field) and 7 Tier-2 states (short linked summary doc), same pattern
  as `scripts/build_il_summaries.py`. Also surfaced real scraper gaps worth filing
  upstream: NV/OK/GU leave real data on the table, MA's bill text is actually
  machine-readable HTML (not PDF-only as assumed), VT's PDF has an easy-to-extract
  "Statement of purpose" on page 1.
- `tamara-notes/state-specific/fl-tracking.md` — FL specifically has two **unresolved,
  not-yet-root-caused** findings from 2026-08-07: House committee-vote data can silently
  regress (get deleted) bill-to-bill across nightly wipe-and-replace runs if a rescrape
  hits an active bot-detection block window, and at least one confirmed case (HB 755)
  where the raw scrape *did* capture a vote but it never propagated through
  `actions/format` into `govbot-data` at all. Both are "is the data we show actually
  complete" questions, squarely in scope for this audit, not yet investigated further.

## Related docs

- `tamara-notes/session-dates/session-dates-comparison.md` — LegiScan vs. OpenStates session
  date comparison, the starting point for the "outside source" question in step 1.
- `tamara-notes/scraper-status/not-working.md` / `working-in-session.md` /
  `working-out-of-session.md` — current per-state status, last audited 2026-07-21/24, not
  yet run through this audit's bar.
- `tamara-notes/scraper-status/critical-merge-conflict-corruption.md` — separate, deprioritized
  finding (self-heals nightly; concurrency guard already covers the specific race that caused
  it — see session notes 2026-07-27/28). Not part of this audit's scope.
- `actions/pipeline-manager/check-sessions.py` — the disabled automated session-pause script;
  context for why we can't just trust an API feed here.

## Fleet-wide WARNING-level sweep (2026-10-02)

Generalized the MA finding (PR #187 — scrape.sh never matched `WARNING`-level scraper log
lines, only `ERROR`-text and raw exception reprs) into a one-time sweep of every state's
most recent successful `openstates-scrape.yml` run
(`tamara-notes/processes/sweep_scraper_warnings.py`, results in
`tamara-notes/processes/warning_sweep_output.json`). MA was found by accident; this checks
systematically whether other states have the same "reports GitHub Actions success while
quietly dropping data" pattern.

**Raw count is a candidate-finder, not a severity score** — confirmed by actually reading
what's behind the top offenders (`tamara-notes/processes/categorize_warnings.py`, groups
matches by normalized message template):

**Real, MA-like silent data loss (worth fixing):**
- **DE**: 459× `Failed to fetch scrape_votes on attempt 3 of 3, giving up` — real vote data
  lost after exhausted retries, same shape as MA's `Server Error` pattern.
- **NH**: 232× `Missing version_id for X, can't build bill page` — whole bill pages failing
  to build, arguably worse than MA since it's the entire page, not one sub-component.

**Real but narrower data-quality gaps (actions captured, just malformed):**
- **MN**: ~1,360 `ACTION without date` across several sub-patterns — the action text is
  there, but no parseable date (matters because `write_action_logs()` keys the log
  filename on date — an unparseable date may mean the action silently never gets its own
  log file at all; not yet traced all the way through, worth checking).
- **KS**: same class, hundreds of `No date found for action row Hearing: ...`, specific to
  hearing/event actions.

**High raw count, but actually benign on inspection (don't chase these):**
- **NY** (22,000 — the fleet's highest by far): 21,999 of them are one single template,
  `No active version for X, assuming first` — the scraper explicitly names its own
  fallback decision. Not data loss.
- **FL** (5,735): `No vote/chapter-law/analysis/citations table for X` — plausibly just
  normal per-bill variation (not every bill has every document type).
- **MO** (1,361): `Found missing Witness Form link for bill X` — informational.
- **CA**: `Failed to extract committee abbr from '...'` — a cosmetic normalization miss;
  the underlying action still gets saved.

### Checked against already-known problem states — does this sweep generalize, or was MA a one-off?

- **FL** (the real, documented committee-vote-loss problem from `fl-tracking.md`): **already
  caught by a different, pre-existing mechanism**, not this new one. Read FL's actual fix
  branch (`fix/fl-streaming-bills` in the local `openstates-scrapers` checkout):
  `ResilientFetchPage` logs its real failures as
  `self.logger.warning(f"SKIPPED BILL: {id} -- {message}")` — and `SKIPPED BILL:` is
  exactly the string this sweep (and `scrape.sh`'s `OTHER_ERRORS`) deliberately excludes,
  because it already has its own dedicated counter (`SKIPPED_COUNT`/`SKIPPED_ITEMS`,
  pre-dating this session). FL's gap wasn't a detection gap on our side — MA's scraper
  simply never adopted the `SKIPPED BILL:` convention FL's fix pioneered. The real
  takeaway: a state with a high *warning_count* that does NOT use the `SKIPPED BILL:`
  convention is a candidate for "needs the same fix FL already has," not just "needs
  investigation."
- **TX** (`tx-backfill-runbook.md`: IP-blocked at the firewall, plus upstream's
  session-level `active: False` gating): **not caught by this sweep, and can't be** —
  neither failure shows up as a `self.warning()` call at all. IP-blocking already has its
  own detection (`scrape.sh`'s `FAILURE_TYPE` classification,
  N1/H1_ACTIVE_BLOCK). The "session silently never attempted because upstream marked it
  inactive" half has **no detection anywhere** — a real, still-open completeness gap, same
  category as dimension 5 in `what-does-healthy-mean.md`.
- **KY** (0% sponsorships) / **OR** (56% sponsor coverage) — from
  `pdf-only-bill-detail-audit.md`'s "Other Findings" section: **confirmed NOT caught by
  this sweep either** (KY and OR both show exactly 1 warning in the sweep — the routine
  "no session provided" line, nothing else). Checked directly. A silently-empty field
  produces no log line at all, warning or otherwise — this failure class is invisible to
  any log-based check by construction. It only shows up by inspecting actual committed
  bill *content* (what `pdf-only-bill-detail-audit.py` already does). Same story for GU's
  0 actions (3 benign warnings, nothing else) — already known to be sparse at the source,
  not a scraper bug.

### Three distinct detection layers, confirmed independent (none subsumes another)

1. **Infrastructure layer** (`fleet-monitor`) — did the workflow run and succeed, how
   stale is the last commit. Blind to content entirely.
2. **Log-warning layer** (this sweep, PR #187) — catches a scraper *trying* something and
   logging a failure via `self.warning()`/`self.error()`, as long as it isn't already
   using the `SKIPPED BILL:` convention (which has its own, separate counter). Blind to
   fields that are simply never populated with no log trace.
3. **Content-field-coverage layer** (`pdf-only-bill-detail-audit.py`) — inspects actual
   committed bill JSON for which fields are populated. Catches KY/OR/GU-style silent gaps.
   Blind to *why* a field is empty (scraper bug vs. genuinely absent at the source — see
   that doc's own per-state spot-checks for the difference).

None of the three would have found all of today's findings alone. Worth keeping in mind for
Dec 15: "how do we know a state is healthy" doesn't have a single tool answer — it took three
independently-built, differently-blind checks layered together.

### Not yet done
- DE's `scrape_votes` failures and NH's `can't build bill page` failures haven't been
  traced to root cause yet (unlike MA, where the exact line and fix are known) — next step
  if pursuing a fix, not done as part of this sweep.
- Only checked each state's single most recent successful run, not a trend over time —
  unknown whether DE/NH's pattern is new, growing, or long-standing like MA's was.
- The remaining ~48 states below the top 8 weren't individually categorized by message
  type, only ranked by raw count (see `warning_sweep_output.json` for all 56).

## Pre-existing staleness-audit spec, and a methodology correction it surfaced (2026-10-02)

Found `actions/pipeline-manager/docs/staleness-audit-spec.md` (written 2026-07-14, never
built — `Status: Not built yet`) while scoping the weekly new-bill-flatline audit. It's a
real spec for almost the same goal, written after a one-off manual run found **16 states
plus USA frozen at the exact same timestamp, 2025-12-14 23:31-23:41 UTC** — 7+ months
stale, unnoticed, every workflow still green. Only 4 of those 16 (`nc`, `il`, `wv`, `ar`)
were ever individually investigated at the time.

**Ran the remaining 12 against today's data to check whether they're still frozen.** Result
mixed a real finding with a real methodology mistake, caught and corrected in the same
pass:

- **`usa, mi, oh, pa, vi`** (active, in-session) looked frozen at 2026-07-15 in our local
  clone's `last_commit` field — but cross-checked against fleet-monitor's **live** poll
  (`fleet_monitor_snapshot.json`) and found all 5 actually committed **8-14 hours ago**.
  The local clone was a one-time snapshot taken early in this session and never re-pulled;
  for actively-scraping, in-session states (which commit daily) that snapshot goes stale
  within a day. **Not a real finding — a measurement artifact from our own tooling.**
- **`ak, ar, il, in, nc, ne, nm, nv, ny, sc, vt`** (paused, out-of-session) — July 15 is
  plausibly accurate for these, since nothing changes for a paused state regardless of
  when the clone was taken. Consistent with the pause rollout (PR #180).

**The standing rule this produces, worth keeping for every future audit pass**: a local
clone is fine for content-shape analysis (bill structure, field coverage, log date ranges)
but unsafe for *recency* claims ("last commit," "is this frozen") unless it's freshly
re-pulled or cross-checked against something live (fleet-monitor's poller, or a direct
`gh api` commit-date check) at the time of the claim. This is exactly the trap
`staleness-audit-spec.md` itself warns about (distinguishing a real staleness signal from
a measurement artifact, re: the `.windycivi` tracking-file-commit trap) — we walked into
our own version of it and caught it by cross-referencing two independently-built signals
against each other, which is the whole reason multiple independent layers have been worth
building this session rather than trusting any one tool's output at face value.

**Still open from the original 16**: `ak, in, ne, nm, ny, sc, vt` have never been
individually investigated (only `nc`/`il`/`wv`/`ar` were, back in July) — unknown whether
their current paused/frozen state reflects a legitimate out-of-session pause or an
unresolved problem predating it. Worth a pass once the weekly audit is live, rather than
manually one at a time.
