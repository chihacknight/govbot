# Scrape Action — Error Tracking

Track the status of the scrape action across all 57 jurisdictions.

**Statuses:** `✅ OK` | `❌ Broken` | `⚠️ Intermittent` | `⏸️ Unknown`

Last updated: 2026-07-02

## Full Status Table

| Jurisdiction | Code | Status | Machine Readable? | Error | Bill Counts | Notes |
|---|---|---|:-:|---|---|---|
| Alaska | ak | ✅ OK | ✅ | | 34th Legislature (2025-2026): 514 | |
| Alabama | al | ✅ OK | ❌ | | 2026 Regular Session: 1,507 | |
| Arkansas | ar | ⚠️ Intermittent | ❌ | `ARBillScraper raised EmptyScrape` | 2025 Regular Session: 1,928+ | DATA GAP — scraper filters FTP rows by active session ID (`2026S1`) but `ChamberActions.txt` only contains `2025R` rows. Two entire 2026 sessions missing: 95th Special (ended May 2026) and 95th Fiscal (ended May 2026). Session ID mismatch between OpenStates and AR FTP. 1,928+ bills retained from prior run. |
| Arizona | az | ❌ Broken | ❌ | `AssertionError: Session ID not in bill list` |  | Cookie not persisted through `setsession.php` POST — confirmed from home network, not a WAF issue. PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) open awaiting review. |
| California | ca | ✅ OK | ✅ | | 2025-2026 Regular Session: 4,989 / 2025-2026, Special Session 1: 24+ | GitHub API tree truncated at 2,077 — actual count 5,013 from scraper logs. Scraper spins up a local MySQL container mid-run. |
| Colorado | co | ✅ OK | ❌ | | 2025 First Extraordinary Session: 35 / 2026 Regular Session: 714 | |
| Connecticut | ct | ✅ OK | ❌ | | 2025 Regular Session: 4,076 | Azure IPs blocked by `ftp.cga.ct.gov` — confirmed self-hosted runner fix 2026-07-02: 1,283 bills in 17 min. Moved to self-hosted runner. Issue [#1384](https://github.com/openstates/issues/issues/1384) open for awareness. |
| District of Columbia | dc | ✅ OK | ❌ | | 26th Council Period (2025-2026): 1,659 | PRs #5706 and #5711 merged — mimetype=None and PDF query string issues both fixed. |
| Delaware | de | ✅ OK | ✅ | | 153rd General Assembly (2025-2026): 1,294 | SSL cert verification disabled for `legis.delaware.gov` (every request fires `InsecureRequestWarning`). Intermittent fetch failures: HB 479 and HB 481 failed in 2026-07-02 run (WARNING, not fatal — prior run data retained in repo). |
| Florida | fl | ❌ Broken | ❌ | `spatula.pages.RejectedResponse: Response was rejected (4x)` | 2026 Regular Session: 1,916+ | Site returns HTTP 200 with bot-detection page; spatula `accept_response` rejects it. Fails even from self-hosted runner on home IP. Only 22 files scraped this run — 1,916+ in repo retained from prior run. Also: `tar: Option --mode=755 is not supported` on macOS self-hosted runner (BSD tar vs GNU tar incompatibility in action.yml). |
| Georgia | ga | ✅ OK | ❌ | | 2025-2026 Regular Session: 5,480+ | |
| Guam | gu | ✅ OK | ❌ | | 38th Guam Legislature: 277 | Scraper reports 831 bills but repo has 277 — each bill is saved ~3x per run with different UUIDs. Format action deduplicates correctly; no data loss. Scraper bug causes ~3x unnecessary HTTP requests. Worth filing upstream. |
| Hawaii | hi | ✅ OK | ❌ | | 2025 Regular Session: 3,067+ | Cloudflare WAF blocks GitHub IPs. Self-hosted runner confirmed working 2026-07-02: 6,640 bills + 8,895 vote events in 31 min. |
| Iowa | ia | ✅ OK | ❌ | | 2025-2026 Regular Session: 3,744 | |
| Idaho | id | ✅ OK | ❌ | | 68th Leg., 1st Regular Session (2025): 790 / 68th Leg., 2nd Regular Session (2026): 1 | DATA GAP — scraper hits `minidata/` endpoint but only returns 1 bill (HCR 020) for the completed 2026 session. Same pattern as UT. `minidata/` likely only surfaces active/pending bills. |
| Illinois | il | ✅ OK | ✅ | | 104th Regular Session: 2,945+ | |
| Indiana | in | ✅ OK | ❌ | | 2026 Regular Session: 40 | Requires `INDIANA_API_KEY` secret (confirmed present). |
| Kansas | ks | ✅ OK | ✅ | | 2025-2026 Regular Session: 1,483 | |
| Kentucky | ky | ✅ OK | ❌ | | 2025 Regular Session: 1,441 / 2026 Regular Session: 74 | |
| Louisiana | la | ⚠️ Intermittent | ❌ | ~7 of 525 bills returned | 2025 First Extraordinary Session: 12 / 2026 Regular Session: 7 | Action table fix merged (PR [#5716](https://github.com/openstates/openstates-scrapers/pull/5716)) but bill search still only returns ~7 results. Issue [#1379](https://github.com/openstates/issues/issues/1379) open — awaiting maintainer response. |
| Massachusetts | ma | ✅ OK | ❌ | | 194th Legislature (2025-2026): 5,360+ | |
| Maryland | md | ⚠️ Intermittent | ❌ | | 2025 Regular Session: 2,617+ / 2026 Regular Session: 531 | DATA GAP — 2026 session has only 531 bills (HB0001–HB0298, SB0001–SB0231, HJ0001–HJ0002). MD holds full 90-day sessions annually; 2025 had 2,617+. Scraper runs in 7s suggesting it reads from a list endpoint returning only a subset (likely passed/active bills only). Same pattern as UT/ID/WY. |
| Maine | me | ✅ OK | ❌ | | 132nd Legislature (2025-2026): 2,451+ | |
| Michigan | mi | ✅ OK | ✅ | | 2025-2026 Regular Session: 2,360 | |
| Minnesota | mn | ✅ OK | ✅ | | 2025-2026 Regular Session: 9,640+ | |
| Missouri | mo | ✅ OK | ❌ | | 2025 2nd Extraordinary Session: 15+ / 2026 Regular Session: 3,206+ | |
| Northern Mariana Islands | mp | ❌ Broken | ❌ | `ScrapeValueError: validation of Bill failed` | 24th Commonwealth Legislature: 302 | **HCommRes 24-6** (`legID=20113`) has empty title on CNMI website — OCD requires `minLength: 1`. Crashes same bill every run (not rate limiting). Fix: add title fallback in MP scraper. All bills after this one in iteration order are also missing. |
| Mississippi | ms | ✅ OK | ✅ | | 2025 First Extraordinary Session: 106 / 2026 Regular Session: 2,991 | |
| Montana | mt | ✅ OK | ❌ | | 2025 Regular Session: 4,495 | No version links in scraped bills. 8 intermittent `TimeoutError` (SSL handshake to `api.legmt.gov`) per run — scraper retries and completes. Bills re-saved with new UUIDs each run (same pattern as GU) — format action deduplicates, no data loss. GitHub API tree truncated at 1,481 (actual: 4,495). |
| North Carolina | nc | ✅ OK | ❌ | | 2025-2026 Session: 1,794 | |
| North Dakota | nd | ✅ OK | ❌ | | 69th Legislative Assembly (2025-26): 1,101 | |
| Nebraska | ne | ✅ OK | ❌ | | 109th Legislature (2025-2026): 1,037 | |
| New Hampshire | nh | ❌ Broken | ❌ | `ConnectTimeoutError` | 2025 Regular Session: 1,072+ / 2026 Regular Session: 1,393+ | Site bans scraping 6am–9pm ET. Schedule now runs at 2am ET — borderline. Investigating. |
| New Jersey | nj | ✅ OK | ✅ | | 2024-2025 Regular Session: 11,132+ | PR #5707 merged — vote bill_id guard added. |
| New Mexico | nm | ❌ Broken | ❌ | `ValueError: ftp://www.nmlegis.gov/other/ contains no matching files` | 2025 Second Special Session: 2 | FTP directory listing format mismatch in `_init_mdb`. Issue [#1381](https://github.com/openstates/issues/issues/1381) — awaiting maintainer response. |
| Nevada | nv | ✅ OK | ❌ | | 36th (2026) Special Session: 27 | Scraper healthy. Repo created 2025-11-26 — missed the 83rd Regular Session (Feb–Jun 2025, ~1,000+ bills). Only the 36th Special Session (Nov 2025) is in the repo. Backfill with `--session 83` to recover. NV meets biennially (odd years only); no regular session until 2027. |
| New York | ny | ✅ OK | ✅ | | 2025 Regular Session: 9,584+ | Requires `NEW_YORK_API_KEY` secret (confirmed present). |
| Ohio | oh | ✅ OK | ✅ | | 136th Legislature (2025-2026): 1,538 | |
| Oklahoma | ok | ✅ OK | ❌ | | 2025 Regular Session: 3,257+ | |
| Oregon | or | ✅ OK | ❌ | | 2025 Special Session: 3 / 2026 Regular Session: 264 | |
| Pennsylvania | pa | ✅ OK | ✅ | | 2025-2026 Regular Session: 3,578 | |
| Puerto Rico | pr | ✅ OK | ✅ | | 2025-2028 Session: 3,485+ | Word doc format only |
| Rhode Island | ri | ✅ OK | ❌ | | 2025 Regular Session: 2,595+ / 2026 Regular Session: 1,076+ | |
| South Carolina | sc | ✅ OK | ✅ | | 2025-2026 Regular Session: 3,051 | GitHub API tree truncated at 2,244 — actual count 3,051 from scraper logs. |
| South Dakota | sd | ✅ OK | ✅ | | 2025 First Special Session: 2 / 2026 Regular Session: 666 | |
| Tennessee | tn | ✅ OK | ❌ | | 114th Regular Session (2025-2026): 9,112 | Self-hosted runner backfill complete 2026-07-02. All bills captured. Out of session until 2027. GitHub API tree truncated at 2,207 — actual count 9,112. macOS `tar --mode=755` fails on self-hosted runner; falls back to previous release tarball (data still committed). |
| Texas | tx | ✅ OK | ✅ | | 89th Leg. (2025): 2,019+ / 89th Leg. 1st Called (2025): 592+ / 89th Leg. 2nd Called (2025): 692+ | Self-hosted runner on Tamara's laptop bypasses IP block. Backfill complete (89R, 891, 892). See `tx-backfill-runbook.md`. |
| USA | usa | ✅ OK | ✅ | | 119th Congress: 8,250+ | XML format available |
| Utah | ut | ✅ OK | ✅ | | 2025 First Special Session: 18 / 2025 Second Special Session: 5 / 2026 General Session: 3 | XML format available |
| Virginia | va | ❌ Broken | ❌ | `KeyError: ' '` in csv_bills |  | PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) ✅ merged. govbot PR [#58](https://github.com/chihacknight/govbot/pull/58) ✅ merged. Issue [#1385](https://github.com/openstates/issues/issues/1385) filed + PR [#5723](https://github.com/openstates/openstates-scrapers/pull/5723) open (chamber KeyError fix). Needs verification run after Docker rebuild. |
| Virgin Islands | vi | ❌ Broken | ❌ | Workflows disabled | 2025-2026 Regular Session: 148 | No runs since 2026-04-01; workflows appear disabled |
| Vermont | vt | ✅ OK | ❌ | | 2025-2026 Regular Session: 898 | |
| Washington | wa | ✅ OK | ❌ | | 2025-2026 Regular Session: 3,364+ | No version links in scraped bills |
| Wisconsin | wi | ⚠️ Intermittent | ✅ | `TimeoutError: docs.legis.wisconsin.gov timed out` | 2025-2026 Regular Session: 1,624 / May 2026 Special Session: 2 | Failed 2026-06-26 only; OK prior 4 days |
| West Virginia | wv | ❌ Broken | ✅ | 39 bills vs expected 2975 | 2025 Regular Session: 2,709+ | Only House Joint Resolutions returned, regular HB/SB bills missing. PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) open — maintainer disputes (gets 2975 locally). Sent scrape log 2026-07-02, awaiting reply. |
| Wyoming | wy | ✅ OK | ❌ | | 2025 Regular Session: 556 / 2026 Regular Session: 23 | |

---

## Reference

### Session Pause Automation

Out-of-session states are now automatically paused via `check-sessions.py` (`.github/workflows/check-sessions.yml`). States where the scraper returns no data because the legislature is not in session will have their workflow flipped to `openstates-scrape-paused` (dispatch-only). This runs daily and reconciles all repos every Sunday.

### Failure Categories

**A — Out of Session** — scraper finds no data, legislature not meeting. Soft failures — `action.yml` treats a non-zero exit code as a warning when fallback data is available. Out-of-session states are automatically paused by the session-check automation above.

**B — Government Site Structure Changed** — source website changed its HTML/API; OpenStates scraper broken until updated upstream.

**C — OCD Validation Failures** — scraper runs and fetches data, but bill records fail internal Open Civic Data schema validation.

**D — Connectivity Issues** — network timeouts / connection refused.

**E — Workflows Disabled / No Recent Runs**

**F — Active Scraper Blocking** — state is deliberately preventing automated access to public data. Self-hosted runner is the workaround.

### Open TODOs — Node.js 20 Deprecation

All action runs show deprecation warnings. Not breaking yet — GitHub is forcing Node 24 as a shim — but will fail when the shim is removed.

| Action | Current | Target |
|--------|---------|-------- |---|
| `actions/checkout` | `@v4` (node20) | `@v7` (node24) |
| `actions/setup-python` | `@v5` (node20) | `@v6` (node24) |
| `actions/cache` | `@v4` (node20) | `@v6` (node24) |
| `actions/upload-artifact` | `@v4` (node20) | `@v7` (node24) |
| `softprops/action-gh-release` | `@v2` (node20) | `@v3` (node24) |
| `andelf/nightly-release` | `@v1` (node16) | ❌ no newer release — needs replacement |

Files to update: `actions/scrape/action.yml`, `actions/format/action.yml`, `actions/extract/action.yml`, `actions/govbot/action.yml`, `actions/pipeline-manager/templates/` (then re-run `apply.py --all-states`).
