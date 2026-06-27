# Scrape Action — Error Tracking

Track the status of the scrape action across all 57 jurisdictions.

**Statuses:** `✅ OK` | `❌ Broken` | `⚠️ Intermittent` | `⏸️ Unknown`

Last updated: 2026-06-27

## Summary of Failures

### A — Out of Session (scraper finds no data, legislature not meeting)
These should not be hard failures. `ct`, `nm`

**Fix in progress:** Branch `fix/scrape-no-new-data` updates `action.yml` to treat a non-zero
scraper exit code as a soft failure when fallback data is available. The workflow yml files in
`ct-legislation` and `nm-legislation` repos have been temporarily pointed
to `chihacknight/govbot/actions/scrape@fix/scrape-no-new-data` for testing.

✅ All test repos updated back to `@main` on 2026-06-27.

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

✅ tx-legislation updated back to `@main` on 2026-06-27.

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

| Jurisdiction | Code | Status | Error | Notes |
|---|---|---|---|---|
| Alaska | ak | ✅ OK | | |
| Alabama | al | ✅ OK | | |
| Arkansas | ar | ✅ OK | | |
| Arizona | az | ❌ Broken | `S3_SESSION_CONFIG` | Category B — Session ended 2026-04-17; scraper asserting on stale session ID. Will need re-check when 2027 session opens. |
| California | ca | ✅ OK | | |
| Colorado | co | ✅ OK | | |
| Connecticut | ct | ❌ Broken | `ScrapeError: no objects returned from CTBillScraper scrape` | Category A — Legislature likely out of session |
| District of Columbia | dc | ❌ Broken | `S6_VALIDATION` (or `H3_RATE_LIMITED` intermittently) | Category C — Non-PDF attachments in `leg_details["actions"]` set `mimetype=None`, failing OCD schema validation on `media_type`. Scraper crashes mid-run; bills after the failing record are dropped. DC_API_KEY is working fine. PR submitted to openstates/openstates-scrapers: fix/dc-media-type-null. 2026-06-27 run showed H3_RATE_LIMITED — may have gotten further before dying; validation error is the root cause. |
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
| New Hampshire | nh | ❌ Broken | `H3_RATE_LIMITED` (was `ConnectTimeoutError`) | Category D — Session ended 2026-03-14; site returning rate limit errors. Timeout observed previously; may rotate between the two. |
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
| Tennessee | tn | ❌ Broken | `H4_SERVER_DOWN` (was `IndexError`) | Category B — Session ended 2026-04-15; server returning 503. IndexError (site structure bug) is the real issue to fix when 2027 session opens. |
| Texas | tx | ❌ Broken | `ConnectionError: capitol.texas.gov connection refused` | Category F — Active IP block; TX rotates between connection refused (N1) and 503 (H4) depending on the run |
| USA | usa | ✅ OK | | |
| Utah | ut | ✅ OK | | |
| Virginia | va | ❌ Broken | Workflows disabled | Category E — No runs since 2026-04-01; scheduled runs appear disabled. Requires `USER_AGENT` secret (confirmed present). Uses `csv_bills` scraper, not standard bills scraper. |
| Virgin Islands | vi | ❌ Broken | Workflows disabled | Category E — No runs since 2026-04-01; scheduled runs appear disabled |
| Vermont | vt | ✅ OK | | |
| Washington | wa | ✅ OK | | |
| Wisconsin | wi | ⚠️ Intermittent | `TimeoutError: docs.legis.wisconsin.gov timed out` | Category D — Failed 2026-06-26 only; OK prior 4 days |
| West Virginia | wv | ✅ OK | | |
| Wyoming | wy | ✅ OK | | |
