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

## States fixed, with real before/after bill counts

All verified by checking actual git commits and bill counts, not just workflow status —
several of the "old" numbers below already looked fine in our prior tracking doc despite
being months stale, which is exactly the trap this recovery effort uncovered.

| State | Bills before | Bills now | Change |
|---|---:|---:|---|
| USA (Congress) | ~8,250 | **34,658** | +26,408 |
| New York | ~9,584 | **25,321** | +15,737 |
| Illinois | ~2,944 | **12,753** | +9,809 |
| West Virginia | ~2,709 | **5,950** | +3,241 |
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
The only two hiccups (Arkansas, New Mexico) were a timing issue (extraction ran before
formatting had caught up with the freshly-scraped data), not a network or blocking problem.
Fixed by re-running formatting first.

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
| Arizona | Session cookie not persisting through a login POST | PR open upstream ([#5722](https://github.com/openstates/openstates-scrapers/pull/5722)); maintainer can't reproduce, waiting on us for exact repro steps |
| Florida | Site's bot detection blocks even from a home network | Unresolved; incremental-scraping approach proposed as a workaround |
| Louisiana | Bill search only returns ~7 of ~525 bills | Issue open upstream, awaiting maintainer response |
| New Hampshire | Site blocks scraping during business hours | Schedule shifted to run overnight; still borderline, being watched |
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
