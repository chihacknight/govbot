# Session Dates: LegiScan vs. OpenStates

Side-by-side comparison of 2026 legislative session dates from the two sources we have
access to, so we can decide which to trust per state and know where OpenStates simply
doesn't have the data (in which case asking them to add it is the only fix).

- **LegiScan** — from `project_docs/archived_docs/session-dates/session-calendar-2026.md`
  (LegiScan 2026 Legislative Schedule, updated 2026-07-08). This is the source we trust
  most. Covers regular-session floor dates; territories (GU, MP, PR, VI) aren't LegiScan
  jurisdictions, so those rows there are sourced from each territory's own legislature site
  instead (noted per row).
- **OpenStates** — pulled live from the `v3.openstates.org/jurisdictions/{ocd_id}` API
  (`include=legislative_sessions`) on 2026-07-24, using the same jurisdiction-ID mapping and
  biennium end-date correction (`corrected_end_date`) as
  `actions/pipeline-manager/check-sessions.py`. **`check-sessions.py`'s automated
  session-pause pipeline is currently disabled** — its dates were repeatedly wrong and
  caused false "frozen" alarms — so this pull is a manual, one-off snapshot for comparison,
  not a live-trusted feed. Re-run to refresh; don't assume these dates stay current.

## How "OpenStates Matching Session" was picked

OpenStates' `legislative_sessions` array holds a state's entire history, mixing regular and
special sessions, and for many states represents a **whole 2-year term as a single session
object** (e.g. "2025-2026 Regular Session") rather than the specific floor dates LegiScan
tracks for a given year. For each state we picked the OpenStates session that best matches
LegiScan's convene date:

1. LegiScan's convene date falls inside the OpenStates session's `[start, end]` range, or
2. the convene year appears in the OpenStates session's identifier/name, or
3. the OpenStates session starts within a year of LegiScan's convene date.

