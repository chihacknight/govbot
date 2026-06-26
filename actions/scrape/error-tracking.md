# Scrape Action — Error Tracking

Track the status of the scrape action across all 57 jurisdictions.

**Statuses:** `✅ OK` | `❌ Broken` | `⚠️ Intermittent` | `⏸️ Unknown`

Last updated: 2026-06-26

## Summary of Failures

### A — Out of Session (scraper finds no data, legislature not meeting)
These should not be hard failures. `ct`, `nm`

**Fix in progress:** Branch `fix/scrape-no-new-data` updates `action.yml` to treat a non-zero
scraper exit code as a soft failure when fallback data is available. The workflow yml files in
`ct-legislation` and `nm-legislation` repos have been temporarily pointed
to `chihacknight/govbot/actions/scrape@fix/scrape-no-new-data` for testing.

⚠️ **TODO on merge to main:** Update those 2 state repos back to `@main`:
- `govbot-openstates-scrapers/ct-legislation` — `.github/workflows/*.yml`
- `govbot-openstates-scrapers/nm-legislation` — `.github/workflows/*.yml`

### F — Active Scraper Blocking (state is deliberately preventing automated access to public data)
`tx`

Texas returns `ConnectionRefusedError [Errno 111]` — the server is actively refusing TCP
connections from GitHub Actions IP ranges before any HTTP request is even made. This is not
an out-of-session issue: the Texas legislature actively meets and produces data, but access
is being blocked. This is a transparency problem and a priority to fix.

Unlike a timeout or a site being down, connection refused is an intentional firewall-level
decision. The `fix/scrape-no-new-data` branch will prevent daily hard failures for TX by
falling back to prior data, but that is a stopgap — TX data will go stale without a real fix.

**Options to investigate:**
- Route TX scrapes through a non-GitHub-Actions IP (self-hosted runner, proxy, or VPS)
- Check if OpenStates has an alternative data source for TX that doesn't hit capitol.texas.gov directly
- Monitor whether other civic tech orgs (e.g., Plural Policy, LegiScan) have TX data available

⚠️ **TODO on merge to main:** Update tx-legislation back to `@main`:
- `govbot-openstates-scrapers/tx-legislation` — `.github/workflows/*.yml`

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

## Full Status Table

| Jurisdiction | Code | Status | Error | Notes |
|---|---|---|---|---|
| Alaska | ak | ✅ OK | | |
| Alabama | al | ✅ OK | | |
| Arkansas | ar | ✅ OK | | |
| Arizona | az | ❌ Broken | `AssertionError: Session ID not in bill list` | Category B — OpenStates scraper bug; session ID config mismatch |
| California | ca | ✅ OK | | |
| Colorado | co | ✅ OK | | |
| Connecticut | ct | ❌ Broken | `ScrapeError: no objects returned from CTBillScraper scrape` | Category A — Legislature likely out of session |
| District of Columbia | dc | ❌ Broken | `ScrapeValueError: validation of Bill failed` | Category C — OCD validation error on bill data. Requires `DC_API_KEY` secret (confirmed present). |
| Delaware | de | ✅ OK | | |
| Florida | fl | ✅ OK | | |
| Georgia | ga | ✅ OK | | |
| Guam | gu | ✅ OK | | |
| Hawaii | hi | ❌ Broken | `KeyError: 'Report Title'` | Category B — Hawaii site changed structure; scraper expects field that no longer exists |
| Iowa | ia | ✅ OK | | |
| Idaho | id | ✅ OK | | |
| Illinois | il | ✅ OK | | |
| Indiana | in | ✅ OK | | Requires `INDIANA_API_KEY` secret (confirmed present). |
| Kansas | ks | ✅ OK | | |
| Kentucky | ky | ✅ OK | | |
| Louisiana | la | ❌ Broken | `ValueError: not enough values to unpack (expected 5, got 4)` | Category B — Louisiana site changed data format |
| Massachusetts | ma | ✅ OK | | |
| Maryland | md | ✅ OK | | |
| Maine | me | ✅ OK | | |
| Michigan | mi | ✅ OK | | |
| Minnesota | mn | ✅ OK | | |
| Missouri | mo | ✅ OK | | |
| Northern Mariana Islands | mp | ❌ Broken | `ScrapeValueError: validation of Bill failed` | Category C — OCD validation error on bill data |
| Mississippi | ms | ✅ OK | | |
| Montana | mt | ✅ OK | | |
| North Carolina | nc | ✅ OK | | |
| North Dakota | nd | ✅ OK | | |
| Nebraska | ne | ✅ OK | | |
| New Hampshire | nh | ❌ Broken | `ConnectTimeoutError: Connection to gc.nh.gov timed out` | Category D — Government site timing out consistently |
| New Jersey | nj | ❌ Broken | `KeyError: 'A4029'` | Category B — Bill lookup dict missing expected key; site format changed |
| New Mexico | nm | ❌ Broken | `ValueError: ftp://www.nmlegis.gov/other/ contains no matching files` | Category A — NM FTP has no files; likely out of session |
| Nevada | nv | ✅ OK | | |
| New York | ny | ✅ OK | | Requires `NEW_YORK_API_KEY` secret (confirmed present). |
| Ohio | oh | ✅ OK | | |
| Oklahoma | ok | ✅ OK | | |
| Oregon | or | ✅ OK | | |
| Pennsylvania | pa | ✅ OK | | |
| Puerto Rico | pr | ✅ OK | | |
| Rhode Island | ri | ✅ OK | | |
| South Carolina | sc | ✅ OK | | |
| South Dakota | sd | ✅ OK | | |
| Tennessee | tn | ❌ Broken | `IndexError: list index out of range` | Category B — TN site structure changed; list parsing broke |
| Texas | tx | ❌ Broken | `ConnectionError: capitol.texas.gov connection refused` | Category A — TX has biennial legislature; likely out of session |
| USA | usa | ✅ OK | | |
| Utah | ut | ✅ OK | | |
| Virginia | va | ❌ Broken | Workflows disabled | Category E — No runs since 2026-04-01; scheduled runs appear disabled. Requires `USER_AGENT` secret (confirmed present). Uses `csv_bills` scraper, not standard bills scraper. |
| Virgin Islands | vi | ❌ Broken | Workflows disabled | Category E — No runs since 2026-04-01; scheduled runs appear disabled |
| Vermont | vt | ✅ OK | | |
| Washington | wa | ✅ OK | | |
| Wisconsin | wi | ⚠️ Intermittent | `TimeoutError: docs.legis.wisconsin.gov timed out` | Category D — Failed 2026-06-26 only; OK prior 4 days |
| West Virginia | wv | ✅ OK | | |
| Wyoming | wy | ✅ OK | | |
