# Pending local branches

Live-tracked, not chronological — update in place as branches move, don't just append.
Different from `upstream-pr-todo.md` (that's for work already merged locally but waiting on
an OpenStates PR to merge); this is for our own branches still mid-investigation, on either
the `govbot` repo or the `tamara-builds/openstates-scrapers` fork.

## govbot repo

### fix/identifier-count-malformed-json — ✅ MERGED (PR #98, 2026-07-26)

**Real production bug in PR #97's own commit-summary fix, found and fixed same night.**
`count_distinct_identifiers`'s batched `xargs -0 jq ...` call meant a single malformed
`bill_*.json` file made `jq` fail, `xargs` return exit 123, and under `set -euo pipefail` the
entire calling step aborted **silently, with zero output** — including the commit step in
`action.yml`, which could lose a perfectly good commit with no error message at all.

**Confirmed live in production**: GA's 06:30 scheduled run (30191180653) scraped 460 real bills
cleanly, then the commit step crashed with exit 123 at `OLD_DISTINCT=$(count_distinct_identifiers
...)`, losing that commit entirely — conclusion showed `failure` but the underlying scrape had
worked fine. Reproduced exactly in a real `ubuntu:24.04` + `jq` container (matching the actual
runner environment): one malformed file among valid ones → zero output, exit 123.

**Fix**: invoke `jq` once per file instead of one batched `xargs` call, so a single bad file
can't take the others down (`xargs -0 -I{} sh -c 'jq ... "$1" 2>/dev/null || true' _ {}`).
Verified against the exact malformed-file repro, plus empty-directory and missing-directory edge
cases. Same fix applied to `scrape.sh`'s original shrink-guard identifier check too, for
consistency (lower risk there since only invoked when file count already shrank, but same
underlying fragility).

### fix/commit-summary-identifier-aware — ✅ MERGED (PR #97, 2026-07-26)

Two bundled fixes, both found while reviewing USA's shrink-guard test runs:

1. **Commit-summary label was still raw-file-count based.** The job-summary's "Commit Content"
   label (not the shrink-guard itself, already fixed below) used raw `git diff --shortstat`
   insertions/deletions to decide "worth a look" vs "no net new content" — same blind spot the
   shrink-guard used to have. Confirmed on USA: three consecutive commits, distinct bill count
   flat at 17,574 the whole time, but each one flagged "⚠️ Net fewer files than last commit"
   anyway, because stale-duplicate cleanup deletes old files without a 1:1 new file replacing
   them. Fixed by comparing distinct bill identifiers instead, same approach as the shrink-guard.
2. **`503`/`429` classifier false positives.** `scrape.sh`'s failure-type grep did a bare
   substring match on `"503"`/`"429"`, which can match inside cache-busting query params some
   scrapers append to every request URL. Confirmed on NH: a plain `ScrapeError: no objects
   returned` (should classify as `S1_OUT_OF_SESSION`) got mislabeled `H4_SERVER_DOWN` because
   the timestamp in every logged request URL (`?x=<timestamp>`) happened to contain "503".
   Anchored both regexes to require non-digit boundaries.

**Confirmed clean on all three test states:**
- MT (2026-07-26): re-scraped, 4,495 distinct bills flat, correctly labeled "no net new content."
- NH (2026-07-26): correctly reported `S1_OUT_OF_SESSION` instead of `H4_SERVER_DOWN`, fell back
  to nightly (1,751 files) as designed, overall `✅ Success`.
- USA (2026-07-26): re-scraped, 17,574 distinct bills flat, correctly labeled "no net new content"
  despite 18,373 raw deletions vs. 9,229 insertions — exactly the false-alarm case this fix
  targets.

**Cleanup done:** MT/NH/USA's `openstates-scrape.yml` reverted back to `@main` before merging.
PR #97 squash-merged to `main`, branch deleted (local + remote).

### fix/nh-skip-fastmode — ✅ MERGED (PR #95, 2026-07-24)

Drops `--fastmode` for NH so the framework's 60 RPM default applies instead of `--fastmode`'s
`requests_per_minute=0`. Done, on `main`. Kept here only as a pointer — see NH's row in
`not-working.md` for what's still open (whether it actually fixes anything, given the same-day
test during the 6am-9pm ET block window failed a different, harder way).

### fix/state-scrapers + fix/shrink-guard-identifier-check — ✅ MERGED to main (2026-07-25)

