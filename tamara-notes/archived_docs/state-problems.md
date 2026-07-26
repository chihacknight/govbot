---
name: state-problems
description: Detailed per-state scraper/extraction problem tracking — the working notes behind the Scraper/Text-Extraction columns in docs/src/state-status-reference.md
metadata:
  type: project
---

# State Problem Tracking

Detailed, state-by-state investigation notes. The published reference table
(`docs/src/state-status-reference.md`) only gets a short status code + a one-line note per
state — this file is where the actual reasoning, evidence, and history behind each entry lives.

**Only add a state here once it's actually been investigated.** Don't copy speculative or stale
info forward from the older docs (`scraper-health.md`, `error-tracking.md`,
`openstates-responses.md`) without re-checking it first — that scattered, sometimes-contradictory
state is exactly what this file is meant to replace.

Once a state's entry here is solid, update its row in `state-status-reference.md` with the short
version + a date, and link back here if useful.

---

## FL

**Status as of 2026-07-24:** `P1` (in progress) — third scraper bug fixed and deployed to a test
image, live verification run in progress; nothing committed yet

**What we know:**

- Two earlier bugs (2026-07-23/24, PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724)):
  a `list()` anti-pattern holding all ~1,900 bills in memory until the entire session finished
  (fixed by streaming), and a missing `timeout=` on the three `flhouse.gov` request constructions
  in `fl/bills.py` that let a stalled connection hang forever (fixed with `timeout=10`). Both
  confirmed working — a self-hosted run landed 413 real bills, first real FL data since 2026-07-02.
- A third, separate bug found in that same run's final failure: a single bill's `flhouse.gov`
  fetch failing (even after its own retries exhausted) crashed the *entire remaining session*
  instead of just skipping that bill — costing the run everything after that point (149 files
  auto-saved since the last checkpoint were discarded).
- Root cause (confirmed by reading spatula's actual source, not just inferred): spatula's
  `Page._fetch_data` only converts `scrapelib.HTTPError` into its own swallowable `HandledError`.
  A `requests.exceptions.ReadTimeout`/`ConnectionError` — what FL's `patched_get_response` retry
  wrapper re-raises after exhausting its own 3 retries — isn't an `HTTPError`, so it propagates
  raw through spatula's entire recursive `_to_items()` generator chain (BillList → BillDetail →
  HouseSearchPage → HouseBillPage → HouseComVote is all *one* generator), landing in
  `_process_bill_list`'s outer except block meant for session-wide problems, not per-bill ones.

**Fix applied:**

- Added a `ResilientFetchPage` mixin in `scrapers/fl/bills.py` (branch `fix/fl-streaming-bills`,
  `~/tad_code.nosync/current/openstates-scrapers`) that wraps `_fetch_data`, catches transient
  network exceptions, and re-raises them as spatula's own `HandledError` — reusing spatula's
  existing "nothing left to do with this page, move on" handling instead of inventing a new one.
  Applied to 5 classes, all supplementary/independent per-bill data: `HouseSearchPage`,
  `HouseBillPage`, `HouseComVote` (flhouse.gov), `FloorVote`, `UpperComVote` (flsenate.gov vote
  PDFs). Deliberately **not** applied to `BillList`/`BillDetail`/`SubjectPDF` — those are
  session-wide or a bill's own core data, where silently swallowing a failure risks a run looking
  complete when it isn't.
- Companion change in this repo (`actions/scrape/scrape.sh` + `actions/scrape/action.yml`,
  uncommitted): a `SKIPPED BILL:` log-line convention that surfaces a distinct
  "🔁 Skipped, Will Retry Next Run (N)" section in the GitHub Actions summary, separate from the
  generic error bucket — since this scrape runs nightly, a skipped bill is expected to get picked
  up the next night and shouldn't read as an unresolved fault. Generic convention, not FL-specific
  plumbing — any scraper can opt in with the same prefix.
- Deployed to the test image `ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test` (digest
  `sha256:d2c04e736d9c44dc4647ae1274c4b576600446a58ac1274daa782a29833819dc`), verified via direct
  grep inside the pulled image. A live verification run is in progress: `gh run view 30101428905
  -R govbot-openstates-scrapers/fl-legislation` (dispatched 2026-07-24T14:32:11Z, self-hosted).

**Open questions:**

