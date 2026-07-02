# Scrape Action — Error Tracking

Track the status of the scrape action across all 57 jurisdictions.

**Statuses:** `✅ OK` | `❌ Broken` | `⚠️ Intermittent` | `⏸️ Unknown`

Last updated: 2026-06-30

## Session Pause Automation

Out-of-session states are now automatically paused via `check-sessions.py` (`.github/workflows/check-sessions.yml`). States where the scraper returns no data because the legislature is not in session will have their workflow flipped to `openstates-scrape-paused` (dispatch-only). This runs daily and reconciles all repos every Sunday.

## Summary of Failures

### A — Out of Session (scraper finds no data, legislature not meeting)
These are soft failures — `action.yml` treats a non-zero exit code as a warning when fallback data is available (merged in PR #42). Out-of-session states are automatically paused by the session-check automation above.

### F — Active Scraper Blocking (state is deliberately preventing automated access to public data)
`tx` — **Resolved.** Texas blocks GitHub Actions IP ranges at the firewall level. Fixed by routing all TX scrapes through a self-hosted runner on Tamara's laptop (`~/actions-runner/`). See `tx-backfill-runbook.md` for backfill procedures.

### B — Government Site Structure Changed (need OpenStates scraper fixes)
The source website changed its HTML/API; the OpenStates scraper is broken until updated upstream.
`az`, `hi`, `la`, `nj`, `tn`

### C — OCD Validation Failures (data fails Open Civic Data schema validation)
Scraper runs and fetches data, but bill records fail internal validation.
`dc`, `mp`

### D — Connectivity Issues (network timeouts / connection refused)
`nh` (timeout), `wi` (intermittent timeout)

### E — Workflows Disabled / No Recent Runs
`va`, `vi` — last run 2026-04-01; workflows appear disabled

---

## Open TODOs

### Node.js 20 Deprecation — Action Version Bumps
All action runs show deprecation warnings. Not breaking yet — GitHub is forcing Node 24 as a shim — but will fail when the shim is removed.

Required bumps (confirmed by checking `runs.using` in each action's `action.yml`):

| Action | Current | Target |
|--------|---------|--------|
| `actions/checkout` | `@v4` (node20) | `@v7` (node24) |
| `actions/setup-python` | `@v5` (node20) | `@v6` (node24) |
| `actions/cache` | `@v4` (node20) | `@v6` (node24) |
| `actions/upload-artifact` | `@v4` (node20) | `@v7` (node24) |
| `softprops/action-gh-release` | `@v2` (node20) | `@v3` (node24) |
| `andelf/nightly-release` | `@v1` (node16) | ❌ no newer release — needs replacement |

Files to update: `actions/scrape/action.yml`, `actions/format/action.yml`, `actions/extract/action.yml`, `actions/govbot/action.yml`, `actions/pipeline-manager/templates/` (then re-run `apply.py --all-states`).

---

## Full Status Table

| Jurisdiction | Code | Status | Machine Readable? | Error | Notes |
|---|---|---|:-:|---|---|
| Alaska | ak | ✅ OK | ✅ | | |
| Alabama | al | ✅ OK | ❌ | | |
| Arkansas | ar | ✅ OK | ❌ | | |
| Arizona | az | ❌ Broken | ❌ | `AssertionError: Session ID not in bill list` | Cookie not persisted through `setsession.php` POST — confirmed from home network, not a WAF issue. PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) open awaiting review. |
| California | ca | ✅ OK | ✅ | | |
| Colorado | co | ✅ OK | ❌ | | |
| Connecticut | ct | ✅ OK | ❌ | | Azure IPs blocked by `ftp.cga.ct.gov` — confirmed self-hosted runner fix 2026-07-02: 1,283 bills in 17 min. Moved to self-hosted runner. Issue [#1384](https://github.com/openstates/issues/issues/1384) open for awareness. |
| District of Columbia | dc | ✅ OK | ❌ | | PRs #5706 and #5711 merged — mimetype=None and PDF query string issues both fixed. |
| Delaware | de | ✅ OK | ✅ | | |
| Florida | fl | ✅ OK | ❌ | | |
| Georgia | ga | ✅ OK | ❌ | | |
| Guam | gu | ✅ OK | ❌ | | |
| Hawaii | hi | ✅ OK | ❌ | | Cloudflare WAF blocks GitHub IPs. Self-hosted runner confirmed working 2026-07-02: 6,640 bills + 8,895 vote events in 31 min. |
| Iowa | ia | ✅ OK | ❌ | | |
| Idaho | id | ✅ OK | ❌ | | |
| Illinois | il | ✅ OK | ✅ | | |
| Indiana | in | ✅ OK | ❌ | | Requires `INDIANA_API_KEY` secret (confirmed present). |
| Kansas | ks | ✅ OK | ✅ | | |
| Kentucky | ky | ✅ OK | ❌ | | |
| Louisiana | la | ⚠️ Intermittent | ❌ | ~7 of 525 bills returned | Action table fix merged (PR [#5716](https://github.com/openstates/openstates-scrapers/pull/5716)) but bill search still only returns ~7 results. Issue [#1379](https://github.com/openstates/issues/issues/1379) open — awaiting maintainer response. |
| Massachusetts | ma | ✅ OK | ❌ | | |
| Maryland | md | ✅ OK | ❌ | | |
| Maine | me | ✅ OK | ❌ | | |
| Michigan | mi | ✅ OK | ✅ | | |
| Minnesota | mn | ✅ OK | ✅ | | |
| Missouri | mo | ✅ OK | ❌ | | |
| Northern Mariana Islands | mp | ❌ Broken | ❌ | `ScrapeValueError: validation of Bill failed` | Category C — OCD validation error on bill data |
| Mississippi | ms | ✅ OK | ✅ | | |
| Montana | mt | ✅ OK | ❌ | | No version links in scraped bills |
| North Carolina | nc | ✅ OK | ❌ | | |
| North Dakota | nd | ✅ OK | ❌ | | |
| Nebraska | ne | ✅ OK | ❌ | | |
| New Hampshire | nh | ❌ Broken | ❌ | `H3_RATE_LIMITED` (was `ConnectTimeoutError`) | Category D — Session ended 2026-03-14; site returning rate limit errors. Timeout observed previously; may rotate between the two. |
| New Jersey | nj | ✅ OK | ✅ | | PR #5707 merged — vote bill_id guard added. |
| New Mexico | nm | ❌ Broken | ❌ | `ValueError: ftp://www.nmlegis.gov/other/ contains no matching files` | Category A — NM FTP has no files; likely out of session |
| Nevada | nv | ✅ OK | ❌ | | |
| New York | ny | ✅ OK | ✅ | | Requires `NEW_YORK_API_KEY` secret (confirmed present). |
| Ohio | oh | ✅ OK | ✅ | | |
| Oklahoma | ok | ✅ OK | ❌ | | |
| Oregon | or | ✅ OK | ❌ | | |
| Pennsylvania | pa | ✅ OK | ✅ | | |
| Puerto Rico | pr | ✅ OK | ✅ | | Word doc format only |
| Rhode Island | ri | ✅ OK | ❌ | | |
| South Carolina | sc | ✅ OK | ✅ | | |
| South Dakota | sd | ✅ OK | ✅ | | |
| Tennessee | tn | ✅ OK | ❌ | | Self-hosted runner backfill complete 2026-07-02. All bills captured. Out of session until 2027. |
| Texas | tx | ✅ OK | ✅ | | Self-hosted runner on Tamara's laptop bypasses IP block. Backfill complete (89R, 891, 892). See `tx-backfill-runbook.md`. |
| USA | usa | ✅ OK | ✅ | | XML format available |
| Utah | ut | ✅ OK | ✅ | | XML format available |
| Virginia | va | ❌ Broken | ❌ | `KeyError: ' '` in csv_bills | PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) ✅ merged. govbot PR [#58](https://github.com/chihacknight/govbot/pull/58) ✅ merged. Issue [#1385](https://github.com/openstates/issues/issues/1385) filed + PR [#5723](https://github.com/openstates/openstates-scrapers/pull/5723) open (chamber KeyError fix). Needs verification run after Docker rebuild. |
| Virgin Islands | vi | ❌ Broken | ❌ | Workflows disabled | Category E — No runs since 2026-04-01; scheduled runs appear disabled |
| Vermont | vt | ✅ OK | ❌ | | |
| Washington | wa | ✅ OK | ❌ | | No version links in scraped bills |
| Wisconsin | wi | ⚠️ Intermittent | ✅ | `TimeoutError: docs.legis.wisconsin.gov timed out` | Category D — Failed 2026-06-26 only; OK prior 4 days |
| West Virginia | wv | ❌ Broken | ✅ | 39 bills vs expected 2975 | Only House Joint Resolutions returned, regular HB/SB bills missing. PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) open — maintainer disputes (gets 2975 locally). Sent scrape log 2026-07-02, awaiting reply. |
| Wyoming | wy | ✅ OK | ❌ | | |