Fast-forward merged, no conflicts, pushed. **This closes out the whole shrink-guard saga** —
both branches, and everything below, are now just history/context, not active work.

**What's in it:**
- Shrink-guard compares distinct `bill_*.json` identifiers instead of raw file counts, so stale
  duplicate-UUID bloat can't masquerade as (or cause) a false "shrink" (commit `ada2aead`).
- Fixed a *separate*, pre-existing bug that blocked round 1 of live-testing the above: a
  `grep -c ... || echo N` pattern in `SKIPPED_COUNT`/`ERROR_COUNT` double-printed whenever the
  count was genuinely zero (grep -c's own "0" plus the `||` fallback's "0" both landing in the
  variable), corrupting `scrape-summary.json` and crashing every run before the commit step
  could run — even though the actual dedup logic was working correctly every time. Fixed by
  swapping to `|| true` + a parameter-expansion default (commit `ee98b969`).
- Everything else already on `fix/state-scrapers`: NH `--fastmode` (already merged via #95),
  AZ status-doc fix, skipped-items surfacing, self-hosted/tinyproxy flagging for
  GA/MN/OR/WA/MT/PR/MO, and MA/FL forced-self-hosted-on-schedule.

**Live-test results — 5 of 6 states fully confirmed clean, 1 still finishing:**
| State | Before (bloated) | After (real) | Status |
|---|---|---|---|
| MT | 37,555 files | 4,495 bills | ✅ confirmed, 2 clean runs since |
| MO | 22,015 files | 3,158 bills | ✅ confirmed (a later run correctly held back on a small genuine drop — guard working as designed) |
| PR | — | landed clean | ✅ confirmed |
| USA | 34,992 files (half stale) | 17,574ish bills | ✅ confirmed, 2 clean runs since |
| WA | 6,153 files, frozen since 07-24 04:06 | 3,411ish bills | ✅ confirmed, unfroze cleanly |
| MA | 50,183 files (worst bloat found, ~4.5x) | ~11,123 bills expected | 🔄 still not confirmed as of 2026-07-26 — several manually-dispatched runs since the merge got cancelled before finishing (~30-45min in, not the full ~11hr); timeout bumped from 12h to 2 days and re-triggered again |

**FL also has this exact bug** (found 2026-07-25: 3,123 bill files, only 1,878 distinct, 357
duplicated — same-day duplicate timestamps) but was never added to the manual test batch. No
action needed though — since the fix is now on `main` and FL's workflow already points at
`@main`, its next run (including the one already in progress) picks up the fix automatically.

**Cleanup done:** all six states' `openstates-scrape.yml` reverted from
`@fix/shrink-guard-identifier-check` back to `@main` (safe to do mid-run for MA — GitHub Actions
checks out the ref at job start, doesn't re-read it mid-run).

**Still open:**
1. Confirm MA's in-progress run lands a clean `"🕷️ Scrape data for ma"` commit once it finishes.
2. Update `not-working.md`'s CT/MA/MO/MT/OH/PA/PR/USA/WA/FL rows with final ✅ status.
3. Worth a broader sweep: WA, MA, and FL were all found *by accident*, not because anything
   flagged them. Other "success"-reporting states could be silently frozen the same way — the
   identifier-dedup check is cheap enough to run against every state's live repo, not just the
   ones already known to be stuck.

## tamara-builds/openstates-scrapers fork

### fix/nh-rate-limit — 🔄 decision made: RPM cap likely unneeded, verify=False cleanup still pending

- Adds `settings = dict(SCRAPELIB_RPM=20)` to `scrapers/nh/__init__.py`.
- **Decision point resolved 2026-07-26.** Checked both real completed scrapes since
  `fix/nh-skip-fastmode` (#95) merged: 07-25 06:19 (the automatic scheduled run this was waiting
  on) and 07-25 14:34 (a manual dispatch, at 10:34 ET — inside the 6am-9pm ET block window). Both
  landed clean: 1,751 files, `SCRAPE_TARBALL: present`, `SCRAPE_FAILURE_TYPE: NONE`, zero errors.
  Per the original decision point — dropping `--fastmode` alone was sufficient. This branch's
  extra `SCRAPELIB_RPM=20` cap is probably not needed; not building/deploying it.
- **Not deployed anywhere NH's real workflow uses**, and no live test planned now given the
  above — NH still runs on stock `openstates/scrapers:latest`.
- **Still worth doing separately:** commit `1b576734e` (2026-07-24) removed dead `verify=False`
  from all 11 request sites in `bills.py` (`gc.nh.gov`'s cert is valid, checked via `openssl
  s_client`/`curl -v` — not masking a real problem). This part is independent of the RPM-cap
  question and could still go up as its own small PR/cleanup.
- **NH's 6am-9pm ET block window is still real and unaddressed** (confirmed from NH's own site
  logs) — neither this branch nor #95 touches it. Separate, still-open problem.

### fix/mp-blank-title — ✅ confirmed via real GitHub Actions run (2026-07-26), ready for upstream PR

- **Commits:** `b607f5692` (blank-title fallback, 07-24) + `cd8d39403` (bill_id spacing
  normalization, 07-26 — see correction below).
- **Root cause #1:** `HCommRes 24-6` has a genuinely empty title on `cnmileg.net`; OCD requires
  `minLength: 1`, so the scraper crashed on this exact bill every run and silently dropped every
  bill after it in iteration order (139 files = the partial haul before the crash). Fix: fall
  back to the bill's own identifier as the title when the site gives us nothing.
- **Root cause #2:** `cnmileg.net`'s "Number" cell renders the same bill as `HCommRes24-6` (no
  space) instead of the normal `HB 123`-style spacing on the lower-chamber path, breaking
  `bill_type_map[bill_id.split(" ")[0]]`'s lookup (`KeyError: 'HCommRes24-6'`). Fix: normalize
  `bill_id` to always have a space between type prefix and number.
- **Correction, 2026-07-26:** this doc previously claimed root cause #2 was already fixed via a
  commit `4f3af9c54` — that commit **never existed**, confirmed via `git log --all` on the fork.
  Only the blank-title fix had actually been pushed; the local "317 bills, zero tracebacks"
  result described below must have been run against uncommitted local changes that were lost.
  Re-verified the underlying bug is still live in production (07-25 scheduled run: crashes on
  `HCommRes 24-6` every retry, same 139-file fallback every time), then added the actual missing
  fix (`cd8d39403`) before doing anything else with this branch.
- **Confirmed via real GitHub Actions run, not just local** — explicit standard set 2026-07-26:
  a local Docker test alone isn't sufficient confirmation anymore (see MI's arch-mismatch
  mistake). Built `ghcr.io/tamara-builds/openstates-scrapers:mp-fix-test` for `linux/amd64`
  explicitly (verified via `docker manifest inspect --verbose` before dispatching —
  `"architecture": "amd64"`), pointed `mp-legislation`'s workflow at it, dispatched (run
  `30188623954`). **Result: clean, first attempt** — `SCRAPE_EXIT_CODE: 0`,
  `SCRAPE_FAILURE_TYPE: NONE`, `SCRAPE_TARBALL: present`, 321 real bills. Log shows both fixes
  working live: `HCommRes 24-6 has no title on cnmileg.net, using identifier as a fallback` and
  the same for `HCommRes 24-7`, zero tracebacks, zero `KeyError`, zero retries.
- **Pushed:** yes, `origin/fix/mp-blank-title`
- **Upstream PR filed:** [openstates/openstates-scrapers#5744](https://github.com/openstates/openstates-scrapers/pull/5744) (2026-07-26). See `upstream-pr-todo.md` for the merge-day
  checklist. **`mp-legislation`'s workflow stays pointed at `mp-fix-test`** until #5744 actually
  merges — same pattern as AZ, not reverted to default.

### fix/mi-digicert-intermediate — ❌ ABANDONED 2026-07-26, wrong diagnosis

Branch deleted, `mi-fix-test` image and workflow override removed. The DigiCert intermediate
cert theory (missing chain on `legislature.mi.gov`, confirmed via `openssl s_client` against the
bare domain) turned out to be a red herring for what actually blocks production: checked three
real runs' full logs (2026-07-22, 07-23, 07-25) and found **zero** occurrences of
`SSLCertVerificationError` in any of them. `mi/bills.py` already calls with `verify=False` for
the actual bill-detail host (a raw IP, `34.57.23.77`), bypassing the cert chain entirely on every
request — the missing intermediate never actually blocks a live run. Building/testing a custom
image with the cert bundled was solving a problem that doesn't manifest in practice.

**What those three runs actually showed:**
- 07-22 (`29896737044`): scraped cleanly to completion, 5,097 real files, zero tracebacks — but
  blocked by the *old* raw-file-count shrink-guard (`P1_SHRINKING_OUTPUT`), already fixed on
  `main` since (see `fix/commit-summary-identifier-aware`'s sibling fix above).
- 07-23 and 07-25 (`29985152080`, `30147190768`): both crash identically, every retry, on
  `dateutil.parser._parser.ParserError: Unknown string format: 4/29/2025<` at `mi/bills.py:118`
  — a malformed date cell (stray unescaped `<`) on HB 4401, 2025-2026 session. Discards whatever
  was scraped (2,207 files) and falls back to nightly. Misclassified as `H3_RATE_LIMITED` (same
  bare-substring-grep issue as NH's `503` bug — no real rate-limiting involved).

See `fix/mi-date-parsing` below — the actual fix for MI's real, reproducible blocker.

### fix/mi-date-parsing — ✅ confirmed via local Docker test 2026-07-26, first-ever complete MI scrape

- **Commit:** `e68079346` — extracts just the date portion (`\d{1,2}/\d{1,2}/\d{4}`) from
  History table date cells before handing to `dateutil.parser.parse()`, in both
  `scrape_actions` and `scrape_votes` (same table, same bug, both call sites fixed).
- **Root cause:** some action/vote rows' date cells carry a stray, unescaped `<` right after
  the date (e.g. `"4/29/2025<"`), which `dateutil.parser.parse()` can't handle. Confirmed
  reproducible on HB 4401 — every scheduled run since 2026-07-23 crashed on this exact bill.
- **Verified:** regex extraction tested against the exact malformed string plus normal-format
  dates (`4/29/2025<`, `4/29/2025`, `12/1/2025<br`, `1/1/2026`) — all parse to the correct date,
  well-formed dates unaffected.
- **Local Docker test: ✅ complete, clean.** Ran ~2 hours, finished 2026-07-26. **3,884 real
  bills, 5,097 total JSON files** — matches almost exactly the 07-22 GitHub Actions run that got
  blocked by the old raw-count shrink-guard (also 5,097 files), confirming this is genuinely the
  full session. Zero tracebacks during the actual scrape (HB 4401 and every other bill saved
  cleanly) — the only exception anywhere in the log is an unrelated Postgres connection error
  in the report-saving step *after* scraping finishes (no local DB configured for this
  standalone test, not a real problem). MI has never produced a real file before this.
- **Pushed:** yes, `origin/fix/mi-date-parsing`
- **Next:** same standard as MP — needs a real live GitHub Actions confirmation (not just
  local) before deciding upstream PR vs. custom-image-in-the-meantime. Local test alone isn't
  sufficient per the standard set today.
- **Next:** confirm the local test clears HB 4401 without crashing and gets a real final bill
  count, then decide upstream PR vs. custom-image-in-the-meantime (same pattern as AZ/GA/MP).
  Update `not-working.md`'s MI row once resolved either way.

### fix/ga-subjects-resilience — ✅ confirmed working locally (176 bills, 280 vote events, exit 0, zero tracebacks)

- **Commit:** `d5621c239` — GA's `scrape()` was calling `scrape_subjects()` (a separate REST
  API, `legis.ga.gov/api`) unprotected: `get_token()` had no timeout and wasn't even inside
  `scrape_subjects`'s own try/except, so any connection hiccup there killed the *entire* scrape
  over non-critical subject-tag metadata. Matches GA's recorded `N2_CONNECTIVITY` failures
  (near-zero files, no other site-wide symptom).
- Fix: wrap the `scrape_subjects()` call site so failure there degrades to "no subjects"
  instead of killing the run; add `timeout=30` to `get_token()`'s request.
- **Pushed:** yes, `origin/fix/ga-subjects-resilience`
- **Local docker test: ✅ confirmed clean.** 176 bills, 280 vote events, exit 0, zero
  tracebacks — matches production's real `--fastmode` invocation.
- **Next:** decide whether to open an upstream OpenStates PR (this is a real bug fix, not
  GA-specific hackery, plausible to get accepted the way AZ's fixes were) or just run GA on
  this custom image in the meantime the way AZ currently does — see `upstream-pr-todo.md`
  for that pattern. Update `not-working.md`'s GA row once resolved either way.
