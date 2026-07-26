# Morning check-in (2026-07-25)

Everything pending across the scraper-status folder, in one place — not just the upstream PR
follow-ups. Started 2026-07-24 evening; most of the shrink-guard saga resolved same night.

## Do first, time-sensitive

- **Commit-summary identifier-aware fix — MT and NH confirmed, USA still running.**
  `fix/commit-summary-identifier-aware` (pushed to `origin`) fixes a *separate*, still-open bug
  found while reviewing USA's shrink-guard test runs: the job-summary's "Commit Content" label
  (not the shrink-guard itself, which is already fixed) was still using raw `git diff --shortstat`
  insertions/deletions to decide "worth a look" vs "no net new content" — same raw-count blind
  spot the shrink-guard used to have. Confirmed on USA: three consecutive commits, distinct bill
  count flat at 17,574 the whole time, but each one flagged "⚠️ Net fewer files than last commit"
  anyway, because stale-duplicate cleanup deletes old files without a 1:1 new file replacing them.
  Fix compares distinct bill identifiers instead (same approach as the shrink-guard in
  `scrape.sh`). Bundled into the same branch: a second fix for a bare-substring `"503"`/`"429"`
  classifier bug (found live on NH — a cache-busting query-param timestamp coincidentally
  contained "503", mislabeling a plain `S1_OUT_OF_SESSION` as `H4_SERVER_DOWN`).
  **MT confirmed 2026-07-26**: re-scraped, 4,495 distinct bills flat, correctly labeled
  "no net new content" instead of a false alarm. **NH confirmed 2026-07-26**: correctly reported
  `S1_OUT_OF_SESSION` instead of `H4_SERVER_DOWN`, fell back to nightly (1,751 files) as designed,
  overall `✅ Success`. **USA still running** (dispatched ~03:29 UTC 07-26, in progress) — once it
  lands clean, revert MT/NH/USA's `openstates-scrape.yml` back to `@main` and merge the branch.
- **NH's 6am-9pm ET block window is real** (confirmed from NH's own site logs) — don't let the
  classifier fix above be misread as calling that into question. See `not-working.md`'s NH row.

## ✅ Shrink-guard duplicate-bloat bug — RESOLVED, merged to main

Full writeup in `pending-branches.md`. Short version: OpenStates assigns a fresh UUID to every
bill on every scrape; the shrink-guard compared raw file counts, which couldn't tell "real data
loss" apart from "same bills, stale duplicate-UUID copies from an auto-save that a prior
guard-trip never let get cleaned up" — self-reinforcing, not self-healing. Fixed by comparing
distinct bill identifiers instead. A second, unrelated `grep -c` double-print bug blocked the
first live-test round entirely (crashed `scrape-summary.json` before any commit could land) —
found and fixed too. Both fixes merged to `main` 2026-07-25 (fast-forward, no conflicts).

**Confirmed clean (real bill count landed, replacing bloated baseline):**
- MT: 4,495 bills (was 37,555 files) — two clean runs since, holding steady
- MO: 3,158 bills (was 22,015 files) — a later run correctly held back on a small genuine drop
- PR: landed clean (was 23,866 files, only 5,115 real)
- USA: ~17,574 bills (was 48,714 files, half stale) — two clean runs since
- WA: ~3,411 bills (was frozen since 07-24 04:06, silently reporting false "success")
- CT, OH, PA: re-verified clean — their 07-21 manual clear+rescrape had already held

**Still to confirm:** MA — live-test run was still finishing (self-hosted, ~11hr typical) as of
the merge. Check for a clean `"🕷️ Scrape data for ma"` commit.

**No action needed, but worth knowing:** FL also has this bug (3,123 files, only 1,878 real) —
found by accident, never added to the manual test batch. Since the fix is on `main` and FL's
workflow already points at `@main`, its next run picks up the fix automatically.

**Cleanup already done:** all six states manually tested (MT/MO/PR/USA/WA/MA) had their
workflow files reverted from the test branch back to `@main`.

**Worth doing next:** WA, MA, and FL were all found *by accident*. Consider running the
identifier-dedup check against every state's live repo, not just the ones already known to be
stuck — other "success"-reporting states could be silently frozen the same way.

## Other fixes from this session

- **AZ — ✅ resolved, merged, live in production.** `--fastmode` cache-poisoning bug (not the
  old cookie theory). Upstream PR [#5742](https://github.com/openstates/openstates-scrapers/pull/5742).
  AZ runs on a custom image until that merges — see `upstream-pr-todo.md`.
- **GA — ✅ confirmed working locally** (176 bills, 280 vote events, exit 0, zero tracebacks).
  `fix/ga-subjects-resilience`. Next: decide upstream PR vs. custom-image-in-the-meantime.
- **MP — ✅ confirmed working locally** (317 bills vs. old 139-file fallback, zero tracebacks).
  Two layered bugs on the same bill, both fixed. `fix/mp-blank-title`. Same next-step decision.
- **NH — partially resolved.** `--fastmode` fix merged (see above). Separate time-based block
  (6am-9pm ET) still real and unaddressed. Bonus: removed dead `verify=False` from 11 request
  sites (`fix/nh-rate-limit`, not yet deployed anywhere).
- **MI — 🔄 first live GitHub Actions test attempted 2026-07-26, blocked by an infra mistake, retesting.**
  Bundled the missing DigiCert intermediate cert into the Docker CA store; verified `curl`/`requests`
  get clean `HTTP 200` with real cert verification (previously failed on every path, confirmed both
  locally and inside the built image). Built and pushed `ghcr.io/tamara-builds/openstates-scrapers:mi-fix-test`,
  pointed `mi-legislation`'s workflow at it, dispatched — but the first image was built `arm64`-only
  (local machine's native arch) and every attempt failed instantly with `exec format error` on
  GitHub's `linux/amd64` runners, never even reaching `legislature.mi.gov` (nothing to do with the
  DigiCert fix itself). Rebuilding with `docker buildx build --platform linux/amd64` and
  re-dispatching. `fix/mi-digicert-intermediate` (on `tamara-builds/openstates-scrapers`).
- **AR, NV, OR, MN, CT, OH, PA — ✅ all confirmed healthy**, ready to promote out of
  `not-working.md` into `working-in-session.md`/`working-out-of-session.md`.
- **NM** — issue was already closed by the maintainer 07-02; no PR was ever actually filed
  despite the doc claiming one was "ready." Nothing to do.

## Harder — needs a proper deep-dive (not a quick win)

- **VA — issue [#1385](https://github.com/openstates/issues/issues/1385)**: `csv_bills` crashes
  with `KeyError: ' '` on the 2026 regular session's `HISTORY.CSV` — a row has a blank chamber
  code. Zero engagement, never touched. Worth investigating — VA's GitHub Actions workflow has
  been disabled since 2026-04-01 for an "unclear reason," and this crash is a plausible
  explanation nobody's connected yet. Candidate for the same fix-and-test pattern as GA/AZ/NH.
- **NE** — only ever retried through tinyproxy, never genuine self-hosted. Not started.
- **FL** — third fix (single-bill failures) on `fix/fl-streaming-bills`, not yet verified live —
  its verification run got blocked by the shrink-guard bug (now fixed) and was cancelled. Needs
  a fresh live-test run now that the shrink-guard issue is out of the way.

## Reference

- `not-working.md` — full per-state problem list + session status
- `working-in-session.md` / `working-out-of-session.md` — the healthy baseline (7 states ready
  to move in from the list above)
- `upstream-pr-todo.md` — PRs filed with OpenStates, waiting on merge
- `pending-branches.md` — full detail on every branch above, with commit SHAs and run IDs
