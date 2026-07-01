# Scraper Health Log

Tracks the status of all 56 `govbot-openstates-scrapers` repos. Updated manually after health checks.

---

## 2026-07-01 Health Check

Run IDs from the daily 8 AM UTC scrape.

> **Note (2026-07-01):** All 56 repos had been deployed with `windy-civi/toolkit/actions/scrape@main` (wrong action reference) by a prior apply run. Fixed in both pipeline-manager templates, snapshots regenerated, and re-applied to all repos via apply-templates.

### Hard Failures

| State | Status | Issue | Notes |
|-------|--------|-------|-------|
| tx | ❌ failure | Runner connectivity | Self-hosted runner (MacBook) couldn't download action from GitHub at run time — network issue. TX self-hosted runner is required because `capitol.texas.gov` blocks Azure IPs. |
| va | ❌ failure | Disabled since 2026-04-01 | Last run was 3 months ago. Workflows disabled, cause unknown. |
| vi | ❌ failure | Disabled since 2026-04-01 | Same mystery as VA. VI session is ongoing. |

### Cancelled (Timeout)

| State | Status | Issue | Notes |
|-------|--------|-------|-------|
| fl | ⏸️ cancelled | Ran 4+ hours | Too many bills to complete within GitHub Actions time limit. Recurring issue. |
| ma | ⏸️ cancelled | Ran 4+ hours | Same pattern as FL — large bill count. |

### On Fallback (Scraper Error, Serving Stale Data)