Special sessions were excluded from this match (they're called out separately in the Notes
column instead, since LegiScan's row is regular-session-only).

## Agreement key

| Symbol | Meaning |
|---|---|
| ✅ match | Convene and adjourn dates agree exactly |
| ⚠️ adjourn/convene differs | One end agrees, the other doesn't — worth a quick manual check |
| ⚠️ mismatch | Neither end agrees — treat OpenStates as unreliable here, LegiScan is authoritative |
| ℹ️ within OpenStates biennium | OpenStates' full-term session object contains LegiScan's floor dates — not a real disagreement, just coarser granularity |
| ℹ️ LegiScan says no 2026 regular session | State has no regular session this year (MT/ND/NV/TX); OpenStates' nearest non-special match is stale history, not evidence otherwise |
| ❓ no OpenStates coverage | OpenStates has no `legislative_sessions` data for this jurisdiction at all |

## Comparison table

| Code | Jurisdiction | LegiScan Session | LegiScan Convenes | LegiScan Adjourns | OpenStates Matching Session | OpenStates Convenes | OpenStates Adjourns | Agreement | Notes |
|---|---|---|---|---|---|---|---|---|---|
| AK | Alaska | 34th Legislature | 2026-01-20 | 2026-05-20 | 34th Legislature (2025-2026) | 2025-01-21 | 2025-05-21 | ⚠️ mismatch | LegiScan note: Special Session May 21. LegiScan `2026-01-20→2026-05-20` vs OpenStates `2025-01-21→2025-05-21` — OpenStates appears to be reporting the *first* year of this 2-year legislature rather than 2026, unlike most other biennium states where it spans the full range. Worth a manual check. |
| AL | Alabama | 2026 Regular Session | 2026-01-13 | 2026-04-09 | 2026 Regular Session | 2026-01-13 | 2026-04-02 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-04-09` vs OpenStates `2026-04-02`. |
| AR | Arkansas | 95th General Assembly | 2026-04-08 | 2026-04-29 | 2026 Fiscal Session | 2026-04-08 | 2026-05-01 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-04-29` vs OpenStates `2026-05-01`. OpenStates also lists 1 special session since 2025 not reflected in LegiScan's row. |
| AZ | Arizona | 57th Legislature | 2026-01-12 | 2026-06-13 | 57th Legislature - Second Regular Session | 2026-01-12 | 2026-04-25 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-06-13` vs OpenStates `2026-04-25`. |
| CA | California | 2025-2026 Biennium | 2026-01-05 | 2026-08-31 | 2025-2026 Regular Session | 2024-12-02 | 2026-11-30 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| CO | Colorado | 2026 Regular Session | 2026-01-14 | 2026-05-13 | 2026 Regular Session | 2026-01-14 | 2026-05-13 | ✅ match | OpenStates also lists 1 special session since 2025. |
| CT | Connecticut | 2026 Regular Session | 2026-02-04 | 2026-05-06 | 2026 Regular Session | 2026-02-04 | 2026-05-06 | ✅ match | — |
| DC | District of Columbia | 26th Council | 2026-01-02 | 2026-12-31 | 26th Council Period (2025-2026) | 2025-01-02 | 2026-12-31 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| DE | Delaware | 153rd General Assembly | 2026-01-13 | 2026-06-30 | 153rd General Assembly (2025-2026) | 2025-01-14 | 2026-06-30 | ℹ️ within OpenStates biennium | — |
| FL | Florida | 2026 Regular Session | 2026-01-13 | 2026-03-13 | 2026 Regular Session | 2026-01-13 | 2026-03-13 | ✅ match | OpenStates also lists 6 special sessions since 2025 (A/B/C 2025, D/E/F 2026) — see `state-status-reference.md` FL row for the active bug-fix work happening on this state right now. |
| GA | Georgia | 2025-2026 Biennium | 2026-01-12 | 2026-04-02 | 2025-2026 Regular Session | 2025-01-13 | 2026-04-02 | ℹ️ within OpenStates biennium | — |
| GU | Guam | 38th Legislature | 2025-01-06 | 2026-12-31 | 38th Guam Legislature | 2025-01-01 | 2026-12-31 | ℹ️ within OpenStates biennium | LegiScan note: year-round, sessions called as needed, not a fixed calendar; source guamlegislature.gov. |
| HI | Hawaii | 2026 Regular Session | 2026-01-21 | 2026-05-08 | 2026 Regular Session | 2026-01-21 | 2026-05-08 | ✅ match | — |
| IA | Iowa | 91st General Assembly | 2026-01-12 | 2026-04-21 | 2025-2026 Regular Session | 2025-01-13 | 2025-04-22 | ⚠️ mismatch | LegiScan `2026-01-12→2026-04-21` vs OpenStates `2025-01-13→2025-04-22` — OpenStates' end date looks stuck in 2025 despite the biennium-correction logic; worth a manual check. |
| ID | Idaho | 2026 Regular Session | 2026-01-12 | 2026-04-02 | 68th Legislature, 2nd Regular Session (2026) | 2026-01-05 | 2026-04-10 | ⚠️ mismatch | LegiScan `2026-01-12→2026-04-02` vs OpenStates `2026-01-05→2026-04-10` — both in 2026, but off by about a week on each end. Worth a manual check. |
| IL | Illinois | 104th General Assembly | 2026-01-14 | 2026-05-31 | 104th Regular Session | 2025-01-08 | 2025-05-31 | ⚠️ mismatch | LegiScan `2026-01-14→2026-05-31` vs OpenStates `2025-01-08→2025-05-31` — OpenStates is a full year behind. IL is self-hosted/actively scraped (see `state-status-reference.md`) so this is worth flagging to OpenStates. |
| IN | Indiana | 2026 Regular Session | 2025-12-01 | 2026-02-27 | 2025 Regular Session | 2025-01-09 | 2025-04-29 | ⚠️ mismatch | LegiScan `2025-12-01→2026-02-27` vs OpenStates `2025-01-09→2025-04-29` — OpenStates' latest entry is Indiana's *previous* regular session, not the short session covering LegiScan's Dec 2025–Feb 2026 window. |
| KS | Kansas | 2025-2026 Biennium | 2026-01-12 | 2026-04-10 | 2025-2026 Regular Session | 2025-01-13 | 2025-05-06 | ⚠️ mismatch | LegiScan `2026-01-12→2026-04-10` vs OpenStates `2025-01-13→2025-05-06` — OpenStates' end date is stuck in 2025 despite being labeled a 2025-2026 biennium; worth a manual check. |
| KY | Kentucky | 2026 Regular Session | 2026-01-06 | 2026-04-15 | 2026 Regular Session | 2026-01-06 | 2026-04-15 | ✅ match | — |
| LA | Louisiana | 2026 Regular Session | 2026-03-09 | 2026-06-01 | 2026 Regular Session | 2026-03-09 | 2026-06-01 | ✅ match | OpenStates also lists 1 special session since 2025. |
| MA | Massachusetts | 194th General Court | 2026-01-07 | 2026-07-31 | 194th Legislature (2025-2026) | 2025-01-01 | 2026-07-31 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| MD | Maryland | 2026 Regular Session | 2026-01-14 | 2026-04-13 | 2026 Regular Session | 2026-01-14 | 2026-04-13 | ✅ match | LegiScan note: Special Session August 3rd. |
| ME | Maine | 132nd Legislature | 2026-01-07 | 2026-04-15 | 132nd Legislature (2025-2026) | 2024-12-04 | 2025-06-18 | ⚠️ mismatch | LegiScan `2026-01-07→2026-04-15` vs OpenStates `2024-12-04→2025-06-18` — OpenStates' end date is stuck in 2025 despite being labeled a 2025-2026 legislature; worth a manual check. |
| MI | Michigan | 103rd Legislature | 2026-01-14 | 2026-12-31 | 2025-2026 Regular Session | 2025-01-08 | 2026-12-31 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| MN | Minnesota | 94th Legislature | 2026-02-17 | 2026-05-18 | 2025-2026 Regular Session | 2025-01-14 | 2026-05-20 | ℹ️ within OpenStates biennium | — |
| MO | Missouri | 2026 Regular Session | 2026-01-07 | 2026-05-15 | 2026 Regular Session | 2026-01-07 | 2026-05-15 | ✅ match | — |
| MP | Northern Mariana Islands | 24th Legislature | 2025-01-06 | 2026-12-31 | *(none)* | — | — | ❓ no OpenStates coverage | LegiScan note: year-round, regular + special sessions called as needed; source cnmileg.net. OpenStates has no `legislative_sessions` data for MP at all — consistent with `check-sessions.py`'s known "no scraper coverage" case. Worth filing with OpenStates if we ever need their feed for MP. |
| MS | Mississippi | 2026 Regular Session | 2026-01-06 | 2026-04-15 | 2026 Regular Session | 2025-01-06 | 2025-04-05 | ⚠️ mismatch | LegiScan `2026-01-06→2026-04-15` vs OpenStates `2025-01-06→2025-04-05` — OpenStates is a full year behind. OpenStates also lists 1 special session since 2025. |
| MT | Montana | No Regular Session | — | — | 2025 Regular Session | 2025-01-06 | 2025-05-03 | ℹ️ LegiScan says no 2026 regular session | LegiScan note: no regular session in 2026 (meets biennially). OpenStates' nearest match is its 2025 session — not evidence of a 2026 session, just the closest thing in its history. See `project_docs/state-problems.md` for MT's separate, unrelated `P1` shrink-guard investigation. |
| NC | North Carolina | 2025-2026 Biennium | 2026-04-21 | 2026-07-27 | 2025-2026 Session | 2025-01-11 | 2026-07-01 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. OpenStates also lists 1 special session since 2025. |
| ND | North Dakota | No Regular Session | — | — | 70th Legislative Assembly (2027-28) | 2027-01-07 | 2028-05-02 | ℹ️ LegiScan says no 2026 regular session | LegiScan note: no regular session in 2026 (meets biennially). OpenStates' nearest non-special match is its *next* assembly (2027-28), not evidence of anything in 2026. |
| NE | Nebraska | 109th Legislature | 2026-01-07 | 2026-04-17 | 109th Legislature (2025-2026) | 2025-01-08 | 2026-04-19 | ℹ️ within OpenStates biennium | — |
| NH | New Hampshire | 2026 Regular Session | 2026-01-07 | 2026-06-04 | 2026 Regular Session | 2026-01-08 | 2026-06-30 | ⚠️ mismatch | LegiScan `2026-01-07→2026-06-04` vs OpenStates `2026-01-08→2026-06-30` — same year, convene dates a day apart, but adjourn dates ~4 weeks apart. Worth a manual check. |
| NJ | New Jersey | 2026-2027 Biennium | 2026-01-13 | 2028-01-11 | 2026-2027 Regular Session | 2026-01-13 | 2027-12-31 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| NM | New Mexico | 2026 Regular Session | 2026-01-20 | 2026-02-19 | 2026 Regular Session | 2026-01-20 | 2026-02-19 | ✅ match | OpenStates also lists 2 special sessions since 2025. |
| NV | Nevada | No Regular Session | — | — | 2025 Regular Session | 2025-02-01 | 2025-06-01 | ℹ️ LegiScan says no 2026 regular session | LegiScan note: no regular session in 2026 (meets biennially, no regular session until 2027 per `state-status-reference.md`). OpenStates' nearest match is its 2025 session. OpenStates also lists 1 special session since 2025. |
| NY | New York | 2025-2026 Biennium | 2026-01-07 | 2026-06-05 | 2025 Regular Session | 2025-01-08 | 2026-12-31 | ℹ️ within OpenStates biennium | — |
| OH | Ohio | 136th General Assembly | 2026-01-05 | 2026-12-31 | 136th Legislature (2025-2026) | 2025-01-06 | 2026-12-31 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| OK | Oklahoma | 2026 Regular Session | 2026-02-02 | 2026-05-14 | 2026 Regular Session | 2026-02-02 | 2026-05-29 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-05-14` vs OpenStates `2026-05-29`. |
| OR | Oregon | 2026 Regular Session | 2026-02-02 | 2026-03-06 | 2026 Regular Session | 2026-02-02 | 2026-03-09 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-03-06` vs OpenStates `2026-03-09`. OpenStates also lists 1 special session since 2025. |
| PA | Pennsylvania | 2025-2026 Biennium | 2026-01-06 | 2026-11-30 | 2025-2026 Regular Session | 2025-01-07 | 2026-11-30 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| PR | Puerto Rico | 2026 Regular Session | 2026-01-12 | 2026-06-30 | 2025-2028 Session | 2025-01-13 | 2028-12-31 | ℹ️ within OpenStates biennium | LegiScan note: regular session ends Jun 30 by law (~90 days), special sessions can be called; source senado.pr.gov. OpenStates' object spans the full 4-year term (2025-2028), coarser than any other state. |
| RI | Rhode Island | 2026 Regular Session | 2026-01-06 | 2026-06-11 | 2026 Regular Session | 2026-01-02 | 2026-06-30 | ⚠️ mismatch | LegiScan `2026-01-06→2026-06-11` vs OpenStates `2026-01-02→2026-06-30` — same year, ~3 week gap on adjourn. Worth a manual check. |
| SC | South Carolina | 126th General Assembly | 2026-01-13 | 2026-05-14 | 2025-2026 Regular Session | 2025-01-14 | 2025-05-08 | ⚠️ mismatch | LegiScan note: Special Session May 15. LegiScan `2026-01-13→2026-05-14` vs OpenStates `2025-01-14→2025-05-08` — OpenStates is a full year behind despite being labeled a 2025-2026 session. |
| SD | South Dakota | 2026 Regular Session | 2026-01-13 | 2026-03-30 | 2026 Regular Session | 2026-01-14 | 2026-03-31 | ⚠️ mismatch | LegiScan `2026-01-13→2026-03-30` vs OpenStates `2026-01-14→2026-03-31` — both 2026, off by a day on each end. Close enough it may just be a reporting-date convention difference. |
| TN | Tennessee | 114th General Assembly | 2026-01-13 | 2026-04-24 | 114th Regular Session (2025-2026) | 2025-01-14 | 2026-04-25 | ℹ️ within OpenStates biennium | OpenStates also lists 2 special sessions since 2025. |
| TX | Texas | No Regular Session | — | — | 89th Legislature (2025) | 2025-01-10 | 2025-06-02 | ℹ️ LegiScan says no 2026 regular session | LegiScan note: no regular session in 2026 (biennial, next regular session 2027). OpenStates' nearest match is its 2025 session. OpenStates also lists 2 special sessions since 2025 — see `tx-backfill-runbook.md`, TX blocks GitHub Actions IPs and is self-hosted-only. |
| USA | US Congress | 119th Congress | 2026-01-03 | 2026-10-30 | 119th Congress | 2025-01-03 | 2027-01-03 | ℹ️ within OpenStates biennium | LegiScan note: end date estimated. |
| UT | Utah | 2026 Regular Session | 2026-01-20 | 2026-03-07 | 2026 General Session | 2026-01-20 | 2026-03-06 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-03-07` vs OpenStates `2026-03-06`. OpenStates also lists 2 special sessions since 2025. |
| VA | Virginia | 2026 Regular Session | 2026-01-14 | 2026-03-14 | 2026 Regular Session | 2026-01-14 | 2026-03-14 | ✅ match | — |
| VI | Virgin Islands | 36th Legislature | 2025-01-06 | 2026-12-31 | 2025-2026 Regular Session | 2025-01-09 | 2026-12-31 | ⚠️ convene differs | LegiScan note: year-round, regular sessions called as needed; source legvi.org. Convene dates 3 days apart, adjourn dates agree. |
| VT | Vermont | 2025-2026 Biennium | 2026-01-06 | 2026-05-29 | 2025-2026 Regular Session | 2025-01-08 | 2025-05-08 | ⚠️ mismatch | LegiScan `2026-01-06→2026-05-29` vs OpenStates `2025-01-08→2025-05-08` — OpenStates' end date is stuck in 2025 despite being labeled a 2025-2026 biennium; worth a manual check. |
| WA | Washington | 2025-2026 Biennium | 2026-01-12 | 2026-03-12 | 2025-2026 Regular Session | 2025-01-13 | 2026-03-06 | ℹ️ within OpenStates biennium | — |
| WI | Wisconsin | 2025-2026 Biennium | 2026-01-13 | 2026-03-19 | 2025-2026 Regular Session | 2025-01-06 | 2026-05-25 | ℹ️ within OpenStates biennium | OpenStates also lists 1 special session since 2025. |
| WV | West Virginia | 2026 Regular Session | 2026-01-14 | 2026-03-14 | 2026 Regular Session | 2026-01-14 | 2026-03-14 | ✅ match | — |
| WY | Wyoming | 2026 Budget Session | 2026-02-09 | 2026-03-11 | 2026 Regular Session | 2026-02-09 | 2026-03-06 | ⚠️ adjourn differs | Convene dates agree; LegiScan adjourn `2026-03-11` vs OpenStates `2026-03-06`. |

## Triage: what to do with this

**Trust LegiScan, ignore OpenStates for session dates on these 10 states** — OpenStates'
own "matching" session is a full year (or more) stale, despite being labeled as covering
the current biennium: **IA, IL, KS, ME, MS, SC, VT** (end date stuck in the wrong year), plus
**IN** (latest entry is the *previous* regular session entirely). This is the same class of
bug `check-sessions.py`'s `corrected_end_date()` was written to patch for *some* cases (DC,
MI, PA, NC as of 2026-06-30) — these 7 show it's broader than that patch covers. **AK** looks
like the same failure mode but inverted (OpenStates reports the *first* year of the
biennium instead of extending through it).

