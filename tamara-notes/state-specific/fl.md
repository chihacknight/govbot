---
name: fl
description: Single consolidated, chronological FL scraper history — replaces scattered FL mentions across archived_docs and scraper-status. Read this top-down before doing more FL work. One of the per-state files indexed in tamara-notes/state-specific/README.md.
---

# Florida — consolidated tracking doc

**Why this file exists:** FL shows up across at least 15 different notes files (see "Source
documents" at the bottom), and the same handful of issues have been rediscovered, re-fixed,
and re-flagged multiple times without ever being read together in one place. This doc pulls
every FL mention into one chronological timeline plus a "what's actually true today"
summary, so the next session starts from the top instead of re-walking the same loop.

**Last assembled:** 2026-08-07 (this file is a snapshot — verify against a live run before
trusting any status below as still current).

---

## PR #5724 / issue #1386 — verified live status (checked 2026-08-07 via `gh`)

Prior versions of this doc (and every source file it's built from) only had *references* to
the PR/issue, never their live GitHub state. Pulled directly:

- **PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724): still `OPEN`,
  not merged.** `mergeable: CONFLICTING` — it now has real merge conflicts against upstream
  `main`, on top of not being approved. `reviewDecision` is empty (no formal approve/request-changes
  review was ever left, just comments). 8 commits total, last pushed 2026-07-24. Last activity
  on the thread at all: **2026-07-26T03:09:20Z**, which is Tamara's own comment posing the
  unconditional-vs-opt-in design question — **still no reply from `jessemortenson` or anyone
  else**, 12 days of silence as of this check. Don't read PR silence as tacit approval; it also
  hasn't been marked stale/closed, so it's just sitting.
- **Issue [#1386](https://github.com/openstates/issues/issues/1386): still `OPEN`.** Only one
  comment ever posted (2026-07-23, Tamara's own update about `allow_partial`) — no maintainer
  engagement on the issue itself at all, separate from the PR thread.
- **The incremental-scraping proposal was never actually filed upstream.** Issue #1386's own
  body says "*A separate proposal for incremental scraping support will be posted for
  discussion once we hear...*" — searched `openstates/issues` directly, no such issue exists.
  `fl-incremental-scraping-proposal.md` is still just a local draft that was never sent. Worth
  deciding whether to actually post it (maybe bundled with the design-tension question above,
  since OpenStates may want to weigh in on both scraper-reliability philosophy questions at
  once) or explicitly drop it.
- **Practical implication:** since the PR is unmerged, none of the 8 commits' fixes (streaming,
  timeout, per-bill resilience, `scrape_warnings`) are in `openstates/scrapers:latest` — every
  real FL run to date has run on the temporary `ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test`
  image, not upstream. This has been true and stated throughout the timeline below, now just
  independently confirmed rather than assumed.

**2026-08-07 — PR closed, issue left open.** Given the merge conflicts, 12 days of maintainer
silence, and the fact that we'd already moved past this PR's contents with two newer findings
(per-run vote regression, format-side vote loss), decided to stop carrying this PR forward
piecemeal. Closed [#5724](https://github.com/openstates/openstates-scrapers/pull/5724) with a
[comment](https://github.com/openstates/openstates-scrapers/pull/5724#issuecomment-5223536722)
explaining we're running our own custom image and will come back with a consolidated fix; left
[#1386](https://github.com/openstates/issues/issues/1386) open with an
[update](https://github.com/openstates/issues/issues/1386#issuecomment-5223537655), so anyone
else hitting the same `flhouse.gov` bot-detection problem has somewhere to land. Also
apologized on both threads for the communication gaps (work on FL happens in spurts). **Next
time this picks back up upstream, it should be a fresh PR against current `main`** (this one's
branch has diverged too far) that bundles everything found across this whole timeline, not a
reopen of #5724.

---

## Session context (don't lose track of this)

FL's **2026 Regular Session ran 2026-01-13 → 2026-03-13** (`session-calendar-2026.md`) — it
has been **out of session since March**. There's also a `2026F` special session (5 bills).
This matters: everything from ~April onward is nightly re-scraping of a legislature that's
adjourned, mostly picking up trailing post-session actions (governor signatures, chapter-law
assignments — e.g. HB 755's "Approved by Governor" 2026-06-30, "Chapter No. 2026-181"
2026-07-01) rather than tracking live floor activity. The bot-detection/scrape problems
below are not about racing live legislative activity — they're about finishing a backfill of
an already-concluded session.

---

## Chronological timeline

### 2026-07-01 — Self-hosted runner added
PR [#53](https://github.com/chihacknight/govbot/pull/53) / commit `2bb29d0b`: MA + FL moved to
a self-hosted runner (Tamara's MacBook), on the theory that FL was hitting an IP-level cloud
block like TX/MA/TN. **Diagnosis later proven wrong** — see 07-02.

### 2026-07-02 — First real diagnosis: not IP blocking, it's `flhouse.gov` bot detection
(`error-tracking-2026-07-02.md`, `openstates-responses.md`) Confirmed FL fails even from home
network IPs — `flsenate.gov` never blocks, but `flhouse.gov` returns HTTP 200 with a
"Request Rejected" HTML body after sustained scraping (`spatula.pages.RejectedResponse`).
Only 22 files scraped that run (5 special-session bills + metadata); 1,916+ prior bills
retained from an earlier run. Also found: macOS `tar --mode=755` (GNU-only flag) silently
fails on BSD tar, masking real self-hosted data behind a bogus "Nightly fallback" summary —
affected FL, IL, NC. Root cause identified in `fl/bills.py`: `scrape()` wraps its generator
in `list()`, so the entire ~8,000-bill session must fully materialize before anything is
written — one `RejectedResponse` partway through means **zero bills saved** despite hours of
real progress.

### 2026-07-13/14 — Re-diagnosed again: also just slow, and losing full runs to timeouts
(`error-tracking.md`, `2026-07-14-recovery-summary.md`) A 2026-07-13 self-hosted run got
**zero** bot-detection errors and ran cleanly past bill 250+ before being killed by its own
12h `timeout-minutes` ceiling. Since `scrape.sh` only committed after a full run completed,
**that entire 12 hours of progress was lost** — nothing recoverable, runner workspace reused
before anyone checked. Fix: `timeout-minutes` raised 12h → 24h. Flagged even then that the
real long-term fix was incremental commits during the run, not a bigger timeout ceiling —
this is the seed of `fl-incremental-scraping-proposal.md` (still open as of this writing).

### 2026-07-21 — The overwrite/cancellation incident, timeout regression, and "tinyproxy was never on"
(`2026-07-21-session-handoff.md`) Real, concrete data-loss event: a 6-hour-old in-progress
manual FL scrape got **cancelled** when a delayed `schedule` trigger fired the same workflow
(no concurrency guard existed). The replacement run "succeeded" after only ~5 hours and its
wipe-and-rebuild **overwrote the larger dataset the cancelled run had already saved** — root
cause: `scrape.sh`'s wipe/rebuild only checked `exit_code == 0` and `file count > 0`, never
compared against what was already committed. FL was also confirmed actively IP-blocked
(`N3_ACTIVE_BLOCK`) around the same time. Separately found: FL's 24h timeout was a one-off
hand-edit on the live workflow file (not in the shared template), so an overnight `apply.py`
template rollout had silently reverted it back to 12h — directly contributing to the
mid-scrape kill above. Fixed with a proper per-locale `scrape_timeout_minutes` config field
(PR #88, commit `c9ed36f1`) and FL raised to **42h** (2520 min). Also this session: discovered
tinyproxy had never actually been active for *any* self-hosted state (`PROXY_URL` org secret
was never set — `USE_PROXY: true` but `HTTPS_PROXY: ""`), meaning FL/MA and others had been
running unprotected on raw Azure IPs the whole time tinyproxy was assumed to be helping.
Concurrency guard + proxy secret + shrink-guard (see below) fixed same session; all 56
scrapers re-dispatched to confirm. Overwrite fix itself: commit `83eb4294`/PR #86
("prevent scrape data loss from cancelled/short-lived runs overwriting good data").

### 2026-07-23/24 — Streaming fix + timeout fix, first real FL data since 07-02, third bug found
(`fl-incremental-scraping-proposal.md`, `openstates-responses.md`, `fl-single-bill-failure-handoff.md`,
`state-problems.md`) PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724) opened
upstream: (1) removes the `list()` anti-pattern so bills stream to disk as scraped, (2) adds
`timeout=10` to the three `flhouse.gov` request constructions in `HouseSearchPage`/`HouseBillPage`
— a second, independent bug found while investigating why real runs got far fewer bills
(<40) than the maintainer's own test (~1,400–1,900): `spatula.URL` defaults `timeout=None`, so
a stalled connection hangs forever instead of raising the `ConnectionError` the scraper's own
retry logic already handles. Both fixes **confirmed working live**: a self-hosted run landed
**413 real bills**, first real FL data since 2026-07-02.

That same run's *final* failure revealed a **third bug**: a single bill's (HB/SB 66)
`flhouse.gov` `ReadTimeout` — after exhausting its own 3 retries — propagated raw through
spatula's whole recursive `_to_items()` chain and landed in `_process_bill_list`'s
session-wide except block, **crashing the entire remaining scrape** and discarding 149
not-yet-committed files. Root cause confirmed by reading spatula's actual source: `Page._fetch_data`
only converts `scrapelib.HTTPError` into its own swallowable `HandledError` — a plain
`ReadTimeout`/`ConnectionError` isn't one, so it propagates raw.

**Maintainer feedback (2026-07-17, addressed 07-23):** `jessemortenson` declined to merge PR
#5724 as-is — not objecting to streaming itself, but to the scraper silently exiting
"successfully" on a partial dataset (his own test got ~1,400–1,900 bills; ours was getting
<30). Requested partial-results behavior be opt-in. Addressed via a new `allow_partial` flag
(default off, matches his ask).

### 2026-07-24 — `ResilientFetchPage` fix for the third bug, AZ resolved same day
(`state-problems.md`) Added a `ResilientFetchPage` mixin in `scrapers/fl/bills.py` that wraps
`_fetch_data`, catches transient network exceptions (and later, bot-detection rejections
too), and re-raises as spatula's own `HandledError` — reusing spatula's existing "move on"
mechanism instead of inventing a new one. Applied to 5 classes, all supplementary/independent
per-bill data: `HouseSearchPage`, `HouseBillPage`, `HouseComVote` (flhouse.gov), `FloorVote`,
`UpperComVote` (flsenate.gov vote PDFs). Deliberately **not** applied to
`BillList`/`BillDetail`/`SubjectPDF` — those are session-wide or a bill's own core data, where
silently swallowing a failure risks a run looking complete when it isn't. Companion govbot-side
fix (commit `d84b7ab1`, same day): `SKIPPED BILL:` log-line convention surfaced as its own
"🔁 Skipped, Will Retry Next Run (N)" summary section, separate from the generic error bucket.
Also same day: `force_self_hosted` config field (commit `038195cf`) added so FL's *scheduled*
runs (not just manual dispatches) actually land on self-hosted infra.

### 2026-07-24~26 — Fourth exception type, design-tension flag, sustained-block cooldown
(`project-fl-single-bill-failure-fix.md` memory) A second failure shape of the same
third-bug class found in a run that already had the first fix: bill 411 hit
`spatula.RejectedResponse` (bot-detection) after `HouseSearchPage`'s own retries exhausted —
a different exception class the first fix didn't cover. Fixed same way, verified live twice:
run `30101428905` (confirmed the network-error fix, then crashed on bill 411 — motivating the
second fix) and run `30115056537` (~16h, completed clean with both fixes, watched bills
818/819/820 consecutively bot-detected and correctly skip-and-continue).

**Design tension raised explicitly with the maintainer:** `ResilientFetchPage` is
unconditional (no opt-out unlike `allow_partial`), meaning a bill can now save "successfully"
with House votes silently missing — structurally the same "run succeeds, data missing,
invisible to consumers" problem the maintainer originally objected to, just at per-bill
granularity. Mitigated (not resolved) by adding `bill.extras["scrape_warnings"]` (commit
`cacedec3f`) so the gap is at least visible in the bill's own JSON. Posted as an open question
on the PR 2026-07-26; **not yet answered as of last check**.

**2026-07-26**: an overnight verification run and the automatic run right after it both got
cancelled — `flhouse.gov` was blocking the self-hosted IP almost continuously from ~03:12 to
~14:29 UTC (98.5% of ~810 bills hit `SKIPPED BILL:` in one stretch), likely from the team's own
heavy repeated testing over the prior ~24h. Found real duplicate bloat from this (5,330 bill
files, only 1,878 distinct, up to 11 copies of one bill) — not treated as urgent since
`actions/format` dedupes downstream and the bloat self-resolves on the next full successful
wipe-and-replace. Decided to deliberately not dispatch FL again that weekend to let the IP
cool down; mid-decision found live evidence the block may have already cleared, but the
in-flight cancel wasn't undone.

### 2026-07-25 — FL hits the separate shrink-guard duplicate-bloat bug
(`pending-branches.md`, `morning-todo.md`) Found *by accident* (never in the deliberate 6-state
test batch of MT/MO/PR/USA/WA/MA): 3,123 bill files, only 1,878 distinct identifiers, 357
duplicated with same-day timestamps. This is the shrink-guard's root cause
(`fix/shrink-guard-identifier-check`, merged to `main`) — the guard used to compare raw file
counts, which can't distinguish "the site removed bills" from "same bills, stale duplicate-UUID
copies from a prior run's auto-save that never got cleaned up because that run also tripped
the guard" (self-reinforcing bloat). No manual action needed for FL specifically — its
workflow already points at `@main`, so the fix applies automatically on the next run. Flagged
as a lesson: WA, MA, and FL were all found by accident this way, not because anything alerted
on them — worth a proactive identifier-dedup sweep across all 56 states rather than waiting to
stumble onto the next one.

### 2026-07-27 — Per-run scrape metrics artifact shipped
Commit `24b839ea`: exposes `skipped_count`/`skipped_items`/`distinct_bills_before`/
`distinct_bills_after`/etc. as a fetchable `audit-summary.json` artifact per run. This is what
made the 2026-08-07 investigation below possible without manually parsing raw logs.

### 2026-07-28 — Third fix (single-bill resilience) still unverified live
(`morning-todo.md`) Noted as of this date: the `ResilientFetchPage` fix existed on
`fix/fl-streaming-bills` but its dedicated verification run had been blocked by the (now-fixed)
shrink-guard bug and got cancelled — needed a fresh live test once that was out of the way.

### 2026-08-07 (this session) — Live investigation: skip-rate reality check + a new, sharper finding

Walked a real in-progress/completed local FL run end-to-end instead of assuming from the
`SKIPPED BILL:` log line alone. See `not-working.md`'s FL section for the full writeup; summary:

- **Bills are not lost, and neither are floor votes.** A blocked bill's JSON still has full
  title/sponsors/subjects/citations and the complete cross-chamber action/history timeline
  (from `flsenate.gov`'s own bill-history page, which tracks both chambers regardless of
  `flhouse.gov`'s state). House *floor* votes also come from `flsenate.gov` (`FloorVote`,
  chamber="lower" for any vote-history row whose PDF link contains `"HouseVote"`) — confirmed
  unaffected by construction, not inference.
- **The one genuinely, irrecoverably lost thing per blocked bill: House *committee* roll-call
  votes** (`HouseSearchPage` → `HouseBillPage` → `HouseComVote`, `flhouse.gov` only — the
  class's own docstring says this data "is not available on the Senate's website"). Confirmed
  with a real example: HB 755's committee vote ("Favorable (State Affairs Committee)", 21-0-5,
  `flhouse.gov/Sections/Committees/billvote.aspx`).
- **Checked the latest real run** ([31151185583](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/31151185583),
  2026-08-06/07, 13h38m, ✅ success) via its `audit-summary.json` artifact: **1,902 distinct
  bills**, 1,721 vote_events, **1,480 of 1,902 bills (≈78%) hit the `HouseSearchPage` block** —
  a high, sustained rate, closer to the 07-26 "continuous block" incident than a spotty one.
  Raw-repo duplicate bloat is confirmed fully cleaned up by this run's wipe-and-replace
  (11,667 stale `bill_*.json` files → exactly 1,902, matching the distinct count).
- **New finding, not previously tracked anywhere:** the nightly **full wipe-and-replace means
  a bill's House committee vote can be captured on one run and then silently regressed
  (deleted) on a later run** if that same bill gets rescraped during an active block window —
  there is no "keep the best version we've ever seen" logic. **Confirmed concretely**: HB 755
  had a real committee vote in an earlier scrape (~07-25); in the 2026-08-07 run above, HB 755
  got blocked and the freshly-committed version has 3 floor votes but **no committee vote at
  all** — the previously-captured one is gone from the raw repo. This is the same *class* of
  problem as the 07-21 overwrite incident and the still-open
  `project-govbot-scraper-overwrite-problem` — just discovered here at the level of an
  individual vote record inside an otherwise-successful run, not a whole failed/cancelled run.
- **Second new finding: this loss isn't caught downstream either.** Checked `govbot-data/fl-legislation`
  (the deduped/formatted output `actions/format` produces) for HB 755: `metadata.json` has the
  full action-line text ("Favorable by State Affairs Committee") but no vote tally, and the
  per-bill `logs/` folder is missing the `YYYYMMDDT000000Z.vote_event.pass.lower.json` file that
  `actions/format/handlers/vote_event.py` should have produced for that date — even though the
  raw scrape genuinely captured this vote at the time (`_processing.log_file_created:
  2026-07-25` matches). So `actions/format` has a working `vote_event.py` handler, but this
  vote never made it through — **not yet root-caused**, worth checking
  `DATA_NOT_PROCESSED_FOLDER` error logs or whether format's git-diff-based ingestion missed the
  file. This is a genuinely new thread, not a rediscovery of something already tracked.

---

## What's actually true right now (as of 2026-08-07)

- FL is out of its regular 2026 session (ended 03-13); nightly scrapes are mostly catching
  trailing post-session actions plus whatever the `2026F` special session still needs.
- Streaming fix, timeout fix, and single-bill resilience fix (all 3 root causes from
  07-23–07-26) are live and confirmed working — runs complete without crashing.
- PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724) upstream: still not
  merged as of last check — don't assume any of this is live in `openstates/scrapers:latest`.
  `fl-legislation`'s workflow still points at the temporary
  `ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test` image (now via the config-driven
  `docker_image` field).
- Raw-repo duplicate bloat: resolved as of the 2026-08-07 run (1,902 files = 1,902 distinct
  bills). Will re-bloat between now and the next full successful run, as always — don't treat
  a high raw file count as new information.
- `flhouse.gov` block rate in the most recent completed run: **~78%** of bills. High. Whether
  this is trending up, down, or steady across recent runs — **not yet checked**, was the
  natural next step before this doc-consolidation request interrupted it.
- **Unresolved, newly found**: House committee vote loss can regress bill-to-bill across runs
  (raw side), and can also silently fail to propagate into `govbot-data` even when the raw
  scrape *did* capture it (format side). Neither has a root-caused fix yet.

## Threads that have gone in circles (read before re-investigating)

1. **"Is FL IP-blocked or just slow?"** — answered at least 3 times (07-02, 07-13/14, 07-21)
   with different partial answers each time (not IP-blocked / just slow+timeout / actually was
   IP-blocked that one time too). Current understanding: it's `flhouse.gov` application-layer
   bot detection, not an IP block — but IP-level blocks have also genuinely happened
   independently (07-21's `N3_ACTIVE_BLOCK`). Both are real; don't assume investigating one
   rules out the other.
2. **"Are we losing data?"** — asked and re-answered across 07-21 (overwrite bug, fixed),
   07-25/26 (shrink-guard duplicate bloat, fixed), and now 08-07 (per-vote regression across
   runs + format-side vote loss, both still open). Each time the answer has been "yes, but a
   different mechanism than last time" — worth checking this doc first before re-deriving from
   scratch.
3. **`BillDetail` resilience** — flagged as an explicit open decision on 07-24 ("deliberately
   not done"), never revisited since per the memory file. Still open.
4. **Maintainer's design-tension question** (unconditional `ResilientFetchPage` vs. opt-in) —
   posted 07-26, no confirmation found anywhere that it was ever answered.

## Source documents (for deeper drill-down on any dated entry above)

- `tamara-notes/archived_docs/fl-incremental-scraping-proposal.md` — the ~8,000-bill/~160-per-run
  scale problem and proposed checkpoint/resume designs (still unimplemented).
- `tamara-notes/archived_docs/fl-single-bill-failure-handoff.md` — deep technical handoff on the
  third bug (spatula generator mechanics).
- `tamara-notes/archived_docs/openstates-responses.md` — PR/issue thread history (#5724, #1386).
- `tamara-notes/archived_docs/state-problems.md`, `scraper-health.md`, `error-tracking.md`,
  `error-tracking-2026-07-02.md`, `problem-taxonomy.md`, `scraper-debugging-onboarding.md`,
  `scraper-fix-plan.md`, `bill-format-audit.md`, `bill-counts-by-jurisdiction.md`,
  `text-extraction-summary.md`, `TODO.md`, `2026-07-14-recovery-summary.md`,
  `2026-07-21-session-handoff.md`, `2026-07-21-notes-for-sartaj.md` — scattered FL mentions,
  all folded into the timeline above.
- `tamara-notes/scraper-status/not-working.md` — current FL status row + the detailed
  House-vote-scope writeup from this session (2026-08-05/07).
- `tamara-notes/scraper-status/pending-branches.md`, `morning-todo.md` — shrink-guard bug FL
  details.
- `tamara-notes/session-dates/session-calendar-2026.md`, `session-dates-comparison.md` — FL's
  actual session dates.
- Memory: `project-fl-single-bill-failure-fix.md` — the most detailed single source for the
  07-23–07-26 stretch.