| State | Failure Type | Error | Action |
|-------|-------------|-------|--------|
| la | S5_SITE_STRUCTURE | Crash fixed via PR [#5716](https://github.com/openstates/openstates-scrapers/pull/5716) (merged 2026-07-01). Ran manually after merge — only 7 of 525 bills scraped. Root cause: `r={}1*` search pattern + abbreviation discovery issues. | Issue [#1379](https://github.com/openstates/issues/issues/1379) filed — waiting on OpenStates maintainers |
| ok | S3_SESSION_CONFIG | `CommandError: Session(s) "1998 Regular Session (PROD)" not found` — `(PROD)` suffix not stripped from session list | PR [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) filed; Issue [#1378](https://github.com/openstates/issues/issues/1378) filed |

### Clean (50/56)

All other states ran successfully. Notable counts:

| State | Files | Notes |
|-------|-------|-------|
| ny | 24,937 | |
| ca | 22,680 | |
| il | 15,323 | |
| mt | 13,258 | |
| usa | 11,960 | |
| mn | 9,815 | |
| nj | 8,212 | |
| pa | 6,423 | |
| wa | 5,713 | |
| pr | 5,081 | |
| de | 3,065 | |
| ms | 3,033 | |
| mi | 2,913 | |
| nc | 2,432 | |
| oh | 2,167 | |
| nd | 3,265 | |
| ne | 1,976 | |
| al | 1,511 | |
| ks | 1,487 | |
| sc | 3,947 | |
| ri | 4,132 | |
| ia | 3,748 | |
| me | 3,613 | |
| mo | 4,640 | |
| dc | 2,713 | DC fix (PRs #5706, #5711) confirmed working |
| gu | 833 | |
| vt | 953 | |
| ak | 942 | |
| co | 736 | |
| or | 268 | |
| ga | 460 | |
| md | 535 | |
| wi | 2,701 | |
| wv | 45 | |
| wy | 27 | |
| sd | 45 | |
| ky | 78 | |
| nv | 64 | |
| ut | 28 | |
| mp | 139 | |
| in | 47 | |
| nh | 437 | |
| ar | 4 | Out of session (stale metadata only) |
| az | 4 | Out of session — ended Apr 17 |
| ct | 4 | Out of session |
| hi | 4 | Out of session — ended May 8 |
| id | 5 | Out of session |
| nm | 4 | No 2026 session |
| tn | 37 | Out of session — ended Apr 15 |

---

## Known Ongoing Issues

### FL — Serial Per-Bill Scraping (Out of Session)

FL session ended; one final scrape needed to capture end-of-session data.

Root cause of 6-hour cancellations: the FL scraper fetches each bill individually — BillDetail page, HouseSearchPage, HouseBillPage, then N vote PDFs in a pagination loop ("Votes don't add up; looking for additional ones"). Just one bill (HJR 1F) took ~34 seconds and required 7 separate vote PDF fetches. Across hundreds of bills in two sessions (`2026` and `2026F`), this exhausts the 6-hour GitHub Actions cap. No evidence of IP blocking — `flsenate.gov` and `flhouse.gov` serve Azure IPs without issue, it's just a slow serial design.

**Fix**: Run once from self-hosted runner (removes 6-hour cap). After the data is captured, move FL back to paused.

### MA — Active Throttling by malegislature.gov

MA is actively throttling Azure-originating requests. Response times ramp up progressively within a single run: 36s → 72s → 300s → server errors → connection drop. Run history confirms this: some days complete in 1-2 hours (light throttling), other days cancel after 6 hours (heavy throttling). Two `Server Error` responses visible mid-run on HD3106 and HD3112. The scraper eventually fails and retries from scratch, burning more time.

This is the same underlying pattern as TX (hostile to scraping from cloud IPs), just throttling instead of a hard block. A self-hosted runner on a home network IP bypasses the Azure IP detection.

### VA — Scrape Argument Bug (Fix Pending)
VA session ended Mar 14, 2026. Workflows were disabled since 2026-04-01. Root cause traced to `scrape.sh`: `--session=2025` was placed before the scraper name (`csv_bills`), which OpenStates rejects. Fix (correct arg order + bumped to `--session=2026`) is on `fix/va-vi-scrapers` branch in govbot — **needs PR, merge, and apply-templates run** to push updated `scrape.sh` to va-legislation repo. VA csv_bills also had a hardcoded `session_id = "20251"` ignoring the `--session` argument — fixed in OpenStates PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) (open). Issue [#1377](https://github.com/openstates/issues/issues/1377) filed.

### VI — Server Down
VI is in active session but `billtracking.legvi.org:8082` is returning connection timeouts. This is a server-side outage — no code fix possible until the site comes back online.

### TX — Self-Hosted Runner Dependency
Texas scrapes require Tamara's MacBook (`~/actions-runner/`) to be online. `capitol.texas.gov` actively blocks Azure IP ranges used by GitHub-hosted runners. When the laptop is offline or loses connectivity, TX fails. Runbook: `actions/scrape/tx-backfill-runbook.md`.

---

## OpenStates PRs Filed by Tamara (tamara-builds)

| PR | Description | Status |
|----|-------------|--------|
| [#5706](https://github.com/openstates/openstates-scrapers/pull/5706) | DC mimetype None | ✅ Merged |
| [#5707](https://github.com/openstates/openstates-scrapers/pull/5707) | NJ vote bill_id guard | ✅ Merged |
| [#5711](https://github.com/openstates/openstates-scrapers/pull/5711) | DC PDF query string mimetype | ✅ Merged |
| [#5712](https://github.com/openstates/openstates-scrapers/pull/5712) | Biennium end_date off-by-one (DC, MI, NC, PA) | 🔄 Open |
| [#5716](https://github.com/openstates/openstates-scrapers/pull/5716) | LA action table variable column count (`_` → `*_`) | ✅ Merged 2026-07-01 |
| [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) | VA csv_bills hardcoded session ID + type annotation fix | 🔄 Open |
| [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) | OK session list (PROD) suffix not stripped | 🔄 Open |

## OpenStates Issues Filed by Tamara

| Issue | Description | Status |
|-------|-------------|--------|
| [#1372](https://github.com/openstates/issues/issues/1372) | Filed 2026-06 | 🔄 Open |
| [#1373](https://github.com/openstates/issues/issues/1373) | Filed 2026-06 | 🔄 Open |
| [#1374](https://github.com/openstates/issues/issues/1374) | Filed 2026-06 | 🔄 Open |
| [#1375](https://github.com/openstates/issues/issues/1375) | Filed 2026-06 | 🔄 Open |
| [#1376](https://github.com/openstates/issues/issues/1376) | LA action table column count varies by session (PR #5716 merged) | ✅ Resolved by PR #5716 |
| [#1377](https://github.com/openstates/issues/issues/1377) | VA csv_bills hardcoded session ID ignores --session argument | 🔄 Open (PR #5717 pending) |
| [#1378](https://github.com/openstates/issues/issues/1378) | OK session list (PROD) suffix not stripped | 🔄 Open (PR #5718 pending) |
| [#1379](https://github.com/openstates/issues/issues/1379) | LA bill search only returning ~7 of 525 bills — abbreviation and pattern issues | 🔄 Open — waiting on maintainers |
