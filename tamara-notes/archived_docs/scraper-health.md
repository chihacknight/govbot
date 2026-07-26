# Scraper Health Log

Tracks the status of all 56 `govbot-openstates-scrapers` repos. Updated manually after health checks.

---

## 2026-07-02 Status Update

### Self-Hosted Runner States

3 runners now active on MacBook (`~/actions-runner/`, `~/actions-runner-2/`, `~/actions-runner-3/`) registered at org level (`govbot-openstates-scrapers`).

| State | Status               | Notes                                                                                                                                                                                         |
| ----- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| tx    | ⏸️ out of session    | `capitol.texas.gov` blocks Azure IPs. Runner ready. Resumes ~Jan 2027.                                                                                                                        |
| ma    | ⚠️ needs runner uptime | First self-hosted run completed 2026-07-02 in 7h 43m. PR [#53](https://github.com/chihacknight/govbot/pull/53) ✅ merged. But 6 straight nightly runs (07-07 → 07-12) show `cancelled` — no runner was online to pick up the schedule. See "MA" under Known Ongoing Issues.                                        |
| ct    | ✅ confirmed working | Azure IP blocks CT FTP server. Self-hosted run 2026-07-02: 1,283 bills in 17 min. Issue [#1384](https://github.com/openstates/issues/issues/1384) 🔄 following up.                            |
| fl    | 🔄 backfill running  | End-of-session capture in progress on self-hosted runner. PRs [#53](https://github.com/chihacknight/govbot/pull/53) + [#55](https://github.com/chihacknight/govbot/pull/55) ✅ merged.        |
| tn    | ✅ backfill complete | 114th GA + 114S1 special session data landed 2026-07-02 (~25,800 raw files, ~9,092 bills in session 114). Self-hosted runner via PR [#56](https://github.com/chihacknight/govbot/pull/56) ✅. |
| il    | ✅ confirmed working | Two real upstream markup fixes landed (#5721, #5730 — `h5`→`h2` selector changes), but a third "IndexError" crash persisted on GitHub-hosted runners even after both merged. Confirmed 2026-07-13 by running locally: same code, same site, clean run — Azure/GitHub-hosted IPs get served different content that breaks the title xpath on the first bill. Not a scraper bug. `runner: self-hosted` added to pipeline-manager config. |
| wv    | ✅ confirmed working | Same Azure-block pattern as IL/CT/HI/MA/TN — not a scraper bug. See "WV" under Known Ongoing Issues. `runner: self-hosted` added to pipeline-manager config 2026-07-13. Backfill run 2026-07-14: landed at exactly 2,975 bills, matching jessemortenson's reported count. |
| nc    | ✅ confirmed working | Frozen at Dec 2025 data for ~7 months; **not** an IP block (unlike most others in this table) — see "NC" under Known Ongoing Issues. Self-hosted run 2026-07-14: 2,334 bills in 12.5 min, matching the live site's current feed count exactly. |

### Fix Pending

| State | Status                   | Notes                                                                                                                                                                                                                                                                                                            |
| ----- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| va    | ❓ needs verification    | `scrape.sh` arg order + session fixed (PR [#54](https://github.com/chihacknight/govbot/pull/54) ✅). OpenStates PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) ✅ merged 2026-07-01. Trigger a verification run; close issue [#1377](https://github.com/openstates/issues/issues/1377). |
| wv    | 🔧 waiting on OpenStates | XPath broken after site redesign — 0 bills scraped. PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) 🔄 open. Backfill after merge.                                                                                                                                                       |
| vi    | ❌ server down           | `billtracking.legvi.org:8082` offline. Active session but no code fix possible.                                                                                                                                                                                                                                  |

### Backfill Needed (Docker Timing / Stale Cache)

These states have accessible APIs but were scraped with partial data due to Docker image timing or stale GitHub Actions cache.

| State | Files | Notes                                                                                     |
| ----- | ----: | ----------------------------------------------------------------------------------------- |
| sd    |    41 | Cache cleared 2026-07-02. Fresh backfill dispatch running now — expect 666 bills.         |
| ut    |    28 | 3/1,016 2026 bills (stale cache) + 5 complete 2025S2 bills. Needs cache clear + dispatch. |
| in    |    47 | ~40/1,000+ bills. Docker got 2026 session Mar 23; session ended Feb 27. Needs dispatch.   |
| id    |     5 | 1 bill only. Docker got 2026 session late; session ended Apr 2. Needs dispatch.           |

### Needs Verification Run

| State | Notes                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ok    | PR [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) ✅ merged 2026-07-01 — (PROD) suffix fix. Trigger manual dispatch to confirm bills scraped. |

### WAF / Site Blocking (OpenStates Fix Needed)

| State | Files | Issue                                                        | Notes                                                              |
| ----- | ----: | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| az    |     4 | [#1382](https://github.com/openstates/issues/issues/1382) 🔄 | Sucuri WAF blocks `setsession.php` POST. Full 2026 session missed. |
| hi    |     4 | [#1383](https://github.com/openstates/issues/issues/1383) 🔄 | Cloudflare WAF blocks all bill pages. Full 2026 session missed.    |

### FTP Data Sources (OpenStates Fix Needed)

| State | Files | Issue                                                        | Notes                                                                                                                                                                                                                                                                                            |
| ----- | ----: | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| nm    |     4 | [#1381](https://github.com/openstates/issues/issues/1381) 🔄 | Scrapelib makes the FTP request but directory listing format doesn't match regex in `_init_mdb`. Original diagnosis ("scrapelib can't handle FTP") was wrong per maintainer. Following up with traceback.                                                                                        |
| ct    | 1,283 | [#1384](https://github.com/openstates/issues/issues/1384) 🔄 | **Confirmed Azure IP block on FTP.** CT uses `ftp://ftp.cga.ct.gov/pub/data/bill_info.csv` for initial bill list — Azure blocks FTP → empty list → "no objects returned". Missed entire 2026 session. Self-hosted runner run 2026-07-02: 1,283 bills in 17 minutes. Moved to self-hosted runner. |

### Active Session / Scraper Mystery

| State | Files | Notes                                                                                                                                                                                                                                            |
| ----- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| ar    |     4 | Active session `2026S1` (May 4–Aug 15). FTP source has 2 bills (SB1, HB1001) but scraper produces 0 with EXIT_CODE=0. Root cause unclear — likely stale scrapelib cache. Needs Docker-level investigation.                                       |
| la    |     7 | Crash fixed PR [#5716](https://github.com/openstates/openstates-scrapers/pull/5716) ✅. Only 7/525 bills returned — bill search pattern issues. Issue [#1379](https://github.com/openstates/issues/issues/1379) 🔄 open, waiting on maintainers. |

---

## Known Ongoing Issues

### NC — Not an IP Block, Just Never Ran on a Runner That Was Online

A full 56-repo audit (2026-07-14) of `govbot-data` — comparing the last commit that actually
touched a `sessions/` path (not the daily tracking-file commit that fires regardless of new
data) against the corrected session calendar — found **16 states plus the USA/federal repo**
all frozen at the exact same 10-minute window: **2025-12-14, 23:31–23:41 UTC**. That's not a
gradual per-state legislative slowdown (which shows up as a staircase, and most of the other
40 states do show one); it's a hard cliff, all at once. NC, a currently-in-session state per
the LegiScan calendar (convened 2026-04-21), was in that frozen list.

Investigated like IL/WV: pulled NC's actual bill-discovery feed
(`ncleg.gov/Legislation/Bills/FiledBillsFeed/2025/{S,H}`) directly and confirmed it's fully
accessible and current — 1,090 Senate + 1,244 House bills live today, no blocking, no
different content served. Ruled out an Azure IP block. GitHub Actions log retention is 90
days, so the actual December logs were already gone (`HTTP 410`) by the time this was
investigated — the original failure mode couldn't be reconstructed after the fact.

**Real explanation, found by actually running it**: NC's `runner` was never set to
`self-hosted` — it was quietly stuck on `ubuntu-latest` this whole time, structurally no
different from the many other "frozen" states discovered in this same audit that likely never
had the self-hosted fix applied to them either. Once switched to self-hosted and dispatched,
it picked up the current 2,334 bills (1,090 + 1,244, matching the live feed exactly) cleanly
in 12.5 minutes — no code changes needed. **Important: don't assume "frozen since Dec 14" ==
Azure IP block for the other 15 states in this cohort** — NC turned out to be a config gap,
not a network problem. Each of the other 15 (`usa, ak, ar, il, in, mi, ne, nm, nv, ny, oh,
pa, sc, vi, vt`) needs the same live verification before assuming a cause.

**Bonus find while debugging this**: the self-hosted run's job summary showed `📦 Nightly
fallback` / all metrics `N/A` — looked like the fresh scrape got discarded. It didn't; this
was the `tar --mode=755` macOS-BSD-tar-incompatibility bug (see fix below), a cosmetic
reporting bug, not data loss. Confirmed by checking the actual git commit on
`govbot-openstates-scrapers/nc-legislation` directly — the real 2,334-bill commit landed
fine despite the misleading summary.

### tar --mode=755 macOS Incompatibility (Fixed 2026-07-14)

`actions/scrape/scrape.sh` built its release tarball with `tar zcf ... --mode=755`, a
GNU-tar-only flag. macOS's built-in BSD tar doesn't support it and fails silently at that
step — but by then the real scraped files were already copied into `_data/{state}/`, so the
actual data commit was unaffected. The failure only broke the job summary (forced it into
"nightly fallback" mode, reporting `N/A` for every metric and a stale file count) — actively
misleading anyone checking a self-hosted Mac run's results. Confirmed this cosmetic-only
via IL (real commit had all 12,753 files despite summary saying `4`) and NC (real commit had
all 2,334 bills despite summary saying `2432`, the old Dec 2025 count). **Fix**: replaced
`--mode=755` with a `chmod -R 755` before a plain `tar` call — works identically on GNU and
BSD tar.

### TN — IP Block by wapp.capitol.tn.gov

TN's 114th General Assembly (2025-2026) ended ~2026-04-25. The scraper was blocked by `wapp.capitol.tn.gov` early in the run — only 37 of an estimated ~5,400+ bills were captured before the block hit. Site is accessible from non-cloud IPs; block is specific to GitHub-hosted runner IPs (N1_ACTIVE_BLOCK), same pattern as TX.

**Bill count estimate**: Index at `wapp.capitol.tn.gov/apps/indexes/BillsByIndex/?year=114` shows 98 listing pages — HB0001–HB2671, SB0001–SB2733, plus HJR, SJR, HR, SR series. Roughly 5,400+ total.

**Fix applied 2026-07-02**: `runner: self-hosted` added to TN (PR [#56](https://github.com/chihacknight/govbot/pull/56)), apply-templates run, full backfill dispatch triggered. Next session: 115th GA ~January 2027.

### IL — Azure IP Block Masquerading as Site-Structure Break

`ilga.gov` changed its bill-detail markup twice in July, breaking two different xpath selectors in `scrapers/il/bills.py`: the bill title (`h5`→`h2`, fixed upstream in [#5721](https://github.com/openstates/openstates-scrapers/pull/5721), merged 2026-07-02) and the actions table (`h5`→`h2`, fixed in [#5730](https://github.com/openstates/openstates-scrapers/pull/5730), merged 2026-07-10). `openstates/scrapers:latest` was rebuilt automatically after both merges.

Despite that, a manual dispatch on 2026-07-13 still failed with `IndexError: list index out of range` at the same title-xpath line — on the very first bill (`HB1`), before any session-matching logic even runs. GitHub's own annotation classified it as `S5_SITE_STRUCTURE` (pattern-matched on "IndexError").

That diagnosis was wrong. Running the identical scraper code against the identical URL from a home network succeeded cleanly (bills saving one after another, e.g. `save bill HB22 in 104th`). The `h2` xpath matches fine outside CI. This is the same failure shape as CT and HI: GitHub-hosted (Azure) runner IPs get served different/incomplete content by the state site, which then reads as a "site structure changed" parsing error when it's actually IP-based blocking or bot detection.

**Fix**: `runner: self-hosted` added to IL's entry in `actions/pipeline-manager/chn-openstates-scrape.yml` (2026-07-13), matching CT/HI/MA/AZ/TN. No OpenStates PR needed — the upstream code is already correct.

### WV — Azure IP Block, Not a Broken Selector (Our PR Was Wrong)

We filed PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) theorizing the bill-listing xpath broke after a site redesign (`bill: 39` vs jessemortenson's reported `bill: 2975`). Maintainer rejected it 2026-07-08: our PR unknowingly reverted his own intentional fix from PR [#5703](https://github.com/openstates/openstates-scrapers/pull/5703) (`//a[contains(@href, 'Bills_history')]` → `//table[@id='results']//tr/td[1]/a`), which had fixed a real accuracy bug (the old broad selector picked up "Incorporated into Com. Sub. for SBxxx" cross-references, not just this chamber's own bills). Reverting it would have made WV's data *worse*, not better — he was not going to merge it, full stop.

To find the real cause, we tested the **current** (post-#5703, already-correct) selector directly against the live site from a home network: `Bills_all_bills.cfm?year=2026&sessiontype=RS&btype=bill&orig=h` returned 1,693 links, `orig=s` returned 1,084 — 2,777 combined, in the neighborhood of jessemortenson's 2,975 (resolutions would close the rest of the gap). The code is correct and works fine outside CI. Confirmed live 2026-07-13 with a local scraper run (bills saving cleanly one after another, e.g. `save bill SB 7 in 2026`).

Same failure shape as IL/CT/HI/MA/TN: GitHub-hosted (Azure) runner IPs get served a near-empty results table by `wvlegislature.gov`, which reads as a "site structure changed" bug when it's actually IP-based blocking. One hint from the maintainer: OpenStates routes WV scrapes through `tinyproxy` on a GCP VM — they may have needed to route around the same problem without framing it that way.

**Fix**: `runner: self-hosted` added to WV's entry in `actions/pipeline-manager/chn-openstates-scrape.yml` (2026-07-13), matching IL/CT/HI/MA/AZ/TN. No new OpenStates PR — the upstream code is already correct; do not resubmit a variant of #5719.

**Confirmed 2026-07-14**: backfill landed at exactly 2,975 bills, matching jessemortenson's reported count.

### MA — Active Throttling by malegislature.gov

`malegislature.gov` throttles Azure-originating requests progressively: 36s → 72s → 300s → connection drop. Fixed by moving to self-hosted runner. First successful run 2026-07-02 completed in 7h 43m. Now runs daily on MacBook runner.

**"4 files" scare (2026-07-13), false alarm**: A 9h43m overnight run ([28783093789](https://github.com/govbot-openstates-scrapers/ma-legislation/actions/runs/28783093789), 2026-07-06) looked like it failed with only 4 files pushed. It didn't — it succeeded, scraped 11,026 bills, and pushed a real commit. The "4 files" reading came from the job summary step, which does `⚠️ No summary file found, assuming success` and falls back to a default file count on self-hosted runs — `scrape-summary.json` isn't being found/read the same way it is on GitHub-hosted runners. The step summary is unreliable for self-hosted MA runs; check the actual commit history instead of trusting the Action's summary annotation.

**Real problem found while checking**: every scheduled MA run from 2026-07-07 through 2026-07-12 (six in a row) shows `cancelled`, not `success` or `failure` — the nightly cron queued each day but no self-hosted runner was online to pick it up. The 2026-07-13 run only started because a runner happened to be started manually that day. MA's self-hosted runner needs to be running continuously (or the schedule/runner-uptime needs rethinking) or the nightly cron will keep silently queuing and cancelling instead of actually scraping.

**Extraction is very likely hitting the same Azure-block wall.** `extract-text` for MA currently runs from a GitHub-hosted runner in a separate pilot org (`govbot-test`, e.g. [run 29279441540](https://github.com/govbot-test/ma-legislation/actions/runs/29279441540), using `chihacknight/govbot/actions/extract@feat/session-scoped-repo-lifecycle`) — same site, same IP-blocking problem as the scrape step already has. Needs the same self-hosted-runner treatment; TODO for a follow-up session, tracked in [[project-govbot-state-specific-followups]].

### FL — Serial Per-Bill Scraping

FL scraper fetches each bill individually (BillDetail + HouseSearchPage + N vote PDFs). One bill (HJR 1F) took ~34s with 7 vote PDF fetches. Across two sessions (`2026` + `2026F`), this exceeds the 6-hour GitHub Actions cap. No IP blocking — it's just slow. Fixed by moving to self-hosted runner (no GitHub-imposed time cap).

**Update 2026-07-14**: moving to self-hosted wasn't the full fix — we then hit our *own*
self-imposed `timeout-minutes: 720` (12h) ceiling on a 2026-07-13 run, which got past bill
250+ with zero bot-detection errors before being killed by the timeout. Since `scrape.sh`
only commits after the full run completes, that entire 12 hours of real progress was lost
when the job got cancelled — nothing to recover, the runner's workspace was reused by later
jobs before anyone checked. Raised `timeout-minutes` to 1440 (24h) on FL's live workflow;
longer run in progress as of 2026-07-14. Real long-term fix is committing progress
incrementally during the run rather than only at the end, so a timeout (whatever the limit)
stops being catastrophic — see PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724)
and `fl-incremental-scraping-proposal.md`, both still open.

### VA — Scrape Argument Bug (Waiting on OpenStates)

`scrape.sh` arg order fixed and session bumped to 2026 (PR [#54](https://github.com/chihacknight/govbot/pull/54) ✅). Apply-templates run. Waiting on OpenStates PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) to fix hardcoded `session_id="20251"` in `csv_bills`. Will trigger scrape once #5717 merges.

### TX — Self-Hosted Runner Dependency (Out of Session)

TX out of session (no 2026 regular session). Requires MacBook runner when active — `capitol.texas.gov` blocks Azure IPs. Runner registered at org level. Runbook: `actions/scrape/docs/tx-backfill-runbook.md`.

---

## govbot PRs

| PR                                                    | Description                               | Status               |
| ----------------------------------------------------- | ----------------------------------------- | -------------------- |
| [#52](https://github.com/chihacknight/govbot/pull/52) | VA/VI scraper arg order + session fix     | ✅ Merged            |
| [#53](https://github.com/chihacknight/govbot/pull/53) | MA + FL self-hosted runner                | ✅ Merged 2026-07-02 |
| [#54](https://github.com/chihacknight/govbot/pull/54) | VA scrape.sh arg order + session 2026     | ✅ Merged 2026-07-02 |
| [#55](https://github.com/chihacknight/govbot/pull/55) | MA/FL runner docs + scrape.sh grep -E fix | ✅ Merged 2026-07-02 |
| [#56](https://github.com/chihacknight/govbot/pull/56) | TN self-hosted runner + IP block docs     | ✅ Merged 2026-07-02 |

## OpenStates PRs Filed by Tamara (tamara-builds)

| PR                                                                   | Description                                     | Status               |
| -------------------------------------------------------------------- | ----------------------------------------------- | -------------------- |
| [#5706](https://github.com/openstates/openstates-scrapers/pull/5706) | DC: scraper crashes on non-PDF attachments      | ✅ Merged 2026-06-29 |
| [#5707](https://github.com/openstates/openstates-scrapers/pull/5707) | NJ: skip votes for bills missing from bill_dict | ✅ Merged 2026-06-29 |
| [#5711](https://github.com/openstates/openstates-scrapers/pull/5711) | DC: handle PDF URLs with query strings          | ✅ Merged 2026-06-30 |
| [#5712](https://github.com/openstates/openstates-scrapers/pull/5712) | Biennium end_date off-by-one (DC, MI, NC, PA)   | ✅ Merged 2026-07-01 |
| [#5716](https://github.com/openstates/openstates-scrapers/pull/5716) | LA: handle variable action table column count   | ✅ Merged 2026-07-01 |
| [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) | VA: fix csv_bills hardcoded session ID          | ✅ Merged 2026-07-01 |
| [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) | OK: strip (PROD) suffix from session list       | ✅ Merged 2026-07-01 |
| [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) | WV: XPath broken after site redesign            | 🔄 Open              |

## OpenStates Issues Filed by Tamara

| Issue                                                     | Description                                                        | Status                                                                      |
| --------------------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| [#1372](https://github.com/openstates/issues/issues/1372) | DC: scraper crashes on non-PDF attachments                         | ✅ Closed 2026-06-30                                                        |
| [#1373](https://github.com/openstates/issues/issues/1373) | NJ: KeyError on early vote files                                   | ✅ Closed 2026-06-30                                                        |
| [#1374](https://github.com/openstates/issues/issues/1374) | DC: scraper crashes on PDF URLs with query strings                 | ✅ Closed 2026-06-30                                                        |
| [#1375](https://github.com/openstates/issues/issues/1375) | Biennium end_date off by one year (DC, MI, NC, PA)                 | ✅ Closed 2026-07-01 — resolved by PR #5712                                 |
| [#1376](https://github.com/openstates/issues/issues/1376) | LA: action table column count varies                               | ✅ Closed — resolved by PR #5716                                            |
| [#1377](https://github.com/openstates/issues/issues/1377) | VA: csv_bills hardcoded session ID                                 | 🔄 Open — PR #5717 merged; needs close                                      |
| [#1378](https://github.com/openstates/issues/issues/1378) | OK: (PROD) suffix not stripped                                     | ✅ Closed 2026-07-01 — resolved by PR #5718                                 |
| [#1379](https://github.com/openstates/issues/issues/1379) | LA: bill search returning ~7 of 525 bills                          | 🔄 Open — waiting on maintainers                                            |
| [#1380](https://github.com/openstates/issues/issues/1380) | WV: XPath broken after site redesign                               | 🔄 Open — maintainer disputes; need to provide failing scrape logs          |
| [#1381](https://github.com/openstates/issues/issues/1381) | NM: FTP directory listing regex mismatch                           | 🔄 Open — following up with traceback                                       |
| [#1382](https://github.com/openstates/issues/issues/1382) | AZ: Sucuri WAF blocks setsession.php POST                          | ✅ Closed 2026-07-02 — maintainer: anti-WAF out of scope for OSS; use proxy |
| [#1383](https://github.com/openstates/issues/issues/1383) | HI: Cloudflare WAF blocks bill pages                               | ✅ Closed 2026-07-02 — maintainer: anti-WAF out of scope for OSS; use proxy |
| [#1384](https://github.com/openstates/issues/issues/1384) | CT: zero bills mid-session — possible Azure IP block on FTP server | 🔄 Open — following up with April run logs                                  |