- Does `BillDetail` itself need the same resilience treatment? Deliberately deferred — unlike the
  5 classes above, `BillDetail`'s own primary fetch failing would silently drop that bill's entire
  record (title, sponsors, versions), not just its supplementary votes, which is a materially
  different trade-off. Plan is to watch real skip frequency from the verification run before
  deciding whether it's even needed.
- Does the verification run complete a full session without crashing, and does the new
  "Skipped, Will Retry Next Run" summary section render correctly if any bills actually get
  skipped? Not yet confirmed — run was still in progress as of this writing.
- Nothing is committed yet in either repo (`openstates-scrapers` or this one). Once the
  verification run confirms the fix, next steps are: commit both, push to the `fix/fl-streaming-bills`
  branch (updates open PR #5724), and a short PR comment flagging this as a follow-up.
- Separately (not part of this fix): `chn-openstates-scrape.yml`'s FL locale config has a pending,
  uncommitted `force_self_hosted: "true"` change (verified correct — already proven live on MA) that
  forces the *scheduled* run onto self-hosted too, not just manual dispatches. Intentionally not yet
  applied to the live `fl-legislation` repo, holding off until no scrape is in-flight.

**Related:** PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724), issue
[#1386](https://github.com/openstates/issues/issues/1386). `fl-legislation`'s live workflow still
has a temporary `docker-image: ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test` override —
revert once #5724 merges and upstream cuts a real image with the fix.

---

## AZ

**Status as of 2026-07-24:** `S3` (in progress) — real root cause found (not the WAF/cookie bug
long assumed), fix confirmed working locally twice and mid-way through a live Tinyproxy
verification run; nothing merged yet

**What we know:**

- AZ has never produced bill data. Original diagnosis (issue
  [#1382](https://github.com/openstates/issues/issues/1382)) was a Sucuri WAF blocking the
  `setsession.php` POST. That was disproven 2026-07-14: self-hosting (non-Azure IP) still hit
  `AssertionError: Session ID not in bill list` — the POST goes through fine, cookies aren't the
  issue. PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) (cookie-merge
  fix) merged 2026-07-15 anyway ("more robust at no real cost" per the maintainer, who could never
  reproduce the failure) but **did not fix it** — the 2026-07-24 Hosting Path History audit in
  `docs/src/state-status-reference.md` still shows `S3_SESSION_CONFIG` failing identically on all
  three paths (Tinyproxy, MacBookPro, plain GitHub-hosted), which is what prompted a fresh look.
- **Real root cause, confirmed today by direct reproduction**: `az/bills.py`'s `scrape()` does
  GET `/bills/` → POST `setsession.php` (sets session 130 server-side) → GET `/bills/` again,
  asserting the session now shows as `selected`. `actions/scrape/scrape.sh` always passes
  `--fastmode` to every scraper invocation — and per OpenStates' own CLI help text, that flag's
  actual purpose is `"use cache and turn off throttling"`, a **local dev/iteration convenience
  flag**, not something meant for production scraping. It sets `cache_write_only = False`
  (`openstates/scrape/base.py`), which enables scrapelib's `FileCache` to **serve GET responses
  from disk** — keyed purely on URL, ignoring cookies/headers/method. So the second GET to
  `bill_list_url` was being served the *first* GET's cached response (from before the session was
  set), never reflecting the POST at all. 100% reproducible, on any network, because it's a
  caching bug, not a network one — which explains why it failed identically on every hosting path,
  and why the maintainer couldn't reproduce it locally (their repro command omitted `--fastmode`).
- Verified directly: reproduced the exact failure from a fresh, empty `_cache/` dir inside the
  real `openstates/scrapers:latest` image (confirmed via `--entrypoint bash` + a small script using
  the actual venv). The stale cached page had zero `selected` options at all — the pre-session
  page. A plain `requests`/`curl` test of the same 3-step flow against the live site (no fastmode,
  no persistent cache) worked correctly every time.

**Fix applied:**

- In `scrapers/az/bills.py` (branch `fix/az-fastmode-cache-poisoning`,
  `~/tad_code.nosync/current/openstates-scrapers`, off latest `upstream/main`): temporarily set
  `self.cache_write_only = True` around just the post-session GET, forcing a live fetch instead of
  a cache read for that one request. Verified the toggle fixes it in isolation (same reproduction
  script, cache-read on vs. off) before touching the real scraper code.
- Built and pushed `ghcr.io/tamara-builds/openstates-scrapers:az-fix-test` (linux/amd64), verified
  the fix landed via direct grep inside the pulled image.
- **Local confirmation, twice**: ran `az bills --scrape --fastmode` against the fix image directly
  (not through CI) — first with a fresh cache (2,190 bills, 3,462 vote events, ~10 min), then again
  with the now-warm cache for a clean log (same counts, 26.6s, exit code 0, zero errors/warnings
  besides the expected "no session provided" line). AZ has never produced a single bill before this.
- Live verification: `govbot-openstates-scrapers/az-legislation`'s workflow temporarily points
  `docker-image:` at the test image (pushed directly to that repo's `main`, same pattern FL used —
  intentionally not routed through the shared pipeline-manager template, since it's a temporary
  test override, not a permanent config; see `tamara-notes/scraper-debugging-onboarding.md`).
  First dispatch ([run 30107906183](https://github.com/govbot-openstates-scrapers/az-legislation/actions/runs/30107906183))
  was healthy the whole way through — actively saving bills with zero errors — but got cancelled
  partway through by mistake (looked idle in the UI; log review afterward confirmed it wasn't
  stuck). Re-dispatched: [run 30109209415](https://github.com/govbot-openstates-scrapers/az-legislation/actions/runs/30109209415),
  in progress as of this writing.

**Open questions:**

- Does the live Tinyproxy run finish clean end-to-end? Not yet confirmed — in progress.
- Once confirmed, open the upstream PR (branch already pushed to `tamara-builds/openstates-scrapers`,
  no PR opened yet) — reference the disproven WAF/cookie theory and PR #5722 directly, since the
  maintainer will likely want to understand why the "more robust" merge didn't actually fix
  anything.
- Is any other scraper vulnerable to the same GET-mutate-GET cache-poisoning pattern under
  `--fastmode`? Not checked yet — AZ is the only confirmed case so far.
- Revert `az-legislation`'s live `docker-image:` override once the upstream PR merges and a new
  official `openstates/scrapers:latest` image is built.

**Related:** PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) (merged,
did not fix the real bug), issue [#1382](https://github.com/openstates/issues/issues/1382).
`tamara-notes/scraper-debugging-onboarding.md` has the generalized `--fastmode` gotcha and the
full reproduce→fix→test→upstream playbook this followed.

---

## MT

**Status as of 2026-07-24:** `P1` (disputed) — scrape shrink-guard blocked; text-extraction incomplete, restart mechanism just fixed

**What we know:**

- Scrape: shrink-guard has blocked commits since 2026-07-21 (fresh scrapes producing ~4,495
  bills vs. the ~7,024-file/24,461-total baseline already committed). Real duplication confirmed
  in the baseline (~1-2%, exact-duplicate bills under different UUIDs — e.g. `SB 462`), but that
  rate doesn't explain the size of the gap. Two independent processes (format's own dedup of the
  "cleaned" 07-21 data, and a completely fresh 07-23 scrape) both landed on 4,495 — suggestive,
  not proof. Root cause of the gap is still open.
- Text-extraction: has **not finished** as of this writing. Every run against MT's dataset was
  hitting its ~5.9hr timeout and failing to restart — the auto-restart step needed a real PAT
  (`secrets.PAT_WORKFLOW_TRIGGER`) that was never provisioned org-wide (same gap already found on
  NH 2026-07-21).

**Fix applied:**

Swapped the restart step to use a GitHub App token (same pattern as scrape→format cross-org
dispatch) instead of the missing PAT. Applied to `govbot-data/mt-legislation` via `apply.py` and
merged upstream in the shared template (PR #93). Cancelled the old (pre-fix) run and started a
fresh one so it actually picks up the new definition.

**Open questions:**

- Does the restart actually fire successfully next time extraction hits its timeout? Not yet
  confirmed — need to watch the next long run.
- Why does the raw scrape baseline (~6,900 estimated unique bills) not match format's output
  (4,495)? Still unexplained.
- Should the 6,900-vs-4,495 discrepancy be resolved before or after the extraction restart is
  confirmed working? Text-extraction is currently running against whatever's already committed
  (the disputed 4,495-bill format output), so a later data correction could invalidate/duplicate
  extraction work already done.

**Related:** PR [#93](https://github.com/chihacknight/govbot/pull/93) (restart fix, merged) — same
underlying restart bug likely affects every other state with a large enough bill count to hit the
~5.9hr extraction timeout, not just MT. Worth checking which other states have been silently
failing to restart before assuming this is MT-specific.

## MA

**Status as of 2026-07-24:** `N2`/timeout (fixed, verifying) — real root cause was a platform-level
runner cap, not network/IP blocking; fix applied and a live self-hosted verification run in progress

**What we know:**

- MA has not completed a single *scheduled* scrape since 2026-07-20. Every nightly run from 07-21
  through 07-24 landed on `ubuntu-latest` (the Tinyproxy path, MA's `runner: self-hosted` default
  since PR #75 "un-pause all 27 paused states, default self-hosted locales to tinyproxy") and was
  killed at **exactly 6h00m** each time (job-level timestamps: 06:16:07→12:16:26, 06:21:46→12:22:03,
  06:18:29→12:18:45, 06:27:02→12:27:18) — GitHub's hard, non-configurable 6-hour execution cap for
  GitHub-hosted runners, which `timeout-minutes` cannot raise regardless of value (MA's is set to
  720). Tinyproxy doesn't help here since it still runs on `ubuntu-latest` under the hood.
- Every historical *successful* MA run was on the real self-hosted MacBookPro runner, with durations
  regularly exceeding 6h: ~11h47m (07-15), ~9h45m (07-06), ~7h44m (07-01), ~2h34m (07-13). So this
  isn't "Tinyproxy untested" (the state `scraper-fix-plan.md` had it in before today) — MA's real
  scrape duration makes the Tinyproxy/hosted path structurally incapable of ever completing, not
  merely unlucky so far.
- Older self-hosted-only runs (pre-07-20) that got `cancelled` did so at 24h/29h, consistent with the
  already-known "runner uptime gap" issue (laptop asleep/disconnected) — a separate, real cause that
  only applies to the self-hosted path, not what's been killing the last 4 nights.
- No evidence found of an hours-of-day blocking rule for MA specifically (that may be a memory of
  NH's confirmed 6am-9pm ET block, not MA) — `scrape_cron` (`0 4 * * *` UTC ≈ 11pm-midnight ET) isn't
  implicated in the 6h-cap failures either way.
- Confirmed working correctly and unaffected by any of this: `actions/scrape/scrape.sh`'s 30-minute
  incremental auto-save already commits real in-progress progress directly to
  `govbot-openstates-scrapers/ma-legislation`'s `main` throughout each 6h run (real commit history
  checked, e.g. `06:46:59` through `11:47:27` on 07-24) — so partial data was never actually being
  lost to these cancellations, just never reaching a *complete* dataset.

**Fix applied:**

- Added a `force_self_hosted` locale config flag (default `"false"`, so every other
  `runner: self-hosted` locale renders identically) to `actions/pipeline-manager`'s shared template —
  when `"true"`, the *scheduled* trigger lands on self-hosted directly instead of only being
  reachable via a manual `workflow_dispatch` opt-out. Set `force_self_hosted: "true"` for `ma` (and
  `fl`, same real constraint, already being worked around by hand). Applied to `ma-legislation`'s
  live workflow via `apply.py --test-states ma`; deliberately **not yet** applied to `fl-legislation`
  (active scrape in progress there).
- Verified live: manually dispatched `ma-legislation`'s scrape workflow post-fix, confirmed it landed
  on `MacBookPro-1` (self-hosted) with no `use-self-hosted` flag needed — [run
  30107462477](https://github.com/govbot-openstates-scrapers/ma-legislation/actions/runs/30107462477),
  in progress as of this writing.

**Open questions:**

- Does this verification run actually complete (vs. hitting some other failure once past the 6h
  mark)? Not yet confirmed.
- Does MA's scraper have the same "one bad item crashes the whole session" pattern found in FL's
  `bills.py` (see FL entry above)? Not checked yet.
- 30 other locales are flagged `runner: self-hosted` and inherited the same Tinyproxy-default
  behavior from PR #75 — any of them whose real scrape duration exceeds ~6h has this identical
  structural problem, not just MA/FL. Worth auditing which ones, rather than finding out one at a
  time from repeated silent cancellations.

**Related:** PR #75 (introduced the Tinyproxy default, 2026-07-20) is what turned this from "self-
hosted, occasionally cancelled by runner-uptime gaps" into "guaranteed to fail every single scheduled
run." `tamara-notes/scraper-debugging-onboarding.md` has the general reproduce→fix→test playbook.

<!-- Template for a new entry:

## XX

**Status as of YYYY-MM-DD:** <code> — <one line>

**What we know:**

**Evidence:**

**Open questions:**

**Related:** PR/issue links, related states with the same root cause

-->
