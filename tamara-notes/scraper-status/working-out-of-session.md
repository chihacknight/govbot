# Working, currently out of session (30 states)

Scraper confirmed `✅` in the 2026-07-21 full 56-state audit, and the state is currently
**out of session** per LegiScan's `session-calendar-2026.md` (as of 2026-07-13). Nothing to
do here — these are the boring, correct baseline. Listed so a state falling out of this doc
(into `not-working.md`) is easy to notice.

**Caveat:** "✅" here means *last verified* 2026-07-21, not continuously monitored — see
`not-working.md`'s header for the same caveat applied to the other bucket. A state can drift
out of this list without this doc being touched; check `docs/src/state-status-reference.md`
for anything more recent before trusting this blindly.

| State | Notes |
|---|---|
| AK | Session 34 (2025-2026 Legislature) — verified 2026-07-24: 856 bills in `govbot-data/ak-legislation`, matches LegiScan. No separate session identifier for the 5/21/2026 special session; AK's scraper models the whole 2-year Legislature as one session ("34"), so special-session bills are already captured, not a separate scrape target. |
| AL | — |
| CO | — |
| DE | — |
| HI | Scraper healthy, but text-extraction hits a Cloudflare WAF block (separate issue, not a scraper problem). |
| IA | — |
| ID | — |
| IL | Self-hosted required (Azure IPs served different content, broke title xpath). |
| IN | — |
| KS | — |
| KY | — |
| LA | — |
| MD | — |
| ME | — |
| MS | — |
| ND | — |
| NH | Data side confirmed 2026-07-26: 1,387 real bill directories for the 2026 session in `govbot-data/nh-legislation`, matches expectations. Session itself ended 2026-06-04/06-30 (source disagrees by a few weeks, see `session-dates-comparison.md`), so out-of-session is correct. **Still listed in `not-working.md` too** — the real 6am-9pm ET block window (confirmed from NH's own site logs) is a separate, still-open issue independent of this data confirmation; don't move this row without resolving that. |
| NY | — |
| OK | — |
| RI | — |
| SC | — |
| SD | — |
| TN | — |
| TX | Self-hosted only — blocks GitHub Actions IP ranges at the firewall. See `tx-backfill-runbook.md`. |
| UT | — |
| VA | ✅ Re-verified 2026-07-26 — the "workflow disabled since 2026-04-01" claim in this doc was wrong. Workflow state is `active`, running successfully on its daily `schedule` trigger (confirmed via a 2026-07-25 run: 1,051 files, exit 0, no fallback). The `csv_bills` `KeyError: ' '` crash (issue [#1385](https://github.com/openstates/issues/issues/1385)) was already fixed upstream by [#5725](https://github.com/openstates/openstates-scrapers/pull/5725), merged 2026-07-08 — issue just needs a manual close. |
| VT | — |
| WI | — |
| WV | Self-hosted required (same Azure-block pattern as IL/CT/HI/MA/TN). |
| WY | — |
