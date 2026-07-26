# Next Steps

## 🔁 Scraper Audit — In Progress (2026-07-02)

**Goal:** Review scraper logs for every jurisdiction, document findings, then file OpenStates issues/PRs.

**Process (per state):**

1. Run or pull scraper logs
2. Check bill count against `bill-counts-by-jurisdiction.md`
3. Look for errors, warnings, data gaps, unexpected counts
4. Update `error-tracking.md` (status, bill count, notes)
5. Update `bill-counts-by-jurisdiction.md` (correct truncated counts, flag gaps)
6. Add to `openstates-responses.md` if there's a finding worth filing upstream
7. Add to `TODO.md` if an OpenStates issue needs to be filed

**States completed:** NM, LA, UT, NV, IN, VI, OR, GU, MP, AK, WY, SD, CO, ID, VT, NE, ND, DE, MT, KS, AL, KY, OH, WI, DC, NC, FL, AR, CA, TN, SC, MI, ME, MD

**States remaining (in order):** NH, WV, IL, HI, MS, MO, OK, TX, WA, PR, PA, RI, IA, CT, MA, GA, USA, NY, MN, NJ — plus AZ and VA (broken, skip or verify PR status)

---

## Immediate (this week)

td: `PAT_WORKFLOW_TRIGGER` still not set as an org secret on `govbot-data` — confirmed live 2026-07-21 on NH's `extract-text.yml`: `check-and-restart` now correctly triggers (PR #83's `if:` fix works) but the actual `gh workflow run` retrigger step fails with an empty `GH_TOKEN`. Needs the GitHub web UI (same `admin:org` wall as `PROXY_URL`), or better, switch this step to the GitHub App token approach already used for scrape→format dispatch instead of a second long-lived PAT.

td: NH hours only, still failed. ugh
td: tx wtf>
td: IL? :(

### IL backfill — blocked on ILGA.gov HTML change (again)

Manual scrape triggered 2026-07-03 ([run #28638909079](https://github.com/govbot-openstates-scrapers/il-legislation/actions/runs/28638909079)) failed: `S5_SITE_STRUCTURE` (ValueError/IndexError). ILGA.gov changed HTML again — a fix landed in openstates-scrapers on 2026-07-01 ("site changed bill title element HTML") but the Docker image may not have rebuilt yet, or the site changed a second time.

**Next steps:**

- Check whether latest `openstates/scrapers:latest` Docker image includes the 2026-07-01 commit
- If yes: another ILGA.gov change happened; file a new issue and PR
- If no: wait for Docker rebuild, re-trigger manual scrape
- Also file PR to fix `end_date: "2025-05-31"` → `"2026-05-31"` and `active: False` on 104th Regular Session

### Session date audit — 2026-07-02

Full audit of OpenStates session end_dates vs LegiScan 2026 reference. Full analysis in `actions/scrape/docs/session-audit-2026.md`.

**OpenStates PRs to file:**

- 🔴 **IL** — `end_date: "2026-05-31"`, `active: False` on 104th Regular Session (year off by 1, name has no year range so auto-correction can't fix it)
- 🔴 **MS** — no 2026 session entry exists in OpenStates at all; needs 2026 Regular Session added
- 🟡 **AZ** — 57th Legislature end_date should be 2026-06-13, not 2026-04-25
- 🟡 **AK, IA, KS, ME, SC, VT** — add correct 2026 end_dates so `corrected_end_date()` stops over-extending to Dec 31 (currently holding them in `openstates-scrape` active mode past their spring adjournment)
- 🟢 **NC** — update end_date once NC adjourns (session still active, LegiScan estimates Aug 31)

**Audit tool fixes (this repo):**

- `find_primary_session` in `check-sessions.py`: add `start_date.year <= ref_year` to exclude future sessions (fixes FL, UT false positives)
- `find_primary_session`: broaden filter to exclude session names containing "Special" or "Extraordinary" (fixes VA, GA, MN false positives)
- Consider restricting `corrected_end_date()` to only fire when `os_raw.month == 12 and os_raw.day == 31` (the specific DC/MI/PA pattern it was designed for)

Merge PR #44 — docs cleanup branch is open and ready: PR #44

Watch the first automated check-sessions run — it fires at 6 AM UTC on the next weekday. Check check-sessions.yml to confirm it ran cleanly end-to-end (API call → config update → apply to state repos).

Watch Sunday's full reconciliation — first Sunday run will apply all 56 state repos regardless of changes. Good smoke test that APPLY_TOKEN has correct scope across all repos.

Near-term

Fix macOS `tar --mode=755` incompatibility in `action.yml` — affects all self-hosted runners on Mac (confirmed on FL and TN runners). GNU tar flag not supported by BSD tar. Scrape succeeds but tarball creation fails; workflow falls back to prior release tarball. Fix: detect OS or use portable tar flags.

File OpenStates issues (all identified 2026-07-02, analysis in `tamara-notes/openstates-responses.md`):

- **WY** — scraper misses `enrolled`/`inactive` bills (HB0001, SF0001, SF0002 — the entire point of WY's budget session)
- **IN** — missing all Senate Bills and HB1001-1010 for 2026 session
- **UT + ID** — `minidata`/`billlist.jsp` endpoint only returns active bills; completed sessions get 1-3 bills instead of hundreds
- **MP** — empty title on HCommRes 24-6 (`legID=20113`) crashes OCD validation every run; fix: title fallback in scraper
- **GU** — each bill saved ~3x per run with different UUIDs; format action deduplicates but wastes HTTP requests
- **FL** — bot-detection returns HTTP 200 with challenge page; `accept_response` rejects it; fails even from home IP
- **AR** — session ID mismatch: scraper filters FTP rows for `2026S1` but `ChamberActions.txt` has `2025R`; two entire 2026 sessions missing
- **MD** — 2026 session has only 531 bills (HB tops at 0298, SB at 0231); 2025 had 2,617+; scraper runs in 7s suggesting list endpoint returns subset only (same pattern as UT/ID/WY)

File OpenStates issue about the systemic biennium end_date truncation bug — affects DC, MI, NC, PA (all with the same pattern: end_date stuck in year 1 of a 2-year session). Worth filing once so it's tracked upstream, even if the workaround in check-sessions.py handles it fine for now.

Node.js 20 deprecation — GitHub Actions will eventually force Node 24. The bumps needed are documented in actions/scrape/error-tracking.md — it's not urgent yet but is a known future failure point.

Someday / separate tasks

NV historical backfill — session 83 data exists in old windy-civi-pipelines/nv-data-pipeline in a different format. Not urgent, separate task.

VA and VI mystery — both have had workflows disabled since 2026-04-01 with no explanation. Worth investigating when you have bandwidth.

---
