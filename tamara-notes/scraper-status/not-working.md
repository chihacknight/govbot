# Scraper Status — states with a problem (not currently working)

Moved into `tamara-notes/scraper-status/` alongside `working-in-session.md` and
`working-out-of-session.md` (2026-07-24) — those two cover the states that *are* working,
split by whether the state is currently in session. This doc is the third bucket: anything
not confirmed `✅` in the 2026-07-21 audit, in-session or out, all in one place with a
session-status column since "not working" is the thing that matters here, not session
timing.

Relationship to other docs:
- **`tamara-notes/openstates-responses.md`** stays separate — it's specifically for drafting/tracking
  communications with OpenStates maintainers (issue/PR threads). Cross-referenced from here, not merged.
- **`actions/scrape/docs/error-tracking.md`** and **`actions/scrape/docs/scraper-health.md`** are the
  historical snapshots (2026-07-02 through 2026-07-14) this doc is built from. Superseded by this doc
  going forward — don't update them further; update here instead.

Last audited: **2026-07-21** (full 56-state pass — see `actions/pipeline-manager/` background audit
this session). States with a current problem are listed first, grouped by what kind of action they
need. Healthy states are a compact table at the bottom.

## Session status at a glance (22 states)

In/out of session per LegiScan's `session-calendar-2026.md` (as of 2026-07-13, cross-checked
2026-07-24 in `session-dates-comparison.md`).

