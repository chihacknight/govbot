# Scrape Action — Error Tracking

Track the status of the scrape action across all 57 jurisdictions.

**Statuses:** `✅ OK` | `❌ Broken` | `⚠️ Intermittent` | `⏸️ Unknown`

Last updated: 2026-07-14

## Read this before trusting any row

The previous version of this doc (archived at
`actions/scrape/docs/archive/error-tracking-2026-07-02.md`) tracked bill counts only. That
missed the real problem: 16 states plus USA were frozen at December 2025 data for over 7
months while looking completely healthy, because a large leftover bill count looks the same
whether it's current or months stale. See
`actions/pipeline-manager/docs/staleness-audit-spec.md` for the full story and
`actions/scrape/docs/2026-07-14-recovery-summary.md` for what got fixed.

**This version adds a "Last Verified Fresh" column** — the date someone actually confirmed
(via a real commit + bill count check, not just a green workflow status) that a state's data
is current. A row with an old date there isn't necessarily broken — it just hasn't been
re-checked, which is a different and more honest thing to say than implying it's fine.
Run `actions/pipeline-manager/scripts/audit-data-staleness.sh` periodically to refresh this
column at scale instead of manually re-verifying one state at a time.

## Full Status Table

| Jurisdiction | Code | Status | Bill Count | Last Verified Fresh | Notes |
|---|---|---|---:|---|---|
| USA (Congress) | usa | ✅ OK | 34,658 | 2026-07-14 | Was frozen at ~8,250 since 2025-12-14; fixed via self-hosted runner |
| New York | ny | ✅ OK | 25,321 | 2026-07-14 | Was frozen at ~9,584 since 2025-12-14; fixed via self-hosted runner. Requires `NEW_YORK_API_KEY` |
| Illinois | il | ✅ OK | 12,753 | 2026-07-14 | Was frozen at ~2,944 since 2025-12-14; fixed via self-hosted runner. Two real upstream markup fixes also landed ([#5721](https://github.com/openstates/openstates-scrapers/pull/5721), [#5730](https://github.com/openstates/openstates-scrapers/pull/5730)) |
| West Virginia | wv | ✅ OK | 5,950 | 2026-07-14 | Was reporting 39 vs expected 2,975; not a scraper bug, Azure IP block. Fixed via self-hosted runner + proven working via tinyproxy too |
| South Carolina | sc | ✅ OK | 5,091 | 2026-07-14 | Was frozen at ~3,051 since 2025-12-14; fixed via self-hosted runner |
| Pennsylvania | pa | ✅ OK | 4,857 | 2026-07-14 | Was frozen at ~3,578 since 2025-12-14; fixed via self-hosted runner |
| Michigan | mi | ✅ OK | 3,848 | 2026-07-14 | Was frozen at ~2,360 since 2025-12-14; fixed via self-hosted runner |
| Ohio | oh | ✅ OK | 2,439 | 2026-07-14 | Was frozen at ~1,538 since 2025-12-14; fixed via self-hosted runner |
| North Carolina | nc | ✅ OK | 2,334 | 2026-07-14 | Was frozen at 1,794 since 2025-12-14; root cause was a plain config gap (never had `runner: self-hosted` set), not an IP block — see `scraper-health.md` |
| Nebraska | ne | ✅ OK | 1,632 | 2026-07-14 | Was frozen at ~1,037 since 2025-12-14; fixed via self-hosted runner |
| Vermont | vt | ✅ OK | 1,718 | 2026-07-14 | Was frozen at 898 since 2025-12-14; fixed via self-hosted runner |
| Indiana | in | ✅ OK | 935 | 2026-07-14 | Was frozen at 40 since 2025-12-14; fixed via self-hosted runner |
| Alaska | ak | ✅ OK | 856 | 2026-07-14 | Was frozen at 514 since 2025-12-14; fixed via self-hosted runner |
| New Mexico | nm | ✅ OK | 812 | 2026-07-14 | Was frozen at 2 since 2025-12-14; fixed via self-hosted runner. Extraction had a one-time timing issue (ran before format caught up), resolved |
| Virginia | va | ✅ OK | 299 | 2026-07-14 | Was 0 (broken); fixed via self-hosted runner. Upstream `csv_bills` fixes ([#5717](https://github.com/openstates/openstates-scrapers/pull/5717), [#5725](https://github.com/openstates/openstates-scrapers/pull/5725)) also landed. Issues [#1377](https://github.com/openstates/issues/issues/1377)/[#1385](https://github.com/openstates/issues/issues/1385) still open upstream despite being fixed — worth closing |
| Arkansas | ar | ✅ OK | 1,928 historical + 2 current | 2026-07-14 | Current session (2026S1) was frozen/empty since 2025-12-14; fixed via self-hosted runner, now correctly getting the 2 live 2026S1 bills (SB1, HB1001). Historical 2025 data untouched |
| U.S. Virgin Islands | vi | ⏸️ Unknown | 148 | 2026-07-14 (resumed, count unchanged) | Was disabled/no runs since 2026-04-01; resumed via self-hosted runner but bill count didn't grow — watch next cycle to confirm it's actually finding new data vs. just not erroring |
| Nevada | nv | ✅ OK | 27 | 2026-07-14 | Correct as-is — NV meets biennially, no regular session until 2027. Still missing ~1,000+ bills from the 83rd Regular Session (2025), a separate one-time backfill gap, not an ongoing issue |
| Arizona | az | ❌ Broken | — | 2026-07-02 (not re-verified) | `AssertionError: Session ID not in bill list` — cookie not persisted through `setsession.php` POST. PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) open; maintainer can't reproduce, waiting on us for exact repro steps. Confirmed self-hosting does NOT fix this one (same failure on home network) |
| Florida | fl | ❌ Broken | 1,916+ (stale) | 2026-07-02 (not re-verified) | Site's bot detection (`spatula.pages.RejectedResponse`) blocks even from a self-hosted home IP. Incremental-scraping proposal filed as a workaround, not yet built |
| Louisiana | la | ⚠️ Intermittent | 12 / 7 (stale) | 2026-07-02 (not re-verified) | Bill search only returns ~7 of ~525 bills. Issue [#1379](https://github.com/openstates/issues/issues/1379) open, awaiting maintainer |
| N. Mariana Islands | mp | ❌ Broken | 302 (stale) | 2026-07-02 (not re-verified) | Crashes on the same bill every run (`HCommRes 24-6`, blank title fails OCD validation). Fix identified, not yet filed upstream |
| Guam | gu | ✅ OK | 277 (stale) | 2026-07-02 (not re-verified) | Each bill saved ~3x per run with different UUIDs — wasted requests, no data loss (format layer dedupes). Fix identified, not yet filed upstream |
| Idaho | id | ✅ OK | 790 / 1 (stale) | 2026-07-02 (not re-verified) | Completed 2026 session only shows 1 bill — likely only "active/pending" bills are returned by the endpoint used. Same pattern as MD/UT/WY |
| Maryland | md | ⚠️ Intermittent | 2,617+ / 531 (stale) | 2026-07-02 (not re-verified) | Same "active bills only" pattern as ID/UT/WY |
| Utah | ut | ✅ OK | 18/5/3 (stale) | 2026-07-02 (not re-verified) | Same "active bills only" pattern as ID/MD/WY |
| Wyoming | wy | ✅ OK | 556/23 (stale) | 2026-07-02 (not re-verified) | Root cause confirmed: API filter excludes `enrolled`/`inactive` bills — misses the budget session's actual purpose (the 3 budget bills themselves). Not yet fixed upstream |
| New Hampshire | nh | ❌ Broken | 1,072+/1,393+ (stale) | 2026-07-02 (not re-verified) | Site blocks scraping 6am-9pm ET; schedule shifted to overnight, still borderline |
| Connecticut | ct | ✅ OK | 4,076+ (stale) | 2026-07-02 (not re-verified) | Was Azure-IP-blocked on FTP; fixed via self-hosted runner as of 2026-07-02, prior to this pass |
| Hawaii | hi | ✅ OK | 3,067+ (stale) | 2026-07-02 (not re-verified) | Was Cloudflare-WAF-blocked; fixed via self-hosted runner as of 2026-07-02, prior to this pass |
| Massachusetts | ma | ✅ OK | 5,360+ (stale) | 2026-07-02 (not re-verified) | Was throttled by `malegislature.gov`; fixed via self-hosted runner as of 2026-07-02. Runner-uptime gaps caused 6 missed nights in the following week — needs monitoring, not just a one-time fix |
| Tennessee | tn | ✅ OK | 9,112 (stale) | 2026-07-02 (not re-verified) | Fixed via self-hosted runner as of 2026-07-02, out of session until 2027 |
| Texas | tx | ✅ OK | 2,019+/592+/692+ (stale) | 2026-07-02 (not re-verified) | Fixed via self-hosted runner as of 2026-07-02, out of session |
| Alabama | al | ✅ OK | 1,507 (stale) | 2026-07-02 (not re-verified) | |
| California | ca | ✅ OK | ~5,013 (stale) | 2026-07-02 (not re-verified) | |
| Colorado | co | ✅ OK | 35/714 (stale) | 2026-07-02 (not re-verified) | |
| District of Columbia | dc | ✅ OK | 1,659 (stale) | 2026-07-02 (not re-verified) | |
| Delaware | de | ✅ OK | 1,294 (stale) | 2026-07-02 (not re-verified) | |
| Georgia | ga | ✅ OK | 5,480+ (stale) | 2026-07-02 (not re-verified) | |
| Iowa | ia | ✅ OK | 3,744 (stale) | 2026-07-02 (not re-verified) | |
| Kansas | ks | ✅ OK | 1,483 (stale) | 2026-07-02 (not re-verified) | |
| Kentucky | ky | ✅ OK | 1,441/74 (stale) | 2026-07-02 (not re-verified) | |
| Maine | me | ✅ OK | 2,451+ (stale) | 2026-07-02 (not re-verified) | |
| Minnesota | mn | ✅ OK | 9,640+ (stale) | 2026-07-02 (not re-verified) | |
| Missouri | mo | ✅ OK | 15+/3,206+ (stale) | 2026-07-02 (not re-verified) | |
| Mississippi | ms | ✅ OK | 106/2,991 (stale) | 2026-07-02 (not re-verified) | |
| Montana | mt | ✅ OK | 4,495 (stale) | 2026-07-02 (not re-verified) | No version links; intermittent timeouts, self-recovers |
| North Dakota | nd | ✅ OK | 1,101 (stale) | 2026-07-02 (not re-verified) | |
| New Jersey | nj | ✅ OK | 11,132+ (stale) | 2026-07-02 (not re-verified) | |
| Oklahoma | ok | ✅ OK | 3,257+ (stale) | 2026-07-02 (not re-verified) | |
| Oregon | or | ✅ OK | 3/264 (stale) | 2026-07-02 (not re-verified) | |
| Puerto Rico | pr | ✅ OK | 3,485+ (stale) | 2026-07-02 (not re-verified) | Word doc format only |
| Rhode Island | ri | ✅ OK | 2,595+/1,076+ (stale) | 2026-07-02 (not re-verified) | |
| South Dakota | sd | ✅ OK | 2/666 (stale) | 2026-07-02 (not re-verified) | |
| Washington | wa | ✅ OK | 3,364+ (stale) | 2026-07-02 (not re-verified) | No version links |
| Wisconsin | wi | ⚠️ Intermittent | 1,624/2 (stale) | 2026-07-02 (not re-verified) | |

---

## Reference

### Session Pause Automation

**Disabled as of 2026-07-14** (`gh workflow disable`, `chihacknight/govbot` repo). It flips
states between `openstates-scrape` and `openstates-scrape-paused` based on the OpenStates
API's session dates, which have proven repeatedly inaccurate — part of why IL, WV, NC, VA,
and others ended up incorrectly paused (which also silently strips the nightly schedule
trigger — the only difference between the two templates). Left enabled, it would have
re-paused the states just fixed before their first nightly run. Re-enable only once its
accuracy problem is actually fixed, or once the project has a better way to manage the
paused/active split. See `check-sessions.py`.

### Failure Categories

**A — Out of Session** — scraper finds no data, legislature not meeting. Soft failures — `action.yml` treats a non-zero exit code as a warning when fallback data is available.

**B — Government Site Structure Changed** — source website changed its HTML/API; OpenStates scraper broken until updated upstream.

**C — OCD Validation Failures** — scraper runs and fetches data, but bill records fail internal Open Civic Data schema validation.

**D — Connectivity Issues** — network timeouts / connection refused.

**E — Workflows Disabled / No Recent Runs**

**F — Active Scraper Blocking (IP-based)** — GitHub-hosted (Azure) runner IPs get blocked or served degraded content by the state site. Self-hosted runner (or the tinyproxy alternative, proven working 2026-07-14 for WV) is the fix. **Don't assume this category without verifying** — several states that looked like this (NC, notably) turned out to just have a missing `runner: self-hosted` config, not an actual block.

**G — Config Gap** — new category added 2026-07-14. State was simply never switched to `runner: self-hosted`, or was stuck on the `-paused` template with no schedule trigger. Looks identical to category F from a "bill count didn't grow" perspective — the only way to tell them apart is to actually try a self-hosted run and see if it works.

### Open TODOs — Node.js 20 Deprecation

All action runs show deprecation warnings. Not breaking yet — GitHub is forcing Node 24 as a shim — but will fail when the shim is removed.

| Action | Current | Target |
|--------|---------|--------|
| `actions/checkout` | `@v4` (node20) | `@v7` (node24) |
| `actions/setup-python` | `@v5` (node20) | `@v6` (node24) |
| `actions/cache` | `@v4` (node20) | `@v6` (node24) |
| `actions/upload-artifact` | `@v4` (node20) | `@v7` (node24) |
| `softprops/action-gh-release` | `@v2` (node20) | `@v3` (node24) |
| `andelf/nightly-release` | `@v1` (node16) | ❌ no newer release — needs replacement |

Files to update: `actions/scrape/action.yml`, `actions/format/action.yml`, `actions/extract/action.yml`, `actions/govbot/action.yml`, `actions/pipeline-manager/templates/` (then re-run `apply.py --all-states`).
