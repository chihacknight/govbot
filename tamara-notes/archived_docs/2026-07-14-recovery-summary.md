# Scraper Recovery Summary — 2026-07-14

Shareable summary of what we found and fixed over the last two days. Written for the team,
not just for future-Claude — see `actions/scrape/docs/scraper-health.md` and
`actions/pipeline-manager/docs/staleness-audit-spec.md` for the deeper technical writeups
behind each finding.

## The headline finding

An audit of every `govbot-data` state repo — checking the last commit that actually touched
real bill data, not the daily tracking-file commit every repo gets regardless of whether
anything changed — found **16 states plus the USA/federal repo frozen at December 14, 2025**.
Over 7 months of silently stale data, despite every scheduled workflow reporting a green
checkmark the whole time. Nothing crashed; the scraper is deliberately built to never
hard-fail, so a state quietly getting zero or unchanged data every night looked identical to
a healthy one.

None of this was anyone's fault in the moment — self-hosted runners (the actual fix) didn't
exist as a capability until 2026-07-13, and the project runs on a part-time, seasonal basis.
It's fixed now, and we built a tool (`audit-data-staleness.sh`) to catch this pattern early
next time instead of finding it by accident again.

## States fixed, with before/after JSON file counts

**A note on what this table actually measures**: these numbers are counts of raw JSON files
(scraped bills + vote events + events combined) in each state's data folder, not a count of
distinct bills — a single bill can have several files (its own record, plus one per vote
event, plus one per action/event). We caught this because the USA row didn't match the
formatter's own authoritative bill count (see below), the same way the GitHub UI's "truncated
directory" display didn't reflect the real number earlier. Treat the "Change" column as a
reliable signal that real new data landed (all of it was frozen at zero before), but not as a
literal bill count. Only the USA row below has been cross-checked against the formatter's own
count; the other 17 were built the same way and haven't been re-verified yet.