**Small gaps, low priority** — **AL, AR, AZ, OK, OR, UT, WY** (adjourn dates a few days to a
few weeks apart, convene agrees), **SD** (both ends a day apart), **VI** (convene 3 days
apart). Not worth chasing unless a specific scrape decision depends on the exact day.

**Genuinely worth a manual look** — **NH, RI** (same year, but adjourn dates weeks apart
with no obvious single-cause pattern like the others).

**No regular session in 2026, correctly so** — **MT, ND, NV, TX** — OpenStates has no 2026
data because there isn't any; its "closest match" is just old history, not a contradiction.

**No OpenStates data at all** — **MP**. If we ever want OpenStates as a source for MP,
that's a "please add coverage" ask to them, not a bug to chase on our end.

**Biennium granularity, not a real disagreement (25 states)** — **CA, DC, DE, GA, GU, MA,
MI, MN, NC, NE, NJ, NY, OH, PA, PR, TN, USA, WA, WI**, plus a few above already counted
under other buckets. OpenStates represents the whole 2-year term as one session object;
LegiScan's dates are the specific floor-session window within it. Both are "correct," just
different granularity — no action needed.

## Related docs

- `docs/src/state-status-reference.md` — the operational per-state table (scraper health,
  hosting path, session config) this doc is meant to feed the "Session Dates (verified)"
  column of
- `project_docs/archived_docs/session-dates/session-calendar-2026.md` — the LegiScan source
  data this doc compares against
- `actions/pipeline-manager/check-sessions.py` — the disabled automated session-pause script
  whose OpenStates-fetch logic and known biennium-end-date bug this doc's methodology reuses
