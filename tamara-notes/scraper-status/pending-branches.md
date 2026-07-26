# Pending local branches

Live-tracked, not chronological — update in place as branches move, don't just append.
Different from `upstream-pr-todo.md` (that's for work already merged locally but waiting on
an OpenStates PR to merge); this is for our own branches still mid-investigation, on either
the `govbot` repo or the `tamara-builds/openstates-scrapers` fork.

## govbot repo

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
| MA | 50,183 files (worst bloat found, ~4.5x) | ~11,123 bills expected | 🔄 still running (self-hosted, ~11hr typical) as of merge time |

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

### fix/nh-rate-limit — 🔄 waiting on tonight's automatic scheduled run

- Adds `settings = dict(SCRAPELIB_RPM=20)` to `scrapers/nh/__init__.py`.
- Only matters once `fix/nh-skip-fastmode` is live (already is, merged) — without dropping
  `--fastmode`, this setting is silently ignored regardless.
- **Not deployed anywhere NH's real workflow uses.** This branch lives only on the
  `tamara-builds/openstates-scrapers` fork, never merged upstream, and NH's workflow was never
  pointed at a custom image containing it (unlike AZ's `ghcr.io/tamara-builds/openstates-
  scrapers:az-fix-test`). NH still runs on stock `openstates/scrapers:latest`.
- **The clean re-test is already happening automatically, no manual dispatch needed.** NH's
  cron is `0 4 * * *` UTC (midnight ET) — outside the 6am-9pm ET block window — and its
  workflow points at `@main`, which already has the merged `--fastmode` skip. Tonight's
  scheduled run tests whether dropping `--fastmode` alone (framework's 60 RPM default) is
  sufficient, *without* this fork branch's extra `SCRAPELIB_RPM=20` cap.
- **Decision point once that run lands:** if it's clean, this branch's extra RPM cap may not
  even be necessary — don't bother building/deploying it. If NH still degrades the same gradual
  way as before, this branch's setting is probably needed after all, and building/pointing NH's
  workflow at a custom image (same pattern as AZ) is the next step. If it fails *instantly* the
  way the mid-block-window test did, that's an unrelated, still-unaddressed time-based block
  that neither this branch nor `fix/nh-skip-fastmode` addresses.
- **Also (commit `1b576734e`, 2026-07-24):** removed `verify=False` from all 11 request sites
  in `bills.py`. `gc.nh.gov`'s cert is currently valid (checked directly via `openssl s_client`
  and `curl -v` — Let's Encrypt, verifies clean, not expiring until Oct 2026), so this wasn't
  masking a real problem the way MI's cert issue is — looked like leftover dead code, no comment
  explaining it. Restores real cert verification, kills the `InsecureRequestWarning` log spam.
  Bundled into this branch since it's already touching NH's scraper; no separate test needed
  beyond the same re-test above (this part doesn't change scrape behavior, just verification).

### fix/mp-blank-title — ✅ confirmed working locally, 2 bugs fixed

- **Commits:** `b607f5692` (blank-title fallback) + `4f3af9c54` (bill_id spacing normalization,
  found while testing the first fix).
- **Root cause #1:** `HCommRes 24-6` has a genuinely empty title on `cnmileg.net`; OCD requires
  `minLength: 1`, so the scraper crashed on this exact bill every run and silently dropped every
  bill after it in iteration order (139 files = the partial haul before the crash). Fix: fall
  back to the bill's own identifier as the title when the site gives us nothing.
- **Root cause #2 (found via testing #1):** fixing the title crash surfaced a second, previously
  -hidden bug on the *same* bill — `cnmileg.net`'s "Number" cell renders it as `HCommRes24-6`
  (no space) instead of the normal `HB 123`-style spacing, breaking
  `bill_type_map[bill_id.split(" ")[0]]`'s lookup (`KeyError: 'HCommRes24-6'`). Only affects the
  lower-chamber path. Fix: normalize `bill_id` to always have a space between type prefix and
  number.
- **Local test:** clean full run, 317 bills (vs. the 139-file fallback previously), exit 0, zero
  tracebacks. Bonus: a *second* previously-unknown blank-title bill (`HCommRes 24-7`) also hit
  the fallback cleanly — the fix generalizes, not just hardcoded to the one known case.
- **Pushed:** yes, `origin/fix/mp-blank-title`
- **Next:** decide upstream PR vs. custom-image-in-the-meantime (same pattern as AZ/GA). Update
  `not-working.md`'s MP row once resolved either way.

### fix/mi-digicert-intermediate — 🔄 local docker test in progress, looking very promising

- **Commit:** `fc7e16c43` — bundles the missing DigiCert Global G2 TLS RSA SHA256 2020 CA1
  intermediate certificate into the image's CA store (`update-ca-certificates`), plus
  `REQUESTS_CA_BUNDLE` pointed at the updated system store (requests/urllib3 default to
  certifi's bundle, not the OS store, so the cert alone wouldn't have been enough).
- **Verified before building:** downloaded the exact matching intermediate from DigiCert's own
  repository (`cacerts.digicert.com`), confirmed via `openssl verify -untrusted <intermediate>
  <mi-leaf-cert>` that it actually completes the chain.
- **Verified after building:** inside the built image, both `curl` and Python `requests` now
  get a clean `HTTP 200` from `legislature.mi.gov` with default certificate verification (no
  `-k`/`verify=False`) — previously an `SSLCertVerificationError` on every path tried, including
  genuine self-hosted with zero proxy.
- **Live scrape test:** running now, 93+ bills saved and climbing as of last check — MI has
  never produced a single file before. Note: `mi/bills.py` itself separately passes
  `verify=False` on its own requests (an `InsecureRequestWarning` shows in the log) — unrelated
  to this fix, worth a follow-up cleanup later (same spirit as the NH `verify=False` removal)
  but not blocking this fix's validity, since the actual chain-verification failure this fixes
  happens at a different layer (TLS handshake) before request-level `verify=` is even relevant
  to *whether a connection succeeds* — it was failing to connect at all before.
- **Pushed:** yes, `origin/fix/mi-digicert-intermediate`
- **Next:** confirm the live test finishes clean (final bill count, exit 0, no tracebacks), then
  decide upstream PR vs. custom-image-in-the-meantime (same pattern as AZ/GA/MP). Update
  `not-working.md`'s MI row once resolved either way.

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
