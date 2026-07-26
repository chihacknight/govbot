# Working, currently out of session (39 states)

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
| AR | ✅ Confirmed clean 07-21 (6 files, matches 2 genuinely-live 2026S1 bills). |
| CO | — |
| CT | ✅ Confirmed clean 2026-07-24 (identifier check: 1,283 bill files, 1,283 distinct, zero dupes). |
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
| MN | ✅ Re-verified 2026-07-24 (10,594 files, 10,590 bill files, 10,587 distinct identifiers, only 3 stray dupes) — the 07-21 `N4_DNS_FAILURE` was genuinely transient. |
| MO | ✅ Confirmed clean 2026-07-25 — shrink-guard identifier-check fix landed 3,158 real bills, replacing a 22,015-file bloated baseline. |
| MS | — |
| MT | ✅ Confirmed clean 2026-07-25 — shrink-guard identifier-check fix landed 4,495 real bills (twice now), replacing a 37,555-file bloated baseline (56% was stale duplicates). |
| ND | — |
| NH | Data side confirmed 2026-07-26: 1,387 real bill directories for the 2026 session in `govbot-data/nh-legislation`, matches expectations. Session itself ended 2026-06-04/06-30 (source disagrees by a few weeks, see `session-dates-comparison.md`), so out-of-session is correct. **Still listed in `not-working.md` too** — the real 6am-9pm ET block window (confirmed from NH's own site logs) is a separate, still-open issue independent of this data confirmation; don't move this row without resolving that. |
| NV | ✅ Looked fine 07-21 (64 files, matches biennial no-regular-session-until-2027 expectation). Separate known ~1,000+ bill backfill gap from the 2025 session (one-time TODO). |
| NY | — |
| OK | — |
| OR | ✅ Looked fine 07-21 (308 files, consistent with 07-02 baseline). |
| PR | ✅ Confirmed clean 2026-07-25 — shrink-guard identifier-check fix landed cleanly, replacing a 23,866-file bloated baseline (only 5,115 were real). |
| RI | — |
| SC | — |
| SD | — |
| TN | — |
| TX | Self-hosted only — blocks GitHub Actions IP ranges at the firewall. See `tx-backfill-runbook.md`. |
| UT | — |
| VA | ✅ Re-verified 2026-07-26 — the "workflow disabled since 2026-04-01" claim in this doc was wrong. Workflow state is `active`, running successfully on its daily `schedule` trigger (confirmed via a 2026-07-25 run: 1,051 files, exit 0, no fallback). The `csv_bills` `KeyError: ' '` crash (issue [#1385](https://github.com/openstates/issues/issues/1385)) was already fixed upstream by [#5725](https://github.com/openstates/openstates-scrapers/pull/5725), merged 2026-07-08 — issue just needs a manual close. |
| VT | — |
| WA | ✅ Confirmed clean 2026-07-25 — was frozen since 2026-07-24T04:06:15Z (silently reporting "success" while landing zero new data). Shrink-guard identifier-check fix unfroze it, replacing a 6,153-file baseline (only 3,411 were real). |
| WI | — |
| WV | Self-hosted required (same Azure-block pattern as IL/CT/HI/MA/TN). Filed and closed issue [#1380](https://github.com/openstates/issues/issues/1380) 2026-07-26 — our diagnosis (XPath broken after site redesign) was wrong; maintainer showed current upstream code correctly gets 2,975 bills, and our proposed fix would have reverted an intentional prior fix (#5703). The low count we saw is our own infra issue, matching this Azure-block pattern. |
| WY | — |