| State | Files before | Files now | Change |
|---|---:|---:|---|
| USA (Congress) | ~8,250 | 34,658 (**14,474 distinct bills**, per formatter's own count) | data unfrozen |
| New York | ~9,584 | **25,321** | +15,737 |
| Illinois | ~2,944 | **12,753** | +9,809 |
| West Virginia | ~2,709 | **5,950** | +3,241 |
| Louisiana | ~7 (blocked) | **5,792** | data unfrozen — old "~525" total baseline was itself stale/wrong |
| South Carolina | ~3,051 | **5,091** | +2,040 |
| Pennsylvania | ~3,578 | **4,857** | +1,279 |
| Michigan | ~2,360 | **3,848** | +1,488 |
| Ohio | ~1,538 | **2,439** | +901 |
| North Carolina | 1,794 | **2,334** | +540 |
| Nebraska | ~1,037 | **1,632** | +595 |
| Vermont | 898 | **1,718** | +820 |
| Indiana | 40 | **935** | +895 |
| Alaska | 514 | **856** | +342 |
| New Mexico | 2 | **812** | +810 |
| Virginia | 0 (broken) | **299** | +299 |
| Arkansas | 1,928 (historical, frozen) | **2 new** (current session) | current session unblocked; historical data untouched/preserved separately |
| U.S. Virgin Islands | 148 | 148 | resumed running; same count so far, watch next cycle |
| Nevada | 27 | 27 | correct as-is — NV meets biennially, no regular session until 2027 |

**Root cause, in short**: every one of these states simply needed `runner: self-hosted`
turned on (several were also sitting on a "paused" template that had silently stripped their
nightly schedule entirely). No scraper code changes were needed for any of them — the
scrapers themselves were already correct; GitHub-hosted runner IPs were the problem, either
via outright blocking or the state site quietly serving degraded content to Azure IP ranges.

**Text extraction** was audited separately across all these states — clean across the board.
See the "Text extraction results" section at the bottom of this doc for the full breakdown.

## New capability: routing around IP blocks without a laptop

Separately from self-hosted runners, we set up and proved a second option: a small always-on
cloud VM running a proxy (tinyproxy), so GitHub-hosted runners can route through it instead
of needing Tamara's laptop to be on and awake. Confirmed working end-to-end for West
Virginia. Self-hosted runners remain the primary fix for now; the proxy is a backup option
for when runner capacity is the bottleneck, or eventually as the main path if it proves more
reliable than depending on a laptop staying online.

## Known issues still open (not touched by this recovery pass)

These are pre-existing, already-diagnosed problems, unaffected by the December freeze:

| State | Issue | Status |
|---|---|---|
| Arizona | Session cookie not persisting through a login POST | PR open upstream ([#5722](https://github.com/openstates/openstates-scrapers/pull/5722)); confirmed 2026-07-14 with a fresh self-hosted run (non-Azure IP) — 100% repro rate, identical failure across all 3 retries, so it's not an IP-blocking issue. Posted the run log + exact repro command [as a comment](https://github.com/openstates/openstates-scrapers/pull/5722#issuecomment-4972662364); maintainer still couldn't reproduce it themselves, waiting on their response |
| Florida | Not actually a blocking issue — re-diagnosed 2026-07-14 | ⏳ **Currently waiting on scraper to finish.** A self-hosted run got no bot-detection errors at all, just ran out of its 12-hour time limit partway through (FL is a very large, slow-to-scrape session). Timeout raised to 24h and a longer self-hosted run is in progress; real long-term fix is committing progress incrementally instead of only at the end, so a timeout doesn't lose everything gathered |
| Louisiana | Bill search only returns ~7 of ~525 bills | ✅ **Fixed 2026-07-14.** Same IP-blocking pattern as IL/WV/NC, not a real scraper bug — the old "~525" total was itself based on stale/blocked data. Self-hosted run scraped **2,616 bills** cleanly (`5791 insertions(+), 10 deletions(-)`), far more than previously thought existed. Moved out of "known issues" |
| New Hampshire | Not just a business-hours block — a real data-loss bug found 2026-07-14 | A self-hosted run got rate-limited (`H3_RATE_LIMITED`) after scraping only jurisdiction/org metadata (zero bills). `scrape.sh` treated those 4 leftover files as "the scrape," wholesale-deleted 436 real bill/vote files from `_data/nh/` and overwrote the nightly fallback release with the same near-empty data — so the fallback safety net was gone too. **Fixed and pushed**: the wipe/rebuild step now requires the scrape to have actually succeeded (`exit_code == 0`), not just "some JSON files exist." **436 deleted files restored** directly to `govbot-openstates-scrapers/nh-legislation` main (commit `59c1af823`, restoring the last known-good snapshot from before the bad wipe — nothing else had touched `_data/nh/` in between). Overnight-only scheduling stays in place as a real, separate mitigation for the business-hours block |
| N. Mariana Islands | Crashes on one specific bill with a blank title | Root cause identified, fix not yet filed upstream |
| Guam | Each bill gets saved ~3x per run (wasted requests, no data loss) | Root cause identified, fix not yet filed upstream |
| Idaho, Maryland, Utah, Wyoming | Only "active" bills returned — completed sessions undercounted | Root cause confirmed for Wyoming (API filters out signed/enrolled bills); same pattern suspected for the others |
| Nevada | Missing an entire historical session (~1,000+ bills from 2025) | Lower priority — current data is correct going forward, this is a one-time backfill gap |

## What changed operationally

- `check-sessions.py`'s automated pause/resume was **disabled** — its session-date source
  (the OpenStates API) has proven repeatedly inaccurate this pass, and it was about to
  silently re-pause several of the states we just fixed. Needs a real fix or replacement
  before re-enabling.
- Fixed a macOS-specific bug (`tar --mode=755`) that made every self-hosted run's summary
  falsely report "nightly fallback" / no data, even on runs that fully succeeded — purely
  cosmetic, but it was actively confusing to anyone checking run results.
- Fixed a real data-loss bug in `scrape.sh`, found via the New Hampshire investigation above:
  a failed scrape that still left a few partial files on disk (e.g. rate-limited right after
  metadata but before any bills) was being treated as a successful scrape, wiping real
  historical data from the git repo *and* corrupting the nightly fallback release with the
  same partial output. Now gated on the scrape having actually succeeded, not just "some JSON
  files exist on disk." Applies to every state, not just NH.

## Text extraction results (govbot-test org)

Full audit of `extract-text.yml` across all 18 recovered states, run against the `govbot-test`
pilot org (which will eventually become the real `govbot-data` once cut over). Format ran
clean everywhere with zero failures. Extraction:

| State | Result | Notes |
|---|---|---|
| Alaska, Illinois, Indiana, Michigan, Nebraska, Nevada, New York, Ohio, Pennsylvania, South Carolina, USA, Virginia, Vermont, North Carolina, West Virginia | ✅ Clean | Zero errors, first pass |
| Arkansas | ✅ Clean | 2/2 bills extracted successfully, after a re-run (see below) |
| New Mexico | ✅ 809/812 (99.6%) | 3 dead-link 404s on the source site, same minor category as Hawaii's known issue — not a real problem |
| U.S. Virgin Islands | ✅ Clean | |
| New Hampshire | ✅ Clean | 334/334 bills, 0 errors — run after the `scrape.sh` fallback-bug fix and full data restore (see above); confirms the restored data is fully extractable |

**One real (and reassuring) finding along the way**: Arkansas and New Mexico both showed a
hard `failure` on the *first* extraction attempt — but it turned out to be a sequencing
issue, not a data problem. Extraction ran before formatting had caught up with the
freshly-scraped data, so there was nothing there yet to extract from. Re-running formatting
first, then re-running extraction, resolved both cleanly. **No state in this whole 18-state
recovery needed a proxy, a code fix, or any further investigation on the extraction side** —
every single issue found was either already-known-and-minor (dead links) or a one-time
sequencing gap, not a new problem.

**Workflow design note worth knowing**: `extract-text.yml` currently treats *any* single
failed bill as a hard job failure (exit code 1), which is why New Mexico's 809/812 — a great
result — initially looked identical to a fully broken run in the GitHub Actions UI. A design
note for fixing this (separating "did the job complete" from "how many bills had errors") is
written up at `actions/extract/docs/error-log-design-note.md`, not yet built.
