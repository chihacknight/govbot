# State Status Reference

One row per jurisdiction, covering scrape/extraction health, session timing, and bill-text
format — the operational data needed to decide when a scraper should be turned on or off, and
what's currently broken vs. just out of session.

**This is a living document — most rows below are placeholders (`TBD`) to be filled in over
time, not a claim that data is missing or wrong.** The columns that are already fully populated
(Machine Readable Bill Text) come straight from `actions/scrape/docs/bill-format-audit.md`
(last updated 2026-07-02) — check there for source domains and detail.

## Why this exists

Turning scrapers on/off by session is already automatable in principle: each state's
`chn-openstates-scrape.yml` config has a `template` field that flips between `openstates-scrape`
(active) and `openstates-scrape-paused` (paused). An automated version of this
(`check-sessions.py`, driven by the OpenStates API's own session dates) is **currently disabled**
— its dates were repeatedly wrong and caused false "frozen" alarms. Until that's trustworthy
again, session dates here should be **manually verified**, not copied from the API, and the
"Should be" column is the actual signal to act on: does the verified session status match what
the config is currently set to?

## Status code legend

Reuses the failure taxonomy already produced by `scrape.sh` / `scrape-summary.json` and
referenced in `scraper-status.md`, so a row here can be copy-pasted straight from an automated
run summary instead of re-classified into a separate scheme.

| Code | Meaning |
|------|---------|
| ✅ | Working, no known issue |
| `N1`/`N3` | Active block (connection refused / reset) |
| `N2` | Connectivity (timeout, connection aborted) |
| `N4` | DNS failure |
| `H1` | Active block (HTTP 403) |
| `H2` | Auth failure (401) |
| `H3` | Rate limited (429) |
| `H4` | Server down (503) |
| `S1`/`S2` | Out of session (soft failure — expected, not broken) |
| `S3` | Session config mismatch |
| `S4`/`S5` | Site structure changed (upstream scraper needs a fix) |
| `S6` | OCD validation failure |
| `P1` | Shrinking output — fresh scrape produced fewer files than committed; guard refused to overwrite |
| `UNKNOWN` | Failed, cause not yet classified |
| `TBD` | Not yet checked |

## Reference table

| State | Current Session | Session Dates (verified) | Config | Should Be | Scraper | Text-Extraction | Machine-Readable Bill Text | Bill Count (current session) | Last Verified / Notes |
|---|---|---|---|---|---|---|---|---|---|
| AK | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| AL | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| AR | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | — |
| AZ | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | Long-standing `S3` cookie bug, PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) open, confirmed self-hosting does NOT fix it |
| CA | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| CO | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| CT | TBD | TBD | TBD | TBD | `P1` | TBD | ❌ (pdf only) | TBD | Hit shrink-guard 2026-07-21 — duplicate bill objects under different UUIDs (1.4-2.9x inflation), single-session not multi-session. Cleared and re-dispatched same day per scraper-status.md; not independently re-verified since (see MT for a case where a similar 'fixed' claim didn't fully hold up). Self-hosted required (Azure IP block on FTP server) |
| DC | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| DE | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (pdf, text/html) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| FL | 2026 Regular (+ 2026F special) | TBD | Self-hosted | Active | 🔧 in progress | TBD | ❌ (pdf only) | TBD | 2026-07-23/24: found two distinct bugs — `flhouse.gov` bot detection (PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724), issue [#1386](https://github.com/openstates/issues/issues/1386)) and a separate missing-timeout hang on the same host. Both fixes pushed, awaiting maintainer review. Self-hosted required; tinyproxy path untested until amd64 image fix lands. |
| GA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| GU | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| HI | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (no bills yet as of audit) | TBD | WAF block (Cloudflare) per bill-format-audit (Scraper ✅ per 2026-07-21 audit) |
| IA | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| ID | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| IL | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (pdf, text/html) | TBD | Self-hosted required (Azure IPs served different content, broke title xpath) (Scraper ✅ per 2026-07-21 audit) |
| IN | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| KS | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (pdf, text/html) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| KY | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| LA | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| MA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Self-hosted required (malegislature.gov blocks Azure); known runner-uptime gaps have caused missed nights |
| MD | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| ME | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| MI | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | Fails on every hosting path — `legislature.mi.gov` doesn't serve its full TLS cert chain, not a proxy/hosting issue |
| MN | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html) | TBD | — |
| MO | TBD | TBD | TBD | TBD | `P1` | TBD | ❌ (pdf only) | TBD | Hit shrink-guard 2026-07-21 — duplicate bill objects under different UUIDs (1.4-2.9x inflation), single-session not multi-session. Cleared and re-dispatched same day per scraper-status.md; not independently re-verified since (see MT for a case where a similar 'fixed' claim didn't fully hold up). |
| MP | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Blank-title OCD validation crash (`S6`), fix identified, not yet filed upstream |
| MS | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| MT | 2025 (only active session upstream — worth double-checking this is still correct given MT meets biennially) | TBD | Not self-hosted (plain GitHub-hosted) | TBD | `P1` (disputed) | 🔧 fixed 2026-07-24 | ❌ (no version links) | ~4,495 (disputed — see notes) | 2026-07-23/24: shrink-guard blocking scrapes since 07-21; investigated at length, real duplication confirmed (~1-2%) but doesn't explain the gap between the committed baseline (~6,900 unique estimated) and format/fresh-scrape output (4,495) — cause still open. Separately, fixed the org-wide broken extract-text restart mechanism (`PAT_WORKFLOW_TRIGGER` → GitHub App token, matching scrape→format pattern); applied to this repo only so far, worth rolling out to all states. |
| NC | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Self-hosted required — was NOT an IP block, was frozen ~7 months for a different reason, see scraper-health.md (Scraper ✅ per 2026-07-21 audit) |
| ND | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| NE | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| NH | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no version links) | TBD | Site blocks scraping 6am-9pm ET — schedule around this, not a real block |
| NJ | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| NM | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | Intermittent FTP server issue (confirmed via direct `curl` testing), not a permanent dead end, not hosting-related |
| NV | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Meets biennially, no regular session until 2027 — low bill count is expected, not broken |
| NY | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| OH | TBD | TBD | TBD | TBD | `P1` | TBD | ✅ (pdf, text/html) | TBD | Hit shrink-guard 2026-07-21 — duplicate bill objects under different UUIDs (1.4-2.9x inflation), single-session not multi-session. Cleared and re-dispatched same day per scraper-status.md; not independently re-verified since (see MT for a case where a similar 'fixed' claim didn't fully hold up). |
| OK | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| OR | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| PA | TBD | TBD | TBD | TBD | `P1` | TBD | ✅ (pdf, text/html, msword) | TBD | Hit shrink-guard 2026-07-21 — duplicate bill objects under different UUIDs (1.4-2.9x inflation), single-session not multi-session. Cleared and re-dispatched same day per scraper-status.md; not independently re-verified since (see MT for a case where a similar 'fixed' claim didn't fully hold up). |
| PR | TBD | TBD | TBD | TBD | `P1` | TBD | ✅ (msword) | TBD | Hit shrink-guard 2026-07-21 — duplicate bill objects under different UUIDs (1.4-2.9x inflation), single-session not multi-session. Cleared and re-dispatched same day per scraper-status.md; not independently re-verified since (see MT for a case where a similar 'fixed' claim didn't fully hold up). |
| RI | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| SC | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, docx) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| SD | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| TN | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| TX | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html, pdf) | TBD | Blocks GitHub Actions IP ranges at the firewall — self-hosted only, see `tx-backfill-runbook.md` (Scraper ✅ per 2026-07-21 audit) |
| USA | TBD | TBD | TBD | TBD | `P1` | TBD | ✅ (text/xml, pdf) | TBD | Hit shrink-guard 2026-07-21 — duplicate bill objects under different UUIDs (1.4-2.9x inflation), single-session not multi-session. Cleared and re-dispatched same day per scraper-status.md; not independently re-verified since (see MT for a case where a similar 'fixed' claim didn't fully hold up). |
| UT | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/xml, pdf) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| VA | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (no bills yet as of audit) | TBD | Workflow disabled since 2026-04-01, reason unclear — worth investigating (Scraper ✅ per 2026-07-21 audit) |
| VI | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Source server itself offline (`billtracking.legvi.org:8082`) — not a code problem, fails on every hosting path |
| VT | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| WA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no version links) | TBD | — |
| WI | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (pdf, text/html) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |
| WV | TBD | TBD | TBD | TBD | ✅ | TBD | ✅ (text/html) | TBD | Self-hosted required (same Azure-block pattern as IL/CT/HI/MA/TN) (Scraper ✅ per 2026-07-21 audit) |
| WY | TBD | TBD | TBD | TBD | ✅ | TBD | ❌ (pdf only) | TBD | Scraper ✅ per 2026-07-21 full 56-state audit (scraper-status.md) — not re-verified since; other columns still unchecked |

## Hosting Path History (audited 2026-07-24)

For every state without a confirmed-healthy scraper, pulled the last 10 scrape workflow runs and
determined the **actual** hosting path each one used (not what config claims — verified directly
from each run's job log: presence of a `Hosted Compute Agent`/`Azure Region` block means
GitHub-hosted, `USE_PROXY: true` within that splits Tinyproxy from plain; its absence entirely
means it ran on the real MacBookPro runner). `cancelled` runs are excluded entirely — those mean
the runner/proxy was never available to pick up the job at all, not that a path was tried and
failed. Only non-`fl`/`mt` states are P1-noted from the same 07-21 audit as the main table above.

| State | Paths Tried | Clean Runs (per path) | Best Path So Far | Notes |
|---|---|---|---|---|
| AR | Tinyproxy, MacBookPro | Tinyproxy 6/6, MacBookPro 0/1 | Tinyproxy | MacBookPro has only one real (non-cancelled) data point, and it failed — not enough to judge that path yet |
| AZ | Tinyproxy, MacBookPro, GitHub-hosted-plain | 0/6, 0/1, 0/2 | None — fails everywhere | `S3_SESSION_CONFIG` on all three paths identically — confirms not hosting-related, PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) open |
| CT | Tinyproxy, MacBookPro, GitHub-hosted-plain | Tinyproxy 4/5, MacBookPro 2/3, GitHub-hosted-plain 0/1 | Tinyproxy or MacBookPro | GitHub-hosted-plain's one real data point was `S1_OUT_OF_SESSION` — a soft/expected failure, not evidence the path itself is broken |
| FL | Tinyproxy, MacBookPro | 0/6, 0/3 | None confirmed yet | See dedicated FL section above — two distinct bugs found and fixed 2026-07-23/24, awaiting merge |
| GA | GitHub-hosted-plain only | 2/10 (+4 no clear signal) | Only path tried | Never tried Tinyproxy or MacBookPro |
| MA | MacBookPro only (2 real runs) | 0/2 | Neither confirmed | No real Tinyproxy data at all; both real MacBookPro runs failed. Known runner-uptime gaps explain most of this state's `cancelled` runs |
| MI | Tinyproxy, MacBookPro | 0/6, 0/2 | None — fails everywhere | Root cause confirmed unrelated to hosting: `legislature.mi.gov` doesn't serve its full TLS cert chain, fails identically on every path including genuine self-hosted |
| MN | GitHub-hosted-plain only | 5/10 (+3 no clear signal) | Only path tried | Never tried Tinyproxy or MacBookPro |
| MO | GitHub-hosted-plain only | 4/9 (+2 no clear signal) | Only path tried | Repeated `P1` shrink-guard hits, not a hosting problem; MacBookPro's only entry was cancelled (discarded) |
| MP | GitHub-hosted-plain only | 0/10 | None — fails every time | Never tried Tinyproxy or MacBookPro. `S6_VALIDATION`/`H3_RATE_LIMITED` — known blank-title crash + rate limiting |
| MT | GitHub-hosted-plain, MacBookPro (1 real run) | GitHub-hosted-plain 3/9, MacBookPro 1/1 | MacBookPro (only one data point, but clean) | GitHub-hosted-plain repeatedly hits the disputed `P1` shrink-guard — see project_docs/state-problems.md for full MT writeup |
| NE | Tinyproxy, MacBookPro | 0/5, 0/3 | None confirmed yet | Both paths failing — Tinyproxy hits shrink-guard/rate-limit, MacBookPro's 3 real runs all failed outright, worth investigating |
| NH | GitHub-hosted-plain, MacBookPro (1 real run) | 0/8, 0/1 | None — fails everywhere | `H3_RATE_LIMITED` on both paths — known site blocks scraping 6am-9pm ET, likely a scheduling/timing issue rather than hosting |
| NM | Tinyproxy, MacBookPro | 0/6, 0/2 | None confirmed yet | Known intermittent FTP server issue (confirmed via direct `curl` testing), not hosting-related |
| NV | Tinyproxy, MacBookPro (1 real run) | Tinyproxy 5/5, MacBookPro 0/1 | Tinyproxy | Strong Tinyproxy track record; MacBookPro's one real run had no clear success/fail signal |
| OH | Tinyproxy, MacBookPro | Tinyproxy 2/5, MacBookPro 1/2 | Mixed, no clear winner | Both paths hit shrink-guard/failures sometimes |
| OR | GitHub-hosted-plain only | 6/10 (+4 no clear signal) | Only path tried | Good track record on the only path tried |
| PA | Tinyproxy, MacBookPro | Tinyproxy 2/5 (3 unclear), MacBookPro 1/2 | Mixed, no clear winner | Known duplicate-cruft/shrink-guard history, see scraper-status.md |
| PR | GitHub-hosted-plain, MacBookPro (1 real run) | GitHub-hosted-plain 2/9, MacBookPro 1/1 | MacBookPro (only one data point, but clean) | GitHub-hosted-plain repeatedly hits `P1` shrink-guard |
| USA | Tinyproxy, MacBookPro | Tinyproxy 3/5, MacBookPro 0/2 | Tinyproxy | MacBookPro's 2 real runs both failed outright |
| VI | Tinyproxy, MacBookPro (1 real run) | 0/6, 0/1 | None — fails everywhere | Source server itself offline (`billtracking.legvi.org:8082`) — confirmed not a hosting problem |
| WA | GitHub-hosted-plain only | 5/10 (+4 no clear signal) | Only path tried | Never tried Tinyproxy or MacBookPro |

## Related docs

- `actions/scrape/docs/bill-format-audit.md` — source for the Machine-Readable column, full format/domain detail
- `actions/scrape/docs/scraper-health.md` / `error-tracking.md` — incident-log style history, not a flat reference
- `actions/pipeline-manager/chn-openstates-scrape.yml` — the actual per-state config this doc should stay consistent with (`runner`, `template`, `scrape_cron`)
- `actions/pipeline-manager/check-sessions.py` — the disabled session-pause automation this doc's session columns are meant to eventually feed