| State | In/Out of Session | Status |
|---|---|---|
| AR | Out | Looked fine 07-21 (6 files, matches 2 genuinely-live 2026S1 bills) — not yet re-marked `✅` in the newer per-state table, borderline "working" but keeping it here until confirmed. |
| AZ | Out | ✅ Resolved 2026-07-24 — real cause was `--fastmode` cache poisoning, not the cookie bug. See dedicated writeup below and PR [#5742](https://github.com/openstates/openstates-scrapers/pull/5742). |
| CT | Out | ✅ Confirmed clean 2026-07-24 (re-verified via identifier check: 1,283 bill files, 1,283 distinct, zero dupes) — the 07-21 clear+rescrape held. Ready to promote to `working-out-of-session.md`. |
| FL | Out | 🔧 Scraper fixes done, awaiting upstream merge. All 3 root causes (bot detection, silent timeout hangs, single-bill failures crashing the whole session) fixed and verified live in PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724), pushed + commented 2026-07-26. `BillDetail` itself still deliberately not covered (open question). Separately: shrink-guard duplicate-bloat bug found 07-25 already resolved (fix merged to govbot `main`, FL's workflow auto-picks it up). Re-verification run in progress ([30185187734](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/30185187734)) combining both fixes. |
| GA | Out | `N2_CONNECTIVITY` — no prior history of this, looks transient. |
| MA | **In** | 🔄 Had the shrink-guard duplicate-bloat bug (50,183 files, only 11,123 distinct — worst ratio found, ~4.5x). Fix merged to `main` 2026-07-25; MA's own live-test run (self-hosted, ~11hr typical) was still finishing as of the merge — confirm it landed a clean `"🕷️ Scrape data for ma"` commit. |
| MI | Out | 🔄 Fix in progress 2026-07-24 (`fix/mi-digicert-intermediate`, `tamara-builds/openstates-scrapers` fork) — bundled the missing DigiCert intermediate into the Docker image's CA store. Verified directly: curl/Python `requests` now get clean `HTTP 200` from `legislature.mi.gov` with real cert verification. Live local scrape test in progress, 93+ bills saved and climbing as of last check (previously 0, always). See `pending-branches.md`. |
| MN | Out | `N4_DNS_FAILURE`, but got a substantial partial haul (5,314 files) — likely transient, hit late in the run. |
| MO | Out | ✅ Confirmed clean 2026-07-25 — shrink-guard identifier-check fix (merged to `main`) landed 3,158 real bills, replacing a 22,015-file bloated baseline. A later run correctly held back on a small genuine drop (guard working as designed). |
| MP | Out | `S6_VALIDATION` — known blank-title OCD crash, fix identified, not yet filed upstream. |
| MT | Out | ✅ Confirmed clean 2026-07-25 — the "1-2% duplication, cause still open" note was wrong; a full census found 2,529 of 4,495 real bills had a stale duplicate (56%, fully explaining the gap). Shrink-guard identifier-check fix (merged to `main`) landed 4,495 real bills twice now, replacing a 37,555-file bloated baseline. |
| NE | Out | `H3_RATE_LIMITED`, likely shared-proxy congestion rather than a new site-specific block; not yet retried on genuine self-hosted. |
| NH | Out | `H3_RATE_LIMITED` — turns out to be two separate issues, not one (found 2026-07-24, see full writeup below and `pending-branches.md`): (1) the site chokes under our unthrottled `--fastmode` request burst even at 2:27am ET, well outside the known block window — fix merged (`fix/nh-skip-fastmode`, PR #95, live on `main`); (2) a same-day test squarely inside the 6am-9pm ET window failed instantly on the very first request — a harder, different failure than (1), consistent with the original block-window theory after all. **The re-test for (1) happens automatically tonight** — NH's cron (`0 4 * * *` UTC = midnight ET) is outside the block window and its workflow already points at `@main`, so no manual dispatch needed. That run will *not* include the fork-side `SCRAPELIB_RPM=20` extra (`fix/nh-rate-limit`, never deployed to NH's actual workflow) — check in the morning whether dropping `--fastmode` alone was enough. **Update 2026-07-26: the 6am-9pm ET block window itself is still real** (confirmed directly from NH's own site logs, not just inferred from run timing) — nothing here changes that. What changed is a *different* run's failure label: a manually-dispatched run at 22:25 ET (`run 30184528088`, outside the block window) got tagged `H4_SERVER_DOWN`, which looked like a new instant-fail mode outside the window. Turned out to be a **classifier false positive**: the actual error on all 3 retry attempts was a plain `ScrapeError: no objects returned`, misclassified because `scrape.sh`'s failure-type grep did a bare substring match on `"503"`, which coincidentally appears inside NH's cache-busting query param (`?x=<timestamp>`) on every logged request URL. Fixed on `fix/commit-summary-identifier-aware` (anchored the `503`/`429` regexes to require non-digit boundaries). With NH's 2026 session already over (ended 2026-06-04/06-30, see `session-dates-comparison.md`), "no objects returned" outside the block window is exactly the expected `S1_OUT_OF_SESSION` behavior, not evidence of anything new — the mislabel just made it look scarier than it was. |
| NM | Out | Intermittent FTP server issue (confirmed via direct `curl` testing) — not a permanent dead end, just unlucky timing on the last run. |
| NV | Out | Looked fine 07-21 (64 files, matches biennial no-regular-session-until-2027 expectation) — not yet re-marked `✅`, keeping here until confirmed. Separate known ~1,000+ bill backfill gap from the 2025 session. |
| OH | **In** | ✅ Confirmed clean 2026-07-24 (re-verified via identifier check: 2,452 bill files, 2,452 distinct, zero dupes) — the 07-21 clear+rescrape held. Ready to promote to `working-in-session.md`. |
| OR | Out | Looked fine 07-21 (308 files, consistent with 07-02 baseline) — not yet re-marked `✅`, keeping here until confirmed. |
| PA | **In** | ✅ Confirmed clean 2026-07-24 (re-verified via identifier check: 4,857 bill files, 4,857 distinct, zero dupes) — the 07-21 clear+rescrape held. Ready to promote to `working-in-session.md`. |
| PR | Out | ✅ Confirmed clean 2026-07-25 — shrink-guard identifier-check fix (merged to `main`) landed cleanly, replacing a 23,866-file bloated baseline (only 5,115 were real). |
| USA | **In** | ✅ Confirmed clean 2026-07-25 — shrink-guard identifier-check fix (merged to `main`) landed 17,574ish real bills twice now, replacing a 48,714-file baseline (half was stale duplicates). |
| VI | **In** | Source server itself offline (`billtracking.legvi.org:8082`) — not a code or hosting problem, fails on every path since the site is down. |
| WA | Out | ✅ Confirmed clean 2026-07-25 — was frozen since `2026-07-24T04:06:15Z` (silently reporting "success" on every scheduled run while landing zero new data). Shrink-guard identifier-check fix (merged to `main`) unfroze it, replacing a 6,153-file baseline (only 3,411 were real) with a clean commit. |

**Read before acting on any row below:** a "current problem" today doesn't always mean something is
newly broken — several rows below are long-known issues that just look scary out of context (see the
"Known, no new info" group). Cross-referencing against history is the whole point of this doc.

**"Config: self-hosted?" is NOT the same as "actually ran on self-hosted infrastructure today."**
A state flagged `runner: self-hosted` in `chn-openstates-scrape.yml` still runs on GitHub-hosted +
tinyproxy by *default* — genuine self-hosted execution (a real MacBookPro runner, no proxy) only
happens when a dispatch explicitly sets `use-self-hosted: true`. These are different things and
this doc distinguishes them per-row below (verified via each run's `runner_name`/`runner_group_name`,
not assumed from the config flag). Don't conflate "flagged self-hosted" with "ran self-hosted."

### Hosting-path results, 2026-07-21 — which path actually works for which state

Legend: **1** = successful scrape · **2** = failed (hosting/network-level) · **\*** = the scrape itself
ran fine, but the shrink-guard blocked the commit (a data-duplication issue, not a hosting failure —
see the P1_SHRINKING_OUTPUT states) · **—** = not tested on that path yet.

| State | GitHub-hosted (plain, no proxy) | Tinyproxy | MacBookPro | Notes |
|---|---|---|---|---|
| MI | 2 | 2 | **2** | Fails identically on **every path tested** (3x GitHub-hosted+proxy, 1x genuine MacBookPro with zero proxy) — same `SSLCertVerificationError` every time. Root cause: `legislature.mi.gov` itself doesn't serve its full TLS certificate chain (missing DigiCert intermediate), confirmed via `openssl s_client`. Not a hosting problem at all — belongs with NM/AZ/VI as "fails everywhere," not the proxy-overload group. **Corrected from an earlier wrong entry in this doc that called it fixed.** |
| PA | — | 2 | 1\* | Proxy: tunnel `500`. MacBookPro-5: scrape itself succeeded (4,872 bills, clean), but hit a *second*, unrelated problem — see PA's row below and the P1_SHRINKING_OUTPUT group. Cleared + re-dispatched. |
| NM | — | 2 | 2 | Fails on **both** — confirmed genuine server-side FTP issue, not hosting-related at all. |
| GA | 1 (after retry) | — | — | First try failed (`N2_CONNECTIVITY`), plain retry succeeded. Never self-hosted-flagged. |
| MN | 1 (after retry) | — | — | Same shape as GA — plain retry succeeded. |
| CT | — | \* | 1 | Proxy run got real data but tripped shrink-guard (duplicate cruft). MacBookPro rescrape: clean success, 1,283 unique bills. |
| OH | — | \* | 🔄 in progress | Same as CT — MacBookPro rescrape still running. |
| USA | — | \* | 🔄 in progress | Same pattern — still running. |
| MO | \* | — | 🔄 in progress | Not self-hosted-flagged, so its shrink-guard trip happened on plain GitHub-hosted, not proxy. MacBookPro rescrape (via `use-self-hosted: true` override) still running. |
| MT | \* | — | 1 | Same as MO — MacBookPro rescrape landed clean. |
| PR | \* | — | 1 | Same as MO/MT — MacBookPro rescrape landed clean. |
| FL | — | 2 (`H3_RATE_LIMITED`) | see FL section below | Three distinct failure modes now confirmed — see the dedicated FL writeup under "🔴 States with a current problem." |
| MA | — | 🔄 in progress | — | Currently running through tinyproxy, not yet tried on MacBookPro. |
| AZ | — | 2 | 2 | Fails on **both** as of this 07-21 audit — the identical cross-path failure turned out to be the key clue pointing away from hosting. ✅ Resolved 2026-07-24, see dedicated writeup below (was `--fastmode` cache poisoning, not a cookie/session bug). |
| VI | — | 2 | 2 | Fails on **both** — source server itself is offline, not a hosting problem. |
| NE | — | 2 (partial, `H3_RATE_LIMITED`) | — | Not yet retried on MacBookPro today. |
| WA | 2 (partial, `H3_RATE_LIMITED`) | — | — | Never self-hosted-flagged. |

**The important rows are NM, AZ, and VI** — they fail on every path tested, which is exactly what
tells you the problem isn't hosting at all (upstream server/scraper issue instead). Everything else
above either has a clear working path (MacBookPro, mostly) or just hasn't been tried on the
alternative path yet.

---

## 🔴 States with a current problem (2026-07-21)

### Proxy-overload casualty from this morning's mass dispatch — fixed

This morning's 56-state re-dispatch never set `use-self-hosted: true`, so every self-hosted-flagged
state ran through the shared tinyproxy VM on a GitHub-hosted runner by default instead of a real
self-hosted machine — and that VM choked under ~24 states' simultaneous traffic. PA's morning failure
was specifically this — a broken proxy tunnel, not a site-side or scraper-side problem.
(**MI turned out NOT to belong in this category at all — see below, its failure is unrelated to
hosting entirely. NM also looked like a match at first, same `EOFError` on FTP connect, also
unrelated — see the "Known, no new info" group.**)

| State | Config: self-hosted? | Today's result | What changed |
|---|---|---|---|
| **PA** | ✅ yes | 🔄 two-part story, second part still fixing | This morning's failure: proxy tunnel `OSError: Tunnel connection failed: 500 Unable to connect`. Re-dispatched to MacBookPro-5 — **the scrape itself then succeeded cleanly** (4,872 bills, 9,886 files) but hit a **second, unrelated** problem: PA's already-committed data (26,658 files) turned out to be ~2.0x duplicate cruft (9,738 bill files, only 4,869 unique identifiers, verified via identifier check — same pattern as the P1_SHRINKING_OUTPUT group below), so the shrink-guard correctly refused to overwrite it with the smaller-but-correct fresh scrape. **Caught this because the run summary said "success" with `P1_SHRINKING_OUTPUT` as the failure type — don't trust `gh run list`'s conclusion field alone, always check the actual scrape summary.** Cleared `_data/pa` and re-dispatched with `use-self-hosted: true` (run 29867692944) — should land clean this time. |

### MI — corrected: NOT a hosting/proxy issue, don't assume it's fixed

**Important correction to this doc's own earlier entry.** MI was originally logged here as "fixed via
MacBookPro," based on verifying the run's hosting path (`runner_name: MacBookPro-2`, `USE_PROXY:
false`) and trusting the workflow's "success" conclusion — the same mistake made once already with
NM and PA tonight: **verifying hosting path is not the same as verifying the scrape actually got
data.** Checked all 5 of today's MI runs directly (`Found N JSON files`, exit code, actual traceback)
instead of the top-line conclusion:

| Run | Hosting | Result |
|---|---|---|
| 05:59 | GitHub-hosted + tinyproxy | 0 files, `SSLCertVerificationError` |
| 06:26 (schedule) | GitHub-hosted + tinyproxy | 0 files, `SSLCertVerificationError` |
| 15:41 (morning mass dispatch) | GitHub-hosted + tinyproxy | 0 files, `SSLCertVerificationError` |
| 19:40 (retry, `use-self-hosted: true`) | **MacBookPro-2, no proxy at all** | 0 files, **same `SSLCertVerificationError`** |
| 20:07 (separate retry, no override) | GitHub-hosted + tinyproxy | 0 files, same `SSLCertVerificationError` |

**All 5 failed identically, regardless of hosting path.** Root cause found: `openssl s_client -connect
www.legislature.mi.gov:443` shows the site serves **only its leaf certificate**, not the DigiCert
intermediate (`DigiCert Global G2 TLS RSA SHA256 2020 CA1`) needed to complete the chain — a genuine
server-side TLS misconfiguration on Michigan's own site. Browsers silently work around this (cached
intermediates / AIA fetching); Python's `ssl` module and curl don't, unless that specific intermediate
is already in the local trust store. This is why it fails identically on GitHub-hosted+proxy AND
genuine self-hosted with zero proxy — the missing piece is the container's CA trust store, not the
network path at all. **Self-hosting does nothing for this one.**

Possible fix (not yet implemented): bundle the missing DigiCert intermediate certificate into the
scraper's Docker container CA store as a targeted workaround, since this is a legitimate, publicly-known
CA cert, not a verification bypass. Otherwise this needs an upstream fix in `openstates-scrapers` (or a
report to Michigan's legislature IT) since no amount of infrastructure changes on our end fixes a
server that doesn't send its own full certificate chain.

### FL — three distinct root causes found and fixed, all verified live

Full history and PR/issue thread details live in `openstates-responses.md`'s FL section — this is
the short version for scraper-health tracking.

**Root cause #1 (known since 07-02): `flhouse.gov` bot detection.** Returns HTTP 200 with a
"Request Rejected" HTML body after sustained scraping of the 2026 regular session — `flsenate.gov`
never blocks. Combined with a `list()` anti-pattern in `scrape()` that forced the entire ~8,000-bill
session to materialize before anything was saved, a block partway through meant **zero** bills saved
despite hours of real progress. Fix proposed in PR #5724 back on 07-13.

**Root cause #2 (newly found 07-23): silent hangs, independent of bot detection.** While
investigating why our runs get far fewer bills than the PR maintainer's own test (~1,400–1,900 vs.
our <40), ran a side-by-side test: the real self-hosted scrape (`--fastmode`) alongside a second,
manually-started docker container without `--fastmode`, writing to a separate scratch dir. Fastmode
turned out not to matter — the no-fastmode container hung completely, twice, at different bill
numbers (11, then 172 after a restart), while `flhouse.gov` itself kept responding fine from the host
(`curl` returned 200 in 0.37s during the second hang). Traced to `spatula.URL` defaulting
`timeout=None` — `HouseSearchPage`/`HouseBillPage` in `fl/bills.py` never passed an explicit timeout
on their three `flhouse.gov` request constructions, so a stalled connection waits forever instead of
raising the `ConnectionError`/`Timeout` the scraper's existing retry/backoff logic already knows how
to handle. This explains failures that looked like "just slow" or "stuck" rather than a clean
rejection — the same signature as the very first hang we investigated this session, before we knew
what it was.

**Historical context worth remembering:** two self-hosted runs from 07-13 ([29286687750](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/29286687750)) and
07-15 ([29386003022](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/29386003022)) each had individual attempts that ran clean for 5–7.5 hours before
hitting bot detection, with the longest clean stretches lining up with FL overnight hours
(~12:30am–8am Eastern). Neither actually landed data (both predate the auto-save feature and died to
infra issues — a 12h timeout cap, then a 21h35m "runner lost communication" — before the final commit
ran), but it's a real signal that bot-detection sensitivity may ease overnight — worth testing
deliberately rather than always dispatching during the day.

**Fix pushed 2026-07-23, same PR (#5724):**
1. `allow_partial` opt-in parameter on `scrape()` (off by default) — directly addresses maintainer
   `jessemortenson`'s 07-17 feedback that a blocked run should fail loudly by default, not silently
   report a subset of bills as complete.
2. `timeout=10` added to all three `flhouse.gov` request constructions — fixes root cause #2.
3. A `black` formatting failure caught by CI on the first push, fixed in a follow-up commit.

Posted as a PR reply + an issue #1386 update comment. CI (`lint`) green as of the latest push.
Awaiting maintainer re-review — **don't assume merged**, check PR state before relying on this fix
being live in `openstates/scrapers:latest` (it isn't yet — the docker image is only rebuilt once
upstream merges and cuts a release).

**Root cause #3 (found 2026-07-24, in a real run with both fixes above already deployed): a single
bill's failure was crashing the entire remaining session.** Traced through spatula's actual source
(`_to_items()`/`_fetch_data()` in `pages.py`): spatula only auto-converts `scrapelib.HTTPError` into
its own swallowable `HandledError`; everything else (a `requests.ReadTimeout` after
`patched_get_response`'s own retries are exhausted, or a `spatula.RejectedResponse` after
`HouseSearchPage`'s own `retries=3` are exhausted) propagates raw through spatula's entire recursive
`_to_items()` generator chain (BillList → BillDetail → HouseSearchPage → HouseBillPage →
HouseComVote is all *one* generator) and lands in `_process_bill_list`'s outer except block —
the one meant for session-wide problems, not a single independent bill's blip.

Confirmed twice, live, in two separate failure shapes:
- **2026-07-24 ~13:30 UTC**: bill 66's `flhouse.gov` fetch hit a plain `ReadTimeout` after retries;
  crashed the whole remaining session.
- **2026-07-24 ~16:46 UTC**, in a *later* run already carrying the fix for the above: bill 411 hit
  `flhouse.gov`'s bot-detection page (`spatula.RejectedResponse`, a different exception class the
  first fix didn't cover) after `HouseSearchPage`'s own retries were exhausted — crashed the same
  way. (Auto-save meant this cost far less than it looked: the run had 4 auto-save commits
  totaling 1,035 real files already safely in git history by the time it crashed, the last one just
  ~14 minutes before — only that last window's progress was actually lost.)

**Fix**: a `ResilientFetchPage` mixin in `scrapers/fl/bills.py` that wraps `_fetch_data`, catches
both failure shapes above, and re-raises them as spatula's own `HandledError` — reusing spatula's
existing "nothing left to do with this page, move on" handling instead of inventing a new one.
Applied to the 5 classes that are per-bill, supplementary, and independent of every other bill:
`HouseSearchPage`, `HouseBillPage`, `HouseComVote` (flhouse.gov) and `FloorVote`, `UpperComVote`
(flsenate.gov vote PDFs). Deliberately **not** applied to `BillList`/`BillDetail`/`SubjectPDF` —
those are session-wide or a bill's own core data, where silently swallowing a failure risks a run
looking complete when it isn't; still an open question whether `BillDetail` itself should eventually
get the same treatment (losing a bill's whole record vs. just its votes is a different trade-off).
Verified against the real `spatula` package (not just read-through) with both a positive test
(failure isolated cleanly, sibling bills still flow) and a negative control (reproduces the real
crash without the fix).

**Status as of 2026-07-26: DONE, verified live twice, pushed, PR commented.** Both commits
(`ac85d4156`, `f5666837c`) pushed to `origin/fix/fl-streaming-bills` — PR #5724 auto-updated,
summary comment posted:
https://github.com/openstates/openstates-scrapers/pull/5724#issuecomment-5081701198. Decided
2026-07-24 not to close the PR while iterating — maintainer `jessemortenson` had already said
he wouldn't merge as-is and no approving review existed, so there was no real risk of it
merging out from under this work.

Live verification: [run 30115056537](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/30115056537)
(2026-07-24/25, ~16h) completed successfully with both fixes deployed. Watched it hit bills
818/819/820 consecutively bot-detected and correctly log `SKIPPED BILL:` and continue,
including still capturing bill 820's other data (Senate committee/floor votes) even though its
House data was skipped.

**Still open**: `BillDetail` itself was deliberately never given the same treatment (losing a
bill's whole record vs. just its votes is a different trade-off) — not revisited since. Also,
FL separately hit the shrink-guard duplicate-bloat bug 2026-07-25 (3,123 bill files, only 1,878
distinct) — unrelated to this fix, already resolved (fix merged to govbot `main` 2026-07-25,
FL's workflow already points at `@main` so it picks it up automatically, no action needed).

**Cleanup pending, gated on upstream**: `fl-legislation`'s live workflow still points at the
temporary `ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test` image — now via a proper
config-driven `docker_image` field in `chn-openstates-scrape.yml` (added 2026-07-25, survives
a future `apply.py` template re-sync, unlike the hand-edit it replaced) rather than a fragile
hand-edit. Revert to the config default once PR #5724 merges and `openstates/scrapers:latest`
is rebuilt upstream with the fix.

A companion, generic (not FL-specific) change in this repo's `actions/scrape/scrape.sh` +
`actions/scrape/action.yml` (merged to `main`) adds a `SKIPPED BILL:` log-line convention: any
scraper that logs a line with that exact prefix gets it surfaced as a distinct "🔁 Skipped, Will
Retry Next Run (N)" section in the GitHub Actions summary, separate from the generic error bucket —
since this scrape runs nightly, a skipped bill is expected to get picked up again and shouldn't read
as an unresolved fault. Same session also shipped a broader, all-states log-folding feature
(`actions/scrape/fold_scrape_log.awk` + related) that collapses routine scrape-log noise into
GitHub Actions groups — see `tamara-notes/` or ask about it separately, not FL-specific.

A separate config fix landed the same session: FL's (and MA's) *scheduled* runs were landing
on GitHub-hosted infrastructure instead of self-hosted regardless of the `runner:
self-hosted` config flag — confirmed via `runner_group_name` on two real cancelled runs
2026-07-25, one killed at exactly the GitHub-hosted 6h00m hard cap. Fixed with a new
`force_self_hosted` locale config field, applied live via `apply.py`.

### AZ — ✅ resolved 2026-07-24, real root cause found (not the long-standing cookie theory)

AZ had never produced a single bill. Original diagnosis was a Sucuri WAF blocking the
`setsession.php` POST (issue [#1382](https://github.com/openstates/issues/issues/1382)). That was
disproven 2026-07-14 — genuine self-hosting (non-Azure IP) still hit the identical
`AssertionError: Session ID not in bill list`. A cookie-merge fix went up as PR
[#5722](https://github.com/openstates/openstates-scrapers/pull/5722) anyway and merged
2026-07-15 ("more robust at no real cost," maintainer could never reproduce the failure) — but
**it didn't actually fix anything**. The 2026-07-24 Hosting Path History audit (this doc's table
above, row 83, plus `docs/src/state-status-reference.md`) still showed the identical failure on
every path tried (Tinyproxy, MacBookPro, plain GitHub-hosted) — that cross-path symmetry is what
prompted a fresh look instead of trusting the cookie diagnosis.

**Real root cause**: `az/bills.py`'s `scrape()` does GET `/bills/` → POST `setsession.php` (sets
the session server-side) → GET `/bills/` again, asserting the session now shows as `selected`.
`actions/scrape/scrape.sh` always passes `--fastmode` to every scraper invocation. Per OpenStates'
own CLI help text, that flag's actual purpose is `"use cache and turn off throttling"` — a local
dev/iteration convenience flag, never meant for production scraping. It sets
`cache_write_only = False` (`openstates/scrape/base.py`), which lets scrapelib's `FileCache` serve
GET responses from disk — keyed purely on URL, ignoring cookies/headers/method entirely. So the
second GET to `bill_list_url` was silently served the *first* GET's cached response, from before
the session was ever set. 100% reproducible on any network, since it's a caching bug, not a
network one — explaining both the identical cross-path failure and why the maintainer could never
reproduce it locally (their repro command omitted `--fastmode`).

Confirmed by direct reproduction: a fresh, empty `_cache/` dir inside the real
`openstates/scrapers:latest` image reproduced the failure immediately; the cached page had zero
`<option selected>` elements at all. A plain `requests`/`curl` version of the same 3-step flow,
with no fastmode-style cache, worked correctly every time.

**Fix**: `scrapers/az/bills.py` now temporarily forces a live fetch (bypasses the cache read) for
just that one post-session GET. Verified locally twice against a custom test image (2,190 bills,
3,462 vote events both times, clean exit code), then confirmed live in production CI through
Tinyproxy — first successful AZ scrape ever:
[run 30109209415](https://github.com/govbot-openstates-scrapers/az-legislation/actions/runs/30109209415),
same 2,190 bills / 3,462 vote events, committed to `main`.

**Status**: PR [#5742](https://github.com/openstates/openstates-scrapers/pull/5742) open upstream
(references and supersedes #5722 — see PR body for the full story). `az-legislation`'s live
workflow is temporarily pointed at a custom test image
(`ghcr.io/tamara-builds/openstates-scrapers:az-fix-test`) so AZ keeps producing real data nightly
while waiting on the merge, rather than sitting broken. Full revert-once-merged checklist tracked
in `tamara-notes/scraper-status/upstream-pr-todo.md` — check that doc before assuming this is
fully closed out.

**General lesson worth remembering for other states**: any scraper that does
"GET → POST to mutate server-side state → GET the same URL again expecting the change reflected"
is vulnerable to this same `--fastmode` cache-poisoning pattern. AZ is the only confirmed case so
far, but nothing else has been specifically checked. See
`tamara-notes/scraper-debugging-onboarding.md` for the generalized writeup.

### Not self-hosted, not proxy-related — genuinely new, still needs a look

| State | Config: self-hosted? | Today's result | What changed |
|---|---|---|---|
| **GA** | no | `N2_CONNECTIVITY`, 4 files | Was healthy 07-02 (5,480+ bills). Root cause found 2026-07-24: `scrape_subjects()`'s `get_token()` call has no timeout and isn't inside its own try/except, so a single connection hiccup on that unrelated REST auth endpoint kills the entire scrape over non-critical subject-tag metadata. Fix drafted on `fix/ga-subjects-resilience` (openstates-scrapers fork), local docker test in progress — see `pending-branches.md`. |

### Known, no new info — already tracked, still open upstream or by design

| State | Config: self-hosted? | Today's result | Context |
|---|---|---|---|
| **MP** | no | `S6_VALIDATION`, 139 files | ✅ Fixed and confirmed locally 2026-07-24 (`fix/mp-blank-title`, `tamara-builds/openstates-scrapers` fork). Two bugs, not one: the known blank-title crash on `HCommRes 24-6` (fixed with an identifier fallback), plus a second bug that fix surfaced — `cnmileg.net` renders that same bill's number with no space (`HCommRes24-6`), breaking a `bill_type_map` lookup. Local test: 317 bills (vs. this 139-file fallback), exit 0, zero tracebacks — a second unknown blank-title bill (`HCommRes 24-7`) also handled cleanly. See `pending-branches.md`. |
| **NH** | no | `H3_RATE_LIMITED`, 4 files | **2026-07-24 update — this is two separate issues, not one:** (1) NH's site blocks scraping 6am-9pm ET (known since 07-02) — the 07-21 dispatch above fired at ~11:41am ET, squarely inside that window, because that morning's dispatch hit all 56 states at once regardless of timing. (2) Separately, a scheduled run today at 2:27am ET — well outside the block window — still failed: got 1,084 clean requests to `gc.nh.gov`, then started dropping connections under our own unthrottled `--fastmode` burst (no delay between requests). Root cause: `--fastmode` sets `requests_per_minute=0` in openstates-core, silently overriding any per-state `SCRAPELIB_RPM` setting. Fix: `fix/nh-skip-fastmode` (govbot repo, commit `90915a52`) drops `--fastmode` for NH — **merged to `main` via PR #95**, so NH's next scheduled run (cron `0 4 * * *` UTC = midnight ET, tonight) picks it up automatically, no manual dispatch needed. A separate, additional `SCRAPELIB_RPM=20` setting exists on `fix/nh-rate-limit` (`tamara-builds/openstates-scrapers` fork) but is **not deployed anywhere NH's real workflow uses** — tonight's run tests whether dropping `--fastmode` alone is sufficient without it. **Separately:** a same-day local test run during the 6am-9pm ET window failed instantly on the very first request — a harder failure than (2)'s gradual degradation, suggesting the original time-block theory is also still real and unaddressed by either fix. See `pending-branches.md` for the full decision tree once tonight's run lands. |
| **VI** | ✅ yes | `UNKNOWN`, 0 files | Matches the already-known dead end: `billtracking.legvi.org:8082` is server-down, not a code problem (`scraper-health.md`). Genuine self-hosted execution doesn't help since the source itself is offline — this isn't a network-path problem. |
| **NM** | ✅ yes | 🟡 Real, not proxy-related — intermittent server issue, not a permanent dead end | Retried on **verified genuine self-hosted** (MacBookPro-6, `runner_group_name: default`, no proxy involved at all) — still failed 3x with `EOFError` on FTP connect to `www.nmlegis.gov`. Verified directly: `curl ftp://www.nmlegis.gov/other/` from Tamara's own network connects the TCP socket fine but the server never sends its FTP welcome banner, hanging until timeout (confirmed twice, ~15 min apart). **But** the 2026-07-14 run (29298513368, source of the known-good 812-bill baseline, also verified genuine self-hosted — MacBookPro-8) hit this exact same `ftp://www.nmlegis.gov/other/` call and got an instant clean response — so the server is intermittently down, not permanently, unlike VI. Not fixable client-side when it's down; worth a plain retry later (tomorrow, or next scheduled run) rather than writing it off. The FTP scrape summary reported "✅ Success" / "Nightly fallback" despite 0 bills — same soft-fail-looks-like-success pattern seen with FL earlier; don't trust the top-line status without checking the actual summary. |
| **NE** | ✅ yes | `H3_RATE_LIMITED`, 3,568 files | Was healthy 07-14 via self-hosted. Today's run went through **tinyproxy on GitHub-hosted** (config flag alone, no `use-self-hosted: true` override), not genuine self-hosted — likely part of the same shared-proxy congestion pattern seen with FL tonight, not a new site-specific block. Not yet retried on real self-hosted. |
| **WA** | no | `H3_RATE_LIMITED`, 2,994 files | Not previously flagged; not self-hosted-flagged at all, so this ran plain GitHub-hosted with no proxy — same likely explanation as NE (tonight's overall load), not a chronic issue. |

### Confirmed healthy 2026-07-24 — ready to move to working-out-of-session.md

| State | Config: self-hosted? | Today's count | Why it's fine |
|---|---|---|---|
| **AR** | ✅ yes | 6 files | Matches 07-14 notes exactly: current session (2026S1) genuinely only has 2 live bills. Correct as-is. |
| **NV** | ✅ yes | 64 files | Matches 07-14 notes: NV meets biennially, no regular session until 2027. Correct as-is. (Separate, known ~1,000+ bill backfill gap from the 2025 session — a one-time TODO, not an ongoing issue.) |
| **OR** | no | 308 files | Consistent with the 07-02 baseline (3 current/264 historical) — no prior flag, looks like normal small-state volume. |
| **MN** | no | 10,594 files | Re-verified 2026-07-24: 10,590 bill files, 10,587 distinct identifiers, only 3 stray dupes (noise, not a systemic problem). The 07-21 `N4_DNS_FAILURE` was genuinely transient as suspected. |

### Still running (not a problem, just not done)

| State | Config: self-hosted? | Notes |
|---|---|---|
| MA | ✅ yes | Shrink-guard-fix live-test run still finishing as of the fix's merge to `main` — see MA's row in the session-status table above. |
| FL | ✅ yes | Re-verification run ([30185187734](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/30185187734), dispatched 2026-07-26 02:50:14Z) combining the now-pushed scraper fixes with the shrink-guard fix already on `main`. Scraper fixes themselves already confirmed working in an earlier full run (see FL section above) — this run is a fresh combined check, not the original verification. |

---

## ✅ Currently healthy (40 states)

ak, al, ca, co, dc, de, gu, hi, ia, id, il, in, ks, ky, la, md, me, ms, nc, nd, nj, ny, ok, ri, sc,
sd, tn, tx, ut, va, vt, wi, wv, wy

**ct, mo, mt, oh, pa, pr, usa, wa, ma (P1_SHRINKING_OUTPUT, all now resolved)** — all nine hit
the shrink-guard duplicate-UUID bloat bug at various points (CT/MO/OH/PA on 07-21, the rest
found later). CT/OH/PA's manual clear+rescrape on 07-21 happened to succeed and held since. The
other six (MT/MO/PR/USA/WA/MA) kept getting re-stuck because the *real* root cause was never
fixed until 2026-07-25: the shrink-guard compared raw file counts, which can't tell "the site
removed bills" apart from "same bills, stale duplicate-UUID copies from a prior run's auto-save
that never got cleaned up because that run also tripped the guard" — self-reinforcing, not
self-healing. Fixed properly by comparing distinct bill identifiers instead
(`fix/shrink-guard-identifier-check`, merged to `main`). See `pending-branches.md` for the full
writeup and before/after counts per state.

**Config vs. actual execution today — important, don't conflate these:**

| State | Config says `runner:` | Actually ran on today (verified via `runner_name`) | Config needs updating? |
|---|---|---|---|
| ct | self-hosted | MacBookPro (self-hosted) | No — already matches |
| oh | self-hosted | MacBookPro (self-hosted) | No — already matches |
| usa | self-hosted | MacBookPro (self-hosted) | No — already matches |
| **mo** | `ubuntu-latest` (default) | **MacBookPro-1 (self-hosted)** | ⚠️ **Undecided** — ran self-hosted today only because of a one-time `-f use-self-hosted=true` dispatch override, not because config says to. Next scheduled/automatic run would fall back to default (no self-hosted, no proxy) unless config is updated. **Holding off on updating config until we see whether self-hosting actually mattered for MO's result** — don't assume it did. |
| **mt** | `ubuntu-latest` (default) | **MacBookPro-2 (self-hosted)** | ⚠️ **Undecided** — same situation as MO. |
| **pr** | `ubuntu-latest` (default) | **MacBookPro-6 (self-hosted)** | ⚠️ **Undecided** — same situation as MO/MT. |

Once MO/MT/PR finish, check whether self-hosted execution was actually load-bearing (vs. the clear+rescrape alone being sufficient) before deciding whether to add `runner: self-hosted` permanently for these three.

Worth noting: several of the first 34 (hi, il, in, nc, va, wv, tn and others) were themselves the
subject of real fixes documented in `error-tracking.md`/`scraper-health.md` (mostly self-hosted-runner
rollouts for IP-blocked states). They're grouped here as "healthy" only because today's audit found
no error code or shrink-guard trip — not re-verified at the bill-count level the way the flagged
states above were.

---

## Reference

### Current `runner: self-hosted` states (from `chn-openstates-scrape.yml`, 2026-07-21)

ak, ar, az, ct, fl, hi, il, in, ma, mi, nc, ne, nm, nv, ny, oh, pa, sc, tn, usa, va, vi, vt, wv

24 states total. If a state above shows a problem despite being self-hosted, that's meaningful —
self-hosting was specifically the fix for IP-blocking, so a self-hosted state still failing means
either a different root cause (AZ), the source site itself being down (VI), or shared-proxy
congestion rather than a per-state block (NE, WA — though WA isn't even self-hosted, worth noting).

### Failure category reference (from `error-tracking.md`, still accurate)

- **A — Out of Session**: scraper finds nothing, legislature not meeting (soft failure).
- **B — Government Site Structure Changed**: upstream scraper broken until OpenStates fixes it.
- **C — OCD Validation Failures**: data fetched but fails schema validation (MP's blank-title case).
- **D — Connectivity Issues**: network timeouts / connection refused.
- **E — Workflows Disabled / No Recent Runs**.
- **F — Active Scraper Blocking (IP-based)**: self-hosted runner or tinyproxy is the fix. Don't assume
  without verifying — some states that looked blocked (NC) just had a missing `runner: self-hosted`
  config, not an actual block.
- **G — Config Gap**: state was never switched to `runner: self-hosted`, or stuck on the `-paused`
  template with no schedule trigger. Looks identical to F until you actually test it.

### Open threads worth closing the loop on

- **Session Pause Automation** (`check-sessions.py`) has been disabled since 2026-07-14 — its
  OpenStates-API-based session dates proved repeatedly inaccurate and caused several of the false
  "frozen" states. Don't re-enable until its accuracy problem is fixed.
- **VA** — ✅ fully closed out 2026-07-26. Issues [#1377](https://github.com/openstates/issues/issues/1377) and
  [#1385](https://github.com/openstates/issues/issues/1385) both closed (the latter referencing
  [#5725](https://github.com/openstates/openstates-scrapers/pull/5725), merged 2026-07-08). VA's
  workflow is genuinely healthy (not disabled as this doc previously claimed elsewhere — see
  `working-out-of-session.md`), running daily, landing real data (1,051 files, exit 0). Not a
  problem state at all.
- **AZ** — ✅ resolved 2026-07-24. #5722 merged but didn't fix the real bug; PR
  [#5742](https://github.com/openstates/openstates-scrapers/pull/5742) has the actual fix
  (`--fastmode` cache poisoning), confirmed working live. See dedicated writeup above and
  `tamara-notes/scraper-status/upstream-pr-todo.md` for the revert-once-merged checklist.
- **FL** PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724) — updated 2026-07-23 per maintainer feedback (opt-in `allow_partial` flag + a newly-found `flhouse.gov` timeout fix), then again 2026-07-26 with a third fix (single-bill failures crashing the whole session, both a plain timeout and a `RejectedResponse` bot-detection variant) — pushed and commented, all three fixes verified live. CI green, awaiting maintainer re-review. Still don't assume merged/live in the official docker image yet — `fl-legislation` runs from a temporary custom image (`ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test`, now config-driven) until it merges. See the dedicated FL section above and `openstates-responses.md` for full detail.
- **NM** — waiting on maintainer to re-open issue [#1381](https://github.com/openstates/issues/issues/1381); we have a PR ready (`urllib.request.urlopen()` swap).
- **WV** — real 39-vs-2975 bill discrepancy from early July is resolved (self-hosted fix confirmed at exactly 2,975), but the *original* root cause of that discrepancy was never actually explained — see `openstates-responses.md`'s WV section before reopening any related work.
- **Node.js 20 deprecation** — all actions still show deprecation warnings (`actions/checkout@v4`, `setup-python@v5`, `cache@v4`, `upload-artifact@v4`, `action-gh-release@v2` all need bumping; `andelf/nightly-release@v1` has no newer version and needs a replacement). Not urgent but will eventually break.
- **MI — `legislature.mi.gov` doesn't serve its full TLS certificate chain** (missing DigiCert intermediate, confirmed via `openssl s_client`). 🔄 Fix drafted and looking very promising 2026-07-24 — see the dedicated row above and `pending-branches.md` for full detail (bundled the intermediate into the Docker CA store, verified working, live test in progress).
