# Morning check-in (2026-07-25)

Everything pending across the scraper-status folder, in one place — not just the upstream PR
follow-ups. Started 2026-07-24 evening; most of the shrink-guard saga resolved same night.

## Recurring maintenance (do this daily, not just once)

- **Clear out local Docker/scraper working files on Tamara's MacBook.** Local test runs (MI, MP,
  and others this session) leave scratch data, mounted volumes, and Docker images/containers
  behind — hogging disk space. Should be an actual daily habit, not a one-time cleanup, given
  how often local Docker tests get run as part of the fix-and-verify workflow. Related: chronic
  disk tightness already flagged in `not-working.md`'s "Resurfaced from historical docs" section
  (~3-4GB free even after a cleanup pass on 07-21) — that was about `apply.py`/template-rollout
  disk pressure specifically; this is the broader daily habit that would help prevent it
  recurring.

## Do first, time-sensitive

- **MP live GitHub Actions test in progress — first real (not just local) confirmation before
  any upstream PR.** Re-checked `fix/mp-blank-title` before trusting it: found the doc's claimed
  second commit (`4f3af9c54`, bill_id spacing normalization) had never actually been pushed —
  only the blank-title fallback existed on the branch. Added the missing fix (normalizes
  `HCommRes24-6` → `HCommRes 24-6` before the `bill_type_map` lookup that otherwise raises
  `KeyError`), confirmed still-live in production via a fresh `2026-07-25` run (crashes on
  `HCommRes 24-6` every single retry, same 139-file fallback every time — the bug is real and
  current, not stale). Built `ghcr.io/tamara-builds/openstates-scrapers:mp-fix-test` explicitly
  for `linux/amd64` this time (learning from MI's arch-mismatch mistake below — confirmed via
  `docker manifest inspect --verbose` before dispatching), pointed `mp-legislation`'s workflow at
  it, dispatched. **No upstream PR for MP/GA/NH until each has an actual confirmed live run** —
  explicit ask, not optional: local Docker tests aren't good enough on their own anymore.

## ✅ Commit-summary identifier-aware fix + 503/429 classifier fix — MERGED (PR #97, 2026-07-26)

`fix/commit-summary-identifier-aware` fixed two bugs found while reviewing USA's shrink-guard
test runs: (1) the job-summary's "Commit Content" label was still raw-file-count based (same
blind spot the shrink-guard itself used to have, now compares distinct bill identifiers), and
(2) a bare-substring `"503"`/`"429"` classifier bug (a cache-busting query-param timestamp on NH
coincidentally contained "503", mislabeling a plain `S1_OUT_OF_SESSION` as `H4_SERVER_DOWN`).
**All three test states confirmed clean:** MT (4,495 distinct bills flat, correctly labeled),
NH (correctly reclassified `S1_OUT_OF_SESSION`), USA (17,574 distinct bills flat despite 18,373
raw deletions vs. 9,229 insertions — exactly the false-alarm case this fix targets). MT/NH/USA's
workflows reverted to `@main` before merging. PR #97 squash-merged, branch deleted.

- **NH's 6am-9pm ET block window is still real** (confirmed from NH's own site logs) — the
  classifier fix above doesn't call that into question, it just fixed an unrelated mislabel.
  See `not-working.md`'s NH row.

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
- **GA — confirmed working locally only** (176 bills, 280 vote events, exit 0, zero tracebacks),
  **but the original `N2_CONNECTIVITY` crash hasn't recurred in any of the last 8 production runs**
  (07-21 through 07-26, all land exactly 460 files, zero tracebacks) — genuinely was a one-off
  transient blip. Can't get a live confirmation of the fix by watching production since production
  isn't currently failing; local test is the best evidence available. `fix/ga-subjects-resilience`.
  Still needs a live custom-image test before any upstream PR, same standard as MP.
- **MP — re-verified 2026-07-25/26, one bug was missing, now both are fixed and being live-tested.**
  See "Do first" above — the doc's claimed second fix was never actually pushed; added it, confirmed
  the underlying crash is still happening in production daily, built a correct `linux/amd64` image,
  dispatched a live test. `fix/mp-blank-title`.
- **NH — `--fastmode` fix confirmed sufficient, extra RPM cap likely unnecessary.** Checked both
  real completed scrapes since PR #95 merged (07-25 06:19 scheduled + 07-25 14:34 manual dispatch,
  the latter at 10:34 ET — inside the block window): both landed clean, 1,751 files, zero errors,
  `SCRAPE_TARBALL: present`. Per the original decision point, `fix/nh-rate-limit`'s extra
  `SCRAPELIB_RPM=20` cap probably isn't needed — dropping `--fastmode` alone did it. The
  `verify=False` cleanup (11 request sites, same branch) is still worth a small separate PR
  regardless. Separate time-based block (6am-9pm ET) still real and unaddressed by any of this.
- **MI — ❌ DigiCert theory abandoned, wrong diagnosis.** Checked three real production runs'
  full logs (07-22, 07-23, 07-25): zero occurrences of `SSLCertVerificationError` in any of them.
  `mi/bills.py` already calls with `verify=False` for the actual bill-detail host (raw IP,
  bypasses the cert chain entirely) — the missing DigiCert intermediate never actually blocks a
  live run. `fix/mi-digicert-intermediate` branch deleted, test image and workflow override
  removed. **Real root cause found:** `dateutil.parser.ParserError: Unknown string format:
  4/29/2025<` at `mi/bills.py:118` — a malformed date cell (stray unescaped `<`) on HB 4401,
  crashes every retry, every run since 07-23, discards partial data, falls back to nightly.
  Fixed on `fix/mi-date-parsing` (extracts just the date portion via regex before parsing, in
  both `scrape_actions` and `scrape_votes`). **Local Docker test clean 2026-07-26:** 3,884 real
  bills, 5,097 total files, zero tracebacks locally. **First live GitHub Actions test failed
  anyway** — a second, different bug on the same bill (HB 4401): an empty action description,
  `ScrapeValueError: '' is too short`, didn't reproduce locally. Fixed (`76b55a323`, skip
  empty-description action rows) and re-dispatched — this is exactly why the live-test standard
  matters, the local test alone would have missed this. Second live test in progress.
- **AR, NV, OR, MN, CT, OH, PA — ✅ all confirmed healthy**, ready to promote out of
  `not-working.md` into `working-in-session.md`/`working-out-of-session.md`.
- **NM** — issue was already closed by the maintainer 07-02; no PR was ever actually filed
  despite the doc claiming one was "ready." Nothing to do.

## Harder — needs a proper deep-dive (not a quick win)

- **VA — ✅ actually resolved, not a deep-dive candidate.** Corrected 2026-07-26: both halves of
  this entry were stale/wrong. The `csv_bills` `KeyError: ' '` crash (issue #1385) was already
  fixed upstream by [#5725](https://github.com/openstates/openstates-scrapers/pull/5725), merged
  2026-07-08 — just needs a manual issue close. The "workflow disabled since 2026-04-01" claim
  was also wrong — re-checked directly: workflow state is `active`, running successfully on its
  daily schedule (2026-07-25 run: 1,051 files, exit 0, no fallback). Nothing left to investigate
  here.
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
