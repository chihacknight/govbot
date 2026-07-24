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
| AK | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | — |
| AL | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| AR | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | — |
| AZ | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | Long-standing `S3` cookie bug, PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) open, confirmed self-hosting does NOT fix it |
| CA | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | — |
| CO | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| CT | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Self-hosted required (Azure IP block on FTP server) |
| DC | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| DE | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | — |
| FL | 2026 Regular (+ 2026F special) | TBD | Self-hosted | Active | 🔧 in progress | TBD | ❌ (pdf only) | TBD | 2026-07-23/24: found two distinct bugs — `flhouse.gov` bot detection (PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724), issue [#1386](https://github.com/openstates/issues/issues/1386)) and a separate missing-timeout hang on the same host. Both fixes pushed, awaiting maintainer review. Self-hosted required; tinyproxy path untested until amd64 image fix lands. |
| GA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| GU | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| HI | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | WAF block (Cloudflare) per bill-format-audit |
| IA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| ID | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| IL | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | Self-hosted required (Azure IPs served different content, broke title xpath) |
| IN | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| KS | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | — |
| KY | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| LA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| MA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Self-hosted required (malegislature.gov blocks Azure); known runner-uptime gaps have caused missed nights |
| MD | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| ME | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| MI | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | Fails on every hosting path — `legislature.mi.gov` doesn't serve its full TLS cert chain, not a proxy/hosting issue |
| MN | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html) | TBD | — |
| MO | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| MP | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Blank-title OCD validation crash (`S6`), fix identified, not yet filed upstream |
| MS | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | — |
| MT | 2025 (only active session upstream — worth double-checking this is still correct given MT meets biennially) | TBD | Not self-hosted (plain GitHub-hosted) | TBD | `P1` (disputed) | 🔧 fixed 2026-07-24 | ❌ (no version links) | ~4,495 (disputed — see notes) | 2026-07-23/24: shrink-guard blocking scrapes since 07-21; investigated at length, real duplication confirmed (~1-2%) but doesn't explain the gap between the committed baseline (~6,900 unique estimated) and format/fresh-scrape output (4,495) — cause still open. Separately, fixed the org-wide broken extract-text restart mechanism (`PAT_WORKFLOW_TRIGGER` → GitHub App token, matching scrape→format pattern); applied to this repo only so far, worth rolling out to all states. |
| NC | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Self-hosted required — was NOT an IP block, was frozen ~7 months for a different reason, see scraper-health.md |
| ND | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| NE | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| NH | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no version links) | TBD | Site blocks scraping 6am-9pm ET — schedule around this, not a real block |
| NJ | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | — |
| NM | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | Intermittent FTP server issue (confirmed via direct `curl` testing), not a permanent dead end, not hosting-related |
| NV | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Meets biennially, no regular session until 2027 — low bill count is expected, not broken |
| NY | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | — |
| OH | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | — |
| OK | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| OR | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| PA | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html, msword) | TBD | — |
| PR | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (msword) | TBD | — |
| RI | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| SC | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, docx) | TBD | — |
| SD | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | — |
| TN | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| TX | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html, pdf) | TBD | Blocks GitHub Actions IP ranges at the firewall — self-hosted only, see `tx-backfill-runbook.md` |
| USA | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/xml, pdf) | TBD | — |
| UT | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/xml, pdf) | TBD | — |
| VA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no bills yet as of audit) | TBD | Workflow disabled since 2026-04-01, reason unclear — worth investigating |
| VI | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | Source server itself offline (`billtracking.legvi.org:8082`) — not a code problem, fails on every hosting path |
| VT | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |
| WA | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (no version links) | TBD | — |
| WI | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (pdf, text/html) | TBD | — |
| WV | TBD | TBD | TBD | TBD | TBD | TBD | ✅ (text/html) | TBD | Self-hosted required (same Azure-block pattern as IL/CT/HI/MA/TN) |
| WY | TBD | TBD | TBD | TBD | TBD | TBD | ❌ (pdf only) | TBD | — |

## Related docs

- `actions/scrape/docs/bill-format-audit.md` — source for the Machine-Readable column, full format/domain detail
- `actions/scrape/docs/scraper-health.md` / `error-tracking.md` — incident-log style history, not a flat reference
- `actions/pipeline-manager/chn-openstates-scrape.yml` — the actual per-state config this doc should stay consistent with (`runner`, `template`, `scrape_cron`)
- `actions/pipeline-manager/check-sessions.py` — the disabled session-pause automation this doc's session columns are meant to eventually feed
