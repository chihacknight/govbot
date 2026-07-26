# OpenStates Communications

Working doc for reviewing and drafting responses to OpenStates maintainers.
Grouped by state. Each entry has the issue/PR, current status, maintainer messages, and notes/draft.

---

## AZ

**Issue [#1382](https://github.com/openstates/issues/issues/1382)** — Sucuri WAF blocks `setsession.php` POST — zero bills for entire 2026 session
**Status:** ✅ Closed by maintainer

**Maintainer message (showerst):**

> @tamara-builds if you can get a working PR that avoids the WAF without a proxy by modifying the request params we'll happily accept it. FWIW you might try scraping this one from a different web host, we haven't run into any blocking here.

**Our follow-up (2026-07-02):** Moved AZ to a self-hosted runner on our home network. The POST to `setsession.php` goes through fine (no WAF blocking from a home IP) — but we still hit `AssertionError: Session ID not in bill list` on both Azure and home network runs. Original WAF diagnosis was wrong. Actual bug: after the POST to `setsession.php`, `req` is reassigned to the POST response — `response.cookies` only contains cookies from that response, not ones sent with it. If `setsession.php` doesn't echo a `Set-Cookie: PHPSESSID=...` header back, the final GET has no session cookie. Filed **PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722)** — saves initial GET cookies, merges in new cookies from the POST, uses the merged set for the final GET.

**Maintainer reply (jessemortenson, 2026-07-08):**

> @tamara-builds similar to what @showerst reported in the issue, I have not experienced any issues running this scraper, whether in the cloud or locally. When i run `docker run openstates/scrapers:latest az bills --scrape` on my laptop, the scraper is running and yielding bills.
>
> What are your steps to reproduce the log output that you report in this PR?

**Status:** 🔄 PR #5722 open — awaiting our repro steps

**Notes:**
Need to give jessemortenson exact reproduction steps (Docker command, environment, timing) for the cookie bug — he can't reproduce it at all.

---

## AR

**Status:** 🔍 Data gap identified — no issue filed yet

**Finding (2026-07-02):**
The govbot-data `ar-legislation` repo has **1,928+ bills from the 2025 Regular Session** but zero bills from either 2026 session. Two complete sessions are missing: the 95th General Assembly Special (ended May 2026) and the 95th General Assembly Fiscal (ended May 2026). The repo has not received a bill update in approximately 8 months.

**Scraper log (2026-07-02 run):**
```
10:41:06 WARNING openstates: Skipping row in session 2025R because it does not match 2026S1
10:41:06 WARNING openstates: Skipping row in session 2025R because it does not match 2026S1
10:41:06 INFO scrapelib: GET - 'https://arkleg.state.ar.us/Home/FTPDocument?path=%2FSessionInformation%2FChamberActions.txt'
10:41:06 WARNING openstates: ARBillScraper raised EmptyScrape, continuing without any results

ar (scrape)
  bills: {}
bills scrape:
  duration:  0:00:00.188520
  objects:
jurisdiction scrape:
  objects:
    jurisdiction: 1
    organization: 3
Found 4 JSON files in _working/_data/ar
```

**Root cause:** The scraper filters FTP rows by the active session ID (`2026S1`), but `ChamberActions.txt` on Arkansas's FTP server contains rows labeled `2025R`. The 2026 session data either uses a different label on the FTP server or lives in a separate file the scraper isn't fetching. Result: EmptyScrape every run for ~8 months.

**Session state (from LegiScan, 2026-07-02):**
| Session | Modified | Status |
|---|---|---|
| 95th General Assembly (2025 Regular) | 2025-05-07 | Complete — in repo ✅ |
| 95th General Assembly Special (2026) | 2026-05-06 | Complete — **missing from repo ❌** |
| 95th General Assembly Fiscal (2026) | 2026-05-01 | Complete — **missing from repo ❌** |

**Next steps:**
- Look at the AR OpenStates scraper to see how it maps session IDs to FTP row labels
- Determine if `2026S1` corresponds to the Special session and what label the FTP file uses for it
- File an OpenStates issue with this analysis

---

## CT

**Issue [#1384](https://github.com/openstates/issues/issues/1384)** — Azure IP block on CT FTP server → zero bills entire 2026 session
**Status:** ✅ Closed — confirmed Azure IP block; moved to self-hosted runner

**Maintainer messages (showerst):**

> Just curious, what version of python are you running this on? I'm open to merging the fix as it looks cleaner, but these scrapers run fine for us.

> I just checked the code on this; our requests path goes through scrapelib which has a transparent callout to urllib.request which fetches the FTP files and then wraps the response in a requests.Response to allow it to fit into our logging. Does this fail for you in an environment with all the dependencies installed, or was this just Claude getting confused about the root cause?

**Our response sent 2026-07-02:**

> I spent some time working on CT today and I can now confirm the root cause. The original diagnosis was wrong and I'm sorry — Claude got the scrapelib internals incorrect.
>
> After switching CT to a self-hosted runner on my home network, I got **1,283 bills in 17 minutes** — after getting zero bills across the entire 2026 session from GitHub-hosted runners. Confirmed: Azure IPs are blocked by CT's FTP server (`ftp.cga.ct.gov`). The scraper uses FTP for the initial bill list (`bill_info.csv`) and HTTPS for individual bills. Azure blocks the FTP call → empty list → "no objects returned". From a home network, FTP works fine.
>
> Running Python 3.9.25 on the runner host (inside `openstates/scrapers:latest` Docker image). The fix is infrastructure, not code — we'll keep CT on a self-hosted runner going forward.

**Resolution:** Moved CT to self-hosted runner in pipeline manager. No code change needed.

---

## FL

**Status:** 🔄 PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724) open — issue [#1386](https://github.com/openstates/issues/issues/1386) filed — maintainer (`jessemortenson`) responded 2026-07-17 requesting a change; addressed 2026-07-23, awaiting re-review (corrected 2026-07-13: PR was mistyped as #5744, actual number is #5724)

**Finding (2026-07-02):**
The FL scraper produces zero bills despite 1–2 hours of active scraping. Home-network IPs are NOT blocked — `flsenate.gov` works fine throughout. The block is from `flhouse.gov` only, which returns HTTP 200 with "Request Rejected" HTML after sustained scraping of the 2026 regular session (SessionId=113). Spatula's `accept_response()` correctly detects this.

**Root cause:** `list()` in `scrape()` forces the entire session generator (~8,000 bills) to fully materialize before any bill is written to disk. When `RejectedResponse` is raised at bill ~160, `list()` propagates the exception and zero bills are saved — despite all the senate-side data having been fetched successfully.

```
spatula.pages.RejectedResponse: Response was rejected (4x) by accept_response: <Response [200]>
⚠️ scrape attempt 3 failed; sleeping 20s...
Found 22 JSON files in _working/_data/fl   ← 5 special session bills + metadata only
```

**Fix (PR #5724):**
1. Remove `list()` wrapper — bills stream to disk as they're yielded
2. Catch `RejectedResponse` in `_process_bill_list()` — scraper exits cleanly with partial data instead of crashing

**Scale context:** FL 2026 regular session has ~8,000 bills. At ~160/run before bot detection, full coverage needs ~50 runs. A separate incremental scraping proposal is in [tamara-notes/fl-incremental-scraping-proposal.md](fl-incremental-scraping-proposal.md) — filed as follow-up in issue #1386 pending OpenStates response.

**Secondary issue (macOS runner):** The action uses `tar --mode=755` (GNU tar flag) which fails silently on macOS's BSD tar. The workflow fell back to the previous nightly release tarball, so no data was lost. **Fixed 2026-07-14** in `actions/scrape/scrape.sh` — replaced with `chmod -R 755` before a plain `tar` call, which works on both GNU and BSD tar. This bug was actively confusing every self-hosted Mac run (FL, IL, NC all showed bogus "Nightly fallback / N/A" summaries despite the real data landing correctly).

**Maintainer feedback (2026-07-17, on PR #5724):** `jessemortenson` declined to merge as-is — his objection wasn't with streaming-as-yielded (he confirmed that part is desired), but with the scraper silently exiting "successfully" on a partial dataset. His own test run got ~1,400 bills vs. ~1,900 on a clean run; ours was getting <30. He offered a specific path to acceptance: put the partial-results behavior behind an opt-in parameter, defaulting to the current fail-loud behavior.

**Second root cause found while investigating the gap (2026-07-23):** Ran a side-by-side test — the real self-hosted scrape (with `--fastmode`) alongside a manually-started second docker container without `--fastmode`, writing to a separate scratch dir, to check whether fastmode explained the gap vs. the maintainer's numbers. It didn't: the no-fastmode container hung completely twice (at bill 11, then again at bill 172 after a restart), with `flhouse.gov` itself still responding fine from the host machine (`curl` returned 200 in 0.37s) — meaning the container's own connection was stuck, not the site. Traced to `spatula.URL` defaulting `timeout=None` (`spatula/sources.py:18`) — `HouseSearchPage`/`HouseBillPage` in `fl/bills.py` never pass an explicit `timeout` on their three `flhouse.gov` request constructions, so a stalled connection there waits forever instead of raising the `ConnectionError`/`Timeout` the scraper's existing retry/backoff logic is already built to catch (`fl_bills.py`'s `patched_get_response` explicitly catches `Timeout`, but it could never fire). This is a distinct bug from the `RejectedResponse` bot-detection issue — a silent hang, not a clean rejection — though both are scoped to `flhouse.gov` specifically.

Also useful context surfaced from two historical self-hosted runs ([29286687750](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/29286687750), 07-13; [29386003022](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/29386003022), 07-15): individual attempts within those runs went 5–7.5 hours without hitting bot detection at all, and the longest clean stretches lined up with FL overnight hours (~12:30am–8am Eastern). Neither run actually landed data in the repo (both predate the incremental auto-save feature and died to infra issues — a 12h timeout cap, then a 21h35m "runner lost communication" — before the final commit step ran), but they're the best evidence so far that bot-detection sensitivity may ease overnight, independent of the timeout/hang bug above.

**Fix pushed 2026-07-23 (same PR, new commits):**
1. `scrape()` now takes `allow_partial` (off by default) — a `RejectedResponse` re-raises by default (matching what the maintainer asked for); pass `allow_partial=true` on the command line (same convention as VA's `csv_bills --scrape session=2026`) to opt into keeping partial results instead.
2. Added `timeout=10` to all three `flhouse.gov` `URL(...)` constructions in `HouseSearchPage`/`HouseBillPage`. Chose 10s over the initially-drafted 30s: every real request observed in testing completed in 1–4s, and this fetch happens up to 3x per bill across ~1,900 bills, so a longer timeout compounds fast if a hang recurs.
3. Fixed a `black` formatting failure caught by CI on the first push.

Posted both changes as a reply on the PR and an update comment on issue #1386. CI (`lint`) is green as of the latest push.

---

## GU

**Status:** 🔍 Scraper bug identified — no issue or PR filed yet

**Finding (2026-07-02):**
The GU scraper reports "bill: 831" in its summary output, but the repo correctly contains only **277 bills** (B1-38 through B277-38 for the 38th Guam Legislature, 2025-2026). The discrepancy is not a data gap — it's a scraper bug.

**Scraper summary output:**
```
gu (scrape)
  bills: {}
bills scrape:
  duration:  0:00:01.658876
  objects:
    bill: 831
jurisdiction scrape:
  objects:
    jurisdiction: 1
    organization: 1
Found 833 JSON files in _working/_data/gu
```

**Root cause:** The scraper saves each bill ~3 times per run with different UUIDs. 277 unique bills × ~3 saves = 831 JSON files. The format action deduplicates by bill identifier when writing to the repo, so no duplicate or missing data results. But the scraper is making ~3x unnecessary HTTP requests and generating ~3x the file I/O on every run.

**Confirmed by:**
- Downloading the nightly release tarball: 831 bill files, 277 unique identifiers, number range B1-38 to B277-38
- Repo tree: 277 bill directories, all `B{n}-38`, no gaps

**Impact:** No data loss. Scraper is slower than it needs to be and wastes GitHub Actions minutes. Worth filing an upstream issue once root cause in the GU scraper is identified (likely a nested loop or duplicate iteration over the bill list).

**Next steps:**
- Look at the GU OpenStates scraper to identify where the duplicate saves originate
- File an issue with the duplicate-save analysis

---

## HI

**Issue [#1383](https://github.com/openstates/issues/issues/1383)** — Cloudflare WAF blocking scraper — KeyError: 'Report Title' on every bill
**Status:** ✅ Closed by maintainer

**Maintainer message (showerst):**

> Yes, this is a known issue. Because bypassing various WAFs is both error prone and may violate various states' TOS (and possibly laws) we don't consider anti-blocking methods to be in scope for the open source part of the project, beyond the basics like setting a user-agent. FYI, you can pass the standard HTTPS_PROXY="" and HTTP_PROXY="" env vars to your scrape to use a proxy.

**Notes:**
Self-hosted runner confirmed working 2026-07-02: **6,640 bills + 8,895 vote events in 31 minutes**. Cloudflare WAF only blocks GitHub-hosted IPs — home network goes through fine. HI is now running on self-hosted runner going forward.

---

## ID

**Status:** 🔍 Data gap identified — no issue or PR filed yet

**Finding (2026-07-02):**
The govbot-data `id-legislation` repo has **790 bills from the 2025 session** and only **1 bill from the 2026 session** (HCR 020). Idaho holds annual sessions; the 68th Legislature's 2nd Regular Session (2026) ran January–April 2026 and would have had hundreds of bills.

**Scraper log (2026-07-01 run):**
```
11:28:22 WARNING openstates: no session provided, using active sessions: {'2026'}
11:28:22 INFO scrapelib: GET - 'https://legislature.idaho.gov/sessioninfo/2026/legislation/topicind/'
11:28:22 INFO scrapelib: GET - 'https://legislature.idaho.gov/sessioninfo/2026/legislation/minidata/'
11:28:22 INFO scrapelib: GET - 'https://legislature.idaho.gov/sessioninfo/2026/legislation/minidata/'
11:28:22 INFO scrapelib: GET - 'https://legislature.idaho.gov/sessioninfo/2026/legislation/HCR020/'
11:28:22 INFO openstates: save bill HCR 020 in 2026 as bill_f7ace9ec-753f-11f1-8da8-26f3860f2b81.json

id (scrape)
  bills: {}
bills scrape:
  duration:  0:00:00.020626
  objects:
    bill: 1
Found 5 JSON files in _working/_data/id
```

**Root cause (likely):** Same pattern as UT. The scraper hits the correct `minidata/` endpoint but the endpoint only returns bills still in an "active/pending" state. For a completed session, nearly all bills are signed or dead — only HCR 020 remains in whatever state the endpoint surfaces. The scraper never gets the full bill list for the concluded session.

**Full repo state:**
| Session | Bills in repo | Expected |
|---|---|---|
| 68th Leg., 1st Regular Session (2025) | 790 | ~790 ✅ |
| 68th Leg., 2nd Regular Session (2026) | 1 | hundreds ❌ |

**Next steps:**
- Look at the ID OpenStates scraper to understand what `minidata/` returns for completed vs active sessions
- Determine if there's a separate endpoint or parameter to fetch the full bill list regardless of status
- This is likely the same underlying bug as UT — worth filing a single issue covering both states if the scraper logic is similar

---

## IN

**Status:** 🔍 Data gap identified — no issue or PR filed yet

**Finding (2026-07-02):**
The govbot-data `in-legislation` repo has only **40 bills** for the 2026 session. Two specific gaps:

1. **HB 1001–1010 are missing** — we have HB 1011 through HB 1047, skipping the first 10 House Bills entirely
2. **Zero Senate Bills** — we have no SB entries at all; only House Bills, 2 House Resolutions, and 1 Senate Concurrent Resolution

**Scraper summary output:**
```
11:26:57 INFO openstates: Api GET: 'https://api.iga.in.gov/2026/bills/sc0001/actions', ...
11:26:57 INFO openstates: save bill SCR 1 in 2026 as bill_c4d0de84-753f-11f1-9416-1219a0dd4075.json

in (scrape)
  bills: {}
bills scrape:
  duration:  0:00:03.788876
  objects:
    bill: 40
    vote_event: 3
jurisdiction scrape:
  objects:
    jurisdiction: 1
    organization: 3
Found 47 JSON files in _working/_data/in
```

The scraper hits `api.iga.in.gov/2026/bills` (Indiana's official API, requires `INDIANA_API_KEY`). Likely causes: API pagination not being walked fully, or Senate and House bills served from separate endpoints that the scraper isn't hitting.

**Full repo state:**
| Session | Bills in repo | Notes |
|---|---|---|
| 2026 Regular Session | 40 | HB 1011–1047, HR 1–2, SCR 1 — no SBs, missing HB 1001–1010 |

**Next steps:**
- Look at the Indiana OpenStates scraper to see how it handles pagination and whether it makes separate calls for Senate bills
- Check `api.iga.in.gov/2026/bills` response structure to confirm if it's paginated and/or House-only

---

## MP

**Status:** 🔍 Scraper bug identified — no issue or PR filed yet

**Finding (2026-07-02):**
The MP scraper crashes on every run, on the same bill every time: **HCommRes 24-6** (`cnmileg.net/leg_sts.asp?legID=20113&secID=1`). The CNMI legislature website has this bill with an empty title field. OpenStates OCD validation requires `title` to have `minLength: 1`, so the scraper crashes before saving it.

**Scraper log (attempt 1 — same failure on all 3 retries):**
```
10:30:08 INFO openstates: GET https://cnmileg.net/leg_sts.asp?legID=20113&secID=1
10:30:08 INFO openstates: save bill HCommRes 24-6 in 24 as bill_ff8ae526-7600-11f1-a843-4eaff7b1e704.json
Traceback (most recent call last):
  ...
openstates.exceptions.ScrapeValueError: validation of Bill ff8ae526-7600-11f1-a843-4eaff7b1e704 failed:
    '' is too short

Failed validating 'minLength' in schema['properties']['title']:
    {'minLength': 1, 'type': 'string'}

On instance['title']:
    ''
⚠️ scrape attempt 1 failed; sleeping 20s...
```
All 3 retry attempts crash on the exact same bill (`legID=20113`, HCommRes 24-6).

**Not rate limiting** — the crash is deterministic. Timing is consistent (~20s per attempt) and the failure hits the exact same bill each time. HCommRes 24-6 genuinely has no title on the CNMI website.

**Proposed fix:** In the MP scraper, add a fallback when the title field is empty — either use the bill identifier as a placeholder (`title = identifier`) or skip the bill with a warning. Either approach unblocks the scraper for all other bills.

**Impact:** The scraper falls back to the previous nightly artifact (139 files = 135ish bills that were scraped before the crash). All bills introduced after HCommRes 24-6 in the iteration order are also missing.

**Next steps:**
- Look at the MP OpenStates scraper to find where the title is fetched from `cnmileg.net`
- Add a guard: if title is empty, fall back to identifier or log a warning and skip
- File an issue / PR

---

## LA

**Issue [#1379](https://github.com/openstates/issues/issues/1379)** — Bill search only returning ~7 of 525 bills — abbreviation and pattern issues
**Status:** 🔄 Open — no maintainer response yet

**PR [#5716](https://github.com/openstates/openstates-scrapers/pull/5716)** — LA action table variable column count
**Status:** ✅ Merged 2026-07-01

**Notes:**
\_

---

## NM

**Issue [#1381](https://github.com/openstates/issues/issues/1381)** — Zero bills scraped for 2026 session — FTP regex mismatch in `_init_mdb`
**Status:** ✅ Closed by maintainer — PR offered, waiting on re-open/response

**Maintainer message (showerst):**

> This is incorrect; see https://github.com/openstates/issues/issues/1384

**Our message sent 2026-07-02:**

hey @showerst ◡̈

First I want to say thank you so very much for being responsive to me. For context, I am a science teacher that works on this project (https://github.com/chihacknight/govbot) on the side, when I have time. Summer is here and I have time now. And yes, I rely heavily on Claude — especially when things get over my skill level.

Second, I want to say thank you so very very much to all of you from the bottom of my heart for creating and maintaining these scrapers. 🩷❤️🧡💛💚🩵💙💜

For every PR I enter I spend a lot of time trying to make sure that I am requesting the correct code. Some of the problems have been more complicated, and I tried to find the root cause and enter an issue, but am definitely wrong, and please push back.

I looked deeper into each of these 2 (CT & NM) issues and have more clarification. I believe that one of our biggest issues overall is running the scrapers through GitHub Actions. We don't have servers — I am a 1-person team working on the back-end of this data and do not have the compute capacity to run this at home. I met with my teammate last night to discuss options about running a local server.

For NM — here you are right, and I'm sorry for the noise. The scrapelib/FTP diagnosis was wrong.

I ran the scraper today to test a backfill (`LegInfo26.zip` has been on the server since April 29) and got a more specific error:

```
INFO scrapelib: GET - 'ftp://www.nmlegis.gov/other/'
ValueError: ftp://www.nmlegis.gov/other/ contains no matching files.
```

So scrapelib does make the FTP request — the problem is that the directory listing it gets back doesn't match the regex in `_init_mdb` looking for `LegInfo26.zip`. When tested directly with `urllib.request.urlopen()` the listing matches fine, so something in scrapelib's response wrapping changes the format slightly.

Just wanted to correct my original diagnosis and share what we're actually seeing. I also noticed you mentioned you'd be open to merging a fix that replaces `self.get(ftp://)` with `urllib.request.urlopen()` as it looks cleaner — I think this fix might solve NM, since the regex would then get the listing in the same format as when we tested with urllib directly. Happy to submit a PR if that would be helpful.

*As a side note I think the problem with CT is Azure IP blocking. I have a few states I am switching to run from my laptop.*

Thank you again from the bottom of my heart for maintaining these scrapers. 🩷

**Next step:** Waiting for maintainer to re-open issue and respond. Ready to submit PR replacing `self.get(ftp://)` with `urllib.request.urlopen()` in `_init_mdb`.

---

## OK

**Issue [#1378](https://github.com/openstates/issues/issues/1378)** — Session list (PROD) suffix not stripped
**Status:** ✅ Closed 2026-07-01

**PR [#5718](https://github.com/openstates/openstates-scrapers/pull/5718)** — Strip (PROD) suffix from session list
**Status:** ✅ Merged 2026-07-01

**Notes:**
\_

---

## UT

**Status:** 🔍 Data gap identified — no issue or PR filed yet

**Finding (2026-07-02):**
The govbot-data `ut-legislation` repo has only **3 bills** for the 2026 General Session (HB 11, HB 12, HB 13). The Utah Legislature's own bill list at `le.utah.gov/billlist.jsp?session=2026GS` shows approximately **510+ House Bills** for the same session — which ran January through mid-March 2026 and has fully concluded.

**Scraper log (2026-07-01 run):**
```
11:17:22 WARNING openstates: no session provided, using active sessions: {'2026', '2025S2'}
11:17:22 INFO scrapelib: GET - 'https://le.utah.gov/billlist.jsp?session=2026GS'
11:17:22 INFO scrapelib: GET - 'https://le.utah.gov/~2026/bills/static/HB0011.html'
11:17:22 INFO scrapelib: GET - 'https://le.utah.gov/data/2026GS/HB0011.json?_=1782904642410'
...
11:17:22 INFO openstates: save bill SJR 201 in 2025S2 as bill_6e9639b6-753e-11f1-9384-0e40324a0af7.json

ut (scrape)
  bills: {}
bills scrape:
  duration:  0:00:00.547365
  objects:
    bill: 8
    vote_event: 16
Found 28 JSON files in _working/_data/ut
```

**Corrected root cause:** The session-check automation IS including `2026GS` in active sessions and the scraper IS hitting `le.utah.gov/billlist.jsp?session=2026GS`. The 8 total bills break down as ~3 from 2026GS (HB0011, HB0012, HB0013) + 5 from 2025S2. The scraper fetches the bill list page but only returns 3 bills for a session that has 510+. This is an **OpenStates scraper bug** — the UT scraper is not returning the full bill list for the completed 2026GS session. Likely cause: the bill list page loads dynamically and the scraper stops after finding bills it already knows about, or the completed session's bill list is rendered differently.

**Full repo state:**
| Session | Bills in repo | Expected |
|---|---|---|
| 2025S1 (First Special Session) | 18 | ~18 ✅ |
| 2025S2 (Second Special Session) | 5 | ~5 ✅ |
| 2026 (General Session, Jan–Mar 2026) | 3 | ~500+ ❌ |

**Why this won't self-heal:** The scraper runs daily and consistently returns only 3 bills for 2026GS. The bill list page is reachable but the scraper isn't extracting the full list. Without a fix to the scraper, the 3-bill state is permanent.

**Next steps:**
- Look at the UT OpenStates scraper to understand how it parses `billlist.jsp` for completed sessions
- Determine if it uses an incremental approach that stops early, or if the page structure differs for ended sessions
- File an issue with this analysis — this is a clear OpenStates scraper bug
- Run a manual backfill once the scraper is fixed to recover the ~510+ missing bills

---

## VA

**Issue [#1377](https://github.com/openstates/issues/issues/1377)** — csv_bills scraper hardcoded session ID ignores --session argument
**Status:** 🔄 Still open as of 2026-07-13 despite PR #5717 merging — nobody closed the issue, needs a manual close

**PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717)** — Fix csv_bills hardcoded session ID
**Status:** ✅ Merged 2026-07-01

---

**Issue [#1385](https://github.com/openstates/issues/issues/1385)** — csv_bills crashes with `KeyError: ' '` on 2026 regular session HISTORY.CSV
**Status:** 🔄 Still open as of 2026-07-13 — but likely fixed by someone else's PR, see below

**PR [#5723](https://github.com/openstates/openstates-scrapers/pull/5723)** — Skip history rows with unknown chamber code in csv_bills
**Status:** ❌ Closed 2026-07-06, not merged — superseded

**Maintainer message (showerst, 2026-07-06):**

> There's [another PR](https://github.com/openstates/openstates-scrapers/pull/5725) addressing this, so closing this. FYI we have a default chamber 'legislature' that can be used here, but in this case...

**What happened:** Another contributor filed **PR [#5725](https://github.com/openstates/openstates-scrapers/pull/5725)** ("VA Bill Actions and Statuses Missing fix") which covers the same `KeyError` — merged 2026-07-08. showerst preferred their fallback (`chamber = "legislature"`) over ours and closed #5723 in favor of it.

**Notes:**
`HISTORY.CSV` for session `20261` has at least one row where `history_description[0]` is a space instead of a chamber code (`H`/`S`/`G`/`C`), causing a `KeyError` crash mid-scrape. Our fix added a guard to skip those rows; the merged fix (#5725) instead defaults to `chamber = "legislature"`. **Next step:** verify #5725 actually resolves the crash with a fresh VA scrape, then close #1385 and #1377 (both technically fixed, neither closed).

---

## WY

**Status:** 🔍 Data gap identified — no issue or PR filed yet

**Finding (2026-07-02):**
Wyoming's 2026 budget session is legitimately small (~20 days, limited legislation), and the scraper runs cleanly. However, 3 bill numbers are missing from what the API returns:

| Missing | Likely significance |
|---|---|
| HB0001 | Almost certainly the budget/appropriations bill — the primary purpose of Wyoming's even-year budget session |
| SF0001 | Unknown — possibly a companion appropriations bill |
| SF0002 | Unknown |

**Scraper summary output:**
```
wy (scrape)
  bills: {}
bills scrape:
  duration:  0:00:00.052901
  objects:
    bill: 23
jurisdiction scrape:
  objects:
    jurisdiction: 1
    organization: 3
Found 27 JSON files in _working/_data/wy
```

**What the scraper does:** Single API call to `lsoservice.wyoleg.gov/api/BillInformation?$filter=Year eq 2026&$orderby=BillNum` — no pagination needed for this session size. The API returns 23 bills; HB0001, SF0001, and SF0002 are simply not in the response.

**Full repo state:**
| Session | Bills in repo | Notes |
|---|---|---|
| 2025 Regular Session | 556 | Looks complete |
| 2026 Budget Session | 23 | Missing HB0001, SF0001, SF0002 |

**Confirmed by comparing 2025 vs 2026 sessions:**
- In 2025 (regular session): HB0001 through HB0341, SF0001 through SF0198 — full sequences, no gaps
- In 2026 (budget session): starts at HB0002, SF0003 — HB0001, SF0001, SF0002 are absent from the API response entirely

**Root cause confirmed (2026-07-02):**
All three missing bills are the budget bills — signed into law and marked `enrolled` or `inactive` by the time the scraper runs. The scraper's API call (`$filter=Year eq 2026&$orderby=BillNum`) silently excludes them, likely filtering on active/pending status only.

| Bill | Title | Status | Signed |
|---|---|---|---|
| HB0001 | General government appropriations-2 | inactive | — |
| SF0001 | General government appropriations | enrolled | 3/6/2026 |
| SF0002 | Legislative budget | enrolled | 3/3/2026 |

Wyoming's budget session exists specifically to pass these three bills. The scraper is missing the entire legislative output of the session.

**Next steps:**
- Investigate the Wyoming OpenStates scraper to see what status filter is applied to the API call
- Determine if `enrolled`/`inactive` bills need to be fetched via a separate API call or parameter
- File an OpenStates issue with this analysis
- Note: Wyoming is used as a fast test runner — this gap means test runs have never validated handling of Wyoming's most important bills

---

## WV

**Issue [#1380](https://github.com/openstates/issues/issues/1380)** — Bill listing XPath broken after site redesign — zero bills scraped
**Status:** 🔄 Open

**PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719)** — Update bill listing XPath after site redesign
**Status:** ❌ Closed 2026-07-08, not merged — our diagnosis and fix were wrong

**Maintainer message (jessemortenson, 2026-07-02):**

> Hi @tamara-builds Can you share the summary output from one of the non-working (missing "regular" bills) scrape that you did?
>
> We've been running the WV bills scraper successfully all week and it consistently returns a count of `bill: 2975` in the summary output. That matches our automated check of how many bills there _should_ be, and the output includes a lot of "regular" HB/SB bills. So I'm unable to verify the problem you're reporting so far, and that makes me curious about what's going on. Any additional details you can provide on what you're seeing are appreciated!

**Our response sent 2026-07-02:**

> Hey @jessemortenson ◡̈
>
> Thanks for checking. Here's our summary output from our most recent run:
>
> ```
> wv (scrape)
>   bills: {}
> bills scrape:
>   duration:  0:00:00.477218
>   objects:
>     bill: 39
>     vote_event: 2
> jurisdiction scrape:
>   duration:  0:00:00.005365
>   objects:
>     jurisdiction: 1
>     organization: 3
> Found 45 JSON files in _working/_data/wv
> 🧹 Cleaning _data/wv/ directory...
> ✅ 45 scraped files in /home/runner/work/wv-legislation/wv-legislation/_data/wv/
> ```
>
> We're getting 39 bills vs your 2975 — and looking at our logs, the last bill saved was HJR 16 (a House Joint Resolution). We might be only picking up resolutions, not regular HB/SB bills.
>
> We're running inside the `openstates/scrapers:latest` Docker image. Is it possible there's a version difference between what we're pulling and what you're running locally?

**Maintainer reply (jessemortenson, 2026-07-08) — rejects our PR:**

> Thanks for reporting back. That's very strange that you're getting such a small number.
>
> What summary output are you getting when you run it with the changes in this PR? does it get 2975 bills with that change in place for you?
>
> The docker image should be the same, our environment is using the same docker image (though pushed to an internal repository, still should be identical).
>
> One possible difference: we are running WV scrapers through a proxy called tinyproxy, but it's just running on a GCP virtual machine, nothing fancy about it.
>
> ---
>
> I looked a little deeper into this, and your PR here actually reverts a change I made intentionally 2 weeks ago: https://github.com/openstates/openstates-scrapers/pull/5703/changes
>
> The code in this PR (which was status quo before the change) actually gets an inaccurate list of bill links. The difference between the two selectors for the Senate version is the following (there is no diff for the House version):
>
> `["Incorporated into Com. Sub. for SB 251", "Incorporated into Com. Sub. for SB 281", "Incorporated into Com. Sub. for SB 374", "Incorporated into Com. Sub. for SB 309", "Incorporated into Com. Sub. for SB 256"]`
>
> Consequently, I am not going to merge this.

**Status:** ❌ Our fix was wrong — needs fresh root-cause work

**Notes:**
Our PR unknowingly reverted jessemortenson's own intentional selector change from PR #5703 (merged ~2 weeks earlier), which fixed a *different* accuracy problem (missing "Incorporated into Com. Sub. for SBxxx" resolution links). Reverting it would have made WV's data worse, not better. The real 39-vs-2975 bill discrepancy is still completely unexplained — the one lead we have is that OpenStates runs WV through `tinyproxy` on a GCP VM, which we don't. Worth testing: does running WV without the reverted change, but through a similar proxy setup (or just checking whether our runner's IP/network path resembles a block), change the count? Do not resubmit a variant of #5719 without a new theory — the xpath itself is not the bug.

---

## Biennium end_date (DC · MI · NC · PA)

**Issue [#1375](https://github.com/openstates/issues/issues/1375)** — Session end_date off by one year for DC, MI, NC, PA
**Status:** ✅ Closed 2026-07-01

**PR [#5712](https://github.com/openstates/openstates-scrapers/pull/5712)** — Correct 2025-2026 session end_date for DC, MI, NC, PA
**Status:** ✅ Merged 2026-07-01

**Notes:**
\_

---

## Already resolved (no action needed)

| State | Issue/PR                                                             | Description                  | Status                  |
| ----- | -------------------------------------------------------------------- | ---------------------------- | ----------------------- |
| DC    | [#1372](https://github.com/openstates/issues/issues/1372)            | Non-PDF attachment crash     | ✅ Closed               |
| DC    | [#1374](https://github.com/openstates/issues/issues/1374)            | PDF query string crash       | ✅ Closed               |
| DC    | [#5706](https://github.com/openstates/openstates-scrapers/pull/5706) | DC mimetype None             | ✅ Merged               |
| DC    | [#5711](https://github.com/openstates/openstates-scrapers/pull/5711) | DC PDF query string mimetype | ✅ Merged               |
| LA    | [#1376](https://github.com/openstates/issues/issues/1376)            | Action table column count    | ✅ Resolved by PR #5716 |
| NJ    | [#1373](https://github.com/openstates/issues/issues/1373)            | Vote bill_id KeyError        | ✅ Closed               |
| NJ    | [#5707](https://github.com/openstates/openstates-scrapers/pull/5707) | NJ vote bill_id guard        | ✅ Merged               |
| OK    | [#1378](https://github.com/openstates/issues/issues/1378)            | PROD suffix not stripped     | ✅ Closed               |
