# Scraper Health Log

Tracks the status of all 56 `govbot-openstates-scrapers` repos. Updated manually after health checks.

---

### Fix Pending

| State | Status             | Issue                                 | Notes                                                                                                                                                                                                                                                                                                                                                                               |
| ----- | ------------------ | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| va    | 🔧 fix in progress | Scrape argument bug                   | Session ended Mar 14. Root cause found: `--session` flag was before scraper name in `scrape.sh`, and `csv_bills` had hardcoded session ID. govbot PR [#52](https://github.com/chihacknight/govbot/pull/52) fixes `scrape.sh`; OpenStates PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) fixes `csv_bills`. After both merge, run apply-templates for `va`. |
| vi    | ❌ server down     | `billtracking.legvi.org:8082` offline | VI is in active session but the site is returning connection timeouts. No code fix possible — waiting for the site to come back online.                                                                                                                                                                                                                                             |

### Self-Hosted Runner States

| State | Status                     | Notes                                                                                                                                                                                                                               |
| ----- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| tx    | ⏸️ out of session          | `capitol.texas.gov` blocks Azure IPs — requires self-hosted runner. Runner now registered at org level. Will resume when next session starts.                                                                                       |
| ma    | 🔄 running on self-hosted  | `malegislature.gov` throttles Azure IPs. Running on MacBook runner daily. PR [#53](https://github.com/chihacknight/govbot/pull/53) pending merge.                                                                                   |
| fl    | 🔧 one-time scrape pending | Session ended. Needs one final scrape from self-hosted runner to capture end-of-session data, then move back to paused.                                                                                                             |
| tn    | 🔧 backfill needed         | `wapp.capitol.tn.gov` blocks Azure IPs (N1_ACTIVE_BLOCK). 114th GA (2025-2026) ended ~2026-04-25 — only 37 of ~5,400+ bills scraped before block hit. Needs one self-hosted runner scrape. Next session: 115th GA, ~January 2027. |

### Cancelled (Timeout) — Now Resolved

| State | Previous Status             | Resolution                              |
| ----- | --------------------------- | --------------------------------------- |
| fl    | ⏸️ cancelled after 4+ hours | Moved to self-hosted runner (see above) |
| ma    | ⏸️ cancelled after 4+ hours | Moved to self-hosted runner (see above) |

### On Fallback (Scraper Error, Serving Stale Data)

| State | Failure Type      | Error                                                                                                                                                                                                                                     | Action                                                                                                                                        |
| ----- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| la    | S5_SITE_STRUCTURE | Crash fixed via PR [#5716](https://github.com/openstates/openstates-scrapers/pull/5716) (merged 2026-07-01). Ran manually after merge — only 7 of 525 bills scraped. Root cause: `r={}1*` search pattern + abbreviation discovery issues. | Issue [#1379](https://github.com/openstates/issues/issues/1379) filed — waiting on OpenStates maintainers                                     |
| ok    | S3_SESSION_CONFIG | `CommandError: Session(s) "1998 Regular Session (PROD)" not found` — `(PROD)` suffix not stripped from session list                                                                                                                       | PR [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) merged 2026-07-01 — fix will take effect on next Docker image release |

### Clean (50/56)

All other states ran successfully. Notable counts:

| State | Files  | Notes                                       |
| ----- | ------ | ------------------------------------------- |
| ny    | 24,937 |                                             |
| ca    | 22,680 |                                             |
| il    | 15,323 |                                             |
| mt    | 13,258 |                                             |
| usa   | 11,960 |                                             |
| mn    | 9,815  |                                             |
| nj    | 8,212  |                                             |
| pa    | 6,423  |                                             |
| wa    | 5,713  |                                             |
| pr    | 5,081  |                                             |
| de    | 3,065  |                                             |
| ms    | 3,033  |                                             |
| mi    | 2,913  |                                             |
| nc    | 2,432  |                                             |
| oh    | 2,167  |                                             |
| nd    | 3,265  |                                             |
| ne    | 1,976  |                                             |
| al    | 1,511  |                                             |
| ks    | 1,487  |                                             |
| sc    | 3,947  |                                             |
| ri    | 4,132  |                                             |
| ia    | 3,748  |                                             |
| me    | 3,613  |                                             |
| mo    | 4,640  |                                             |
| dc    | 2,713  | DC fix (PRs #5706, #5711) confirmed working |
| gu    | 833    |                                             |
| vt    | 953    |                                             |
| ak    | 942    |                                             |
| co    | 736    |                                             |
| or    | 268    |                                             |
| ga    | 460    |                                             |
| md    | 535    |                                             |
| wi    | 2,701  |                                             |
| wv    | 45     |                                             |
| wy    | 27     |                                             |
| sd    | 45     |                                             |
| ky    | 78     |                                             |
| nv    | 64     |                                             |
| ut    | 28     |                                             |
| mp    | 139    |                                             |
| in    | 47     |                                             |
| nh    | 437    |                                             |
| ar    | 4      | Active special session `2026S1` (May 4–Aug 15). FTP source has 2 bills (SB1, HB1001) but scraper produces 0 with EXIT_CODE=0. Root cause unclear — likely stale scrapelib cache or silent pupa validation failure. Needs Docker-level investigation. |
| az    | 4      | Out of session — ended Apr 17               |
| ct    | 4      | Out of session                              |
| hi    | 4      | Out of session — ended May 8                |
| id    | 5      | Out of session                              |
| nm    | 4      | No 2026 session                             |
| tn    | 37     | Out of session — ended Apr 15               |

---

## Known Ongoing Issues

### FL — Serial Per-Bill Scraping (Out of Session)

FL session ended; one final scrape needed to capture end-of-session data.

Root cause of 6-hour cancellations: the FL scraper fetches each bill individually — BillDetail page, HouseSearchPage, HouseBillPage, then N vote PDFs in a pagination loop ("Votes don't add up; looking for additional ones"). Just one bill (HJR 1F) took ~34 seconds and required 7 separate vote PDF fetches. Across hundreds of bills in two sessions (`2026` and `2026F`), this exhausts the 6-hour GitHub Actions cap. No evidence of IP blocking — `flsenate.gov` and `flhouse.gov` serve Azure IPs without issue, it's just a slow serial design.

**Fix in progress**: `fl-legislation` workflow updated to `runs-on: self-hosted`. Once MA finishes and PR [#53](https://github.com/chihacknight/govbot/pull/53) is merged, trigger FL manually. After data is captured, move FL back to `openstates-scrape-paused` template via pipeline-manager config + apply-templates.

### MA — Active Throttling by malegislature.gov

MA is actively throttling Azure-originating requests. Response times ramp up progressively within a single run: 36s → 72s → 300s → server errors → connection drop. Run history confirms this: some days complete in 1-2 hours (light throttling), other days cancel after 6 hours (heavy throttling). Two `Server Error` responses visible mid-run on HD3106 and HD3112. The scraper eventually fails and retries from scratch, burning more time.

This is the same underlying pattern as TX (hostile to scraping from cloud IPs), just throttling instead of a hard block. A self-hosted runner on a home network IP bypasses the Azure IP detection.

**Fix in progress**: `ma-legislation` workflow updated to `runs-on: self-hosted` (via PR [#53](https://github.com/chihacknight/govbot/pull/53)). First run on self-hosted runner in progress as of 2026-07-01. After PR merges, MA will stay on self-hosted for all future daily scrapes.

### VA — Scrape Argument Bug (Fix Pending)

VA session ended Mar 14, 2026. Workflows were disabled since 2026-04-01. Root cause traced to `scrape.sh`: `--session=2025` was placed before the scraper name (`csv_bills`), which OpenStates rejects. Fix (correct arg order + bumped to `--session=2026`) is on `fix/va-vi-scrapers` branch in govbot — **needs PR, merge, and apply-templates run** to push updated `scrape.sh` to va-legislation repo. VA csv_bills also had a hardcoded `session_id = "20251"` ignoring the `--session` argument — fixed in OpenStates PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) (open). Issue [#1377](https://github.com/openstates/issues/issues/1377) filed.

### VI — Server Down

VI is in active session but `billtracking.legvi.org:8082` is returning connection timeouts. This is a server-side outage — no code fix possible until the site comes back online.

### TN — IP Block by wapp.capitol.tn.gov (Backfill Needed)

TN's 114th General Assembly (2025-2026) ended ~2026-04-25. The scraper was blocked by `wapp.capitol.tn.gov` early in the run — only 37 of an estimated ~5,400+ bills were captured before the block hit.

The site itself is accessible from non-cloud IPs (confirmed via manual fetch). The block is specific to GitHub-hosted runner IPs (N1_ACTIVE_BLOCK), same pattern as TX.

**Bill count estimate**: The index page at `wapp.capitol.tn.gov/apps/indexes/BillsByIndex/?year=114` shows 98 listing pages — HB0001–HB2671, SB0001–SB2733, plus HJR, SJR, HR, SR series. Roughly 5,400+ total.

**Scraper mechanism** (`scrapers/tn/bills.py`): fetches the index page → follows 98 paginated listing links → fetches each individual bill page. Gets blocked partway through the listing pages, producing a partial result.

**Fix**: add `runner: self-hosted` to TN in `chn-openstates-scrape.yml`, run apply-templates, then trigger one manual dispatch on `tn-legislation` to do the full backfill. After successful run, TN stays on self-hosted for future sessions.

**Next session**: 115th General Assembly, expected ~January 2027 (TN sessions start in odd years).

### TX — Self-Hosted Runner Dependency (Out of Session)

TX is currently out of session (paused). When it returns, scrapes require Tamara's MacBook (`~/actions-runner/`) to be online. `capitol.texas.gov` actively blocks Azure IP ranges used by GitHub-hosted runners. Runner is now registered at the **org level** (`govbot-openstates-scrapers`) so it covers MA, FL, and TX. Runbook: `actions/scrape/docs/tx-backfill-runbook.md`.

---

## OpenStates PRs Filed by Tamara (tamara-builds)

| PR                                                                   | Description                                                     | Status               |
| -------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------- |
| [#5706](https://github.com/openstates/openstates-scrapers/pull/5706) | DC: scraper crashes on non-PDF attachments, dropping most bills | ✅ Merged 2026-06-29 |
| [#5707](https://github.com/openstates/openstates-scrapers/pull/5707) | NJ: skip votes for bills missing from bill_dict                 | ✅ Merged 2026-06-29 |
| [#5711](https://github.com/openstates/openstates-scrapers/pull/5711) | DC: handle PDF URLs with query strings in actions block         | ✅ Merged 2026-06-30 |
| [#5712](https://github.com/openstates/openstates-scrapers/pull/5712) | Biennium end_date off-by-one (DC, MI, NC, PA)                   | ✅ Merged 2026-07-01 |
| [#5716](https://github.com/openstates/openstates-scrapers/pull/5716) | LA: handle variable action table column count (`_` → `*_`)      | ✅ Merged 2026-07-01 |
| [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) | VA: fix csv_bills hardcoded session ID + type annotation        | 🔄 Open              |
| [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) | OK: strip (PROD) suffix from session list                       | ✅ Merged 2026-07-01 |

## OpenStates Issues Filed by Tamara

| Issue                                                     | Description                                                                      | Status                           |
| --------------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------- |
| [#1372](https://github.com/openstates/issues/issues/1372) | DC: scraper crashes on non-PDF attachments                                       | ✅ Closed (PR #5706)             |
| [#1373](https://github.com/openstates/issues/issues/1373) | NJ: KeyError when bill appears in vote files before MAINBILL.TXT                 | ✅ Closed (PR #5707)             |
| [#1374](https://github.com/openstates/issues/issues/1374) | DC: scraper crashes on PDF attachment URLs with query strings                    | ✅ Closed (PR #5711)             |
| [#1375](https://github.com/openstates/issues/issues/1375) | Biennium session end_date off by one year (DC, MI, NC, PA)                       | ✅ Closed (PR #5712)             |
| [#1376](https://github.com/openstates/issues/issues/1376) | LA: action history table column count varies by session state                    | ✅ Closed (PR #5716)             |
| [#1377](https://github.com/openstates/issues/issues/1377) | VA: csv_bills hardcoded session ID ignores --session argument                    | 🔄 Open (PR #5717 pending)       |
| [#1378](https://github.com/openstates/issues/issues/1378) | OK: session list (PROD) suffix not stripped                                      | ✅ Closed (PR #5718)             |
| [#1379](https://github.com/openstates/issues/issues/1379) | LA: bill search only returning ~7 of 525 bills — abbreviation and pattern issues | 🔄 Open — waiting on maintainers |
