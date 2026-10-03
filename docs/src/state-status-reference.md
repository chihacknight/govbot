# State Status Reference

One row per jurisdiction, covering session timing, config, bill-discovery volume, and
scraper health — the quick-glance signal for "is this state working right now." Redesigned
2026-10-03: the prior 9-column version (session dates, config/should-be, text-extraction,
bill-text format, bill count) stayed mostly `TBD` for over two months because no single
investigation naturally fills more than one or two of those columns at once. This version is
narrower and booleans-first, matching what's actually generated on a repeatable cadence.

**For the full story behind any row, check `tamara-notes/state-specific/` first** — see
`tamara-notes/state-specific/README.md` for the index of every state with a currently open
issue, one file per state for full chronological history. This table is the downstream
quick-glance summary; the narrative detail lives there, not duplicated here.

## Columns

- **In Session** — ✅/❌, from `tamara-notes/session-dates/session-calendar-2026.md` (manually
  verified against each state's own source, not blindly trusted from an API — see that
  file's own header for why).
- **Scraper Active** — ✅/❌, whether `chn-openstates-scrape.yml`'s `template` field for this
  state is `openstates-scrape` (✅) or `openstates-scrape-paused` (❌). Always current — pulled
  directly from that file, not hand-tracked.
- **Weekly Bill Count** — the sum of `new_bills_seen` (new distinct bills discovered) over the
  last 7 recorded days, fed automatically by
  `actions/openstates-scrape-audits/weekly-scraper-audit.py`'s `output/weekly_bill_counts.json`
  on its weekly cadence. `—` means no data yet for that state (not the same as a confirmed
  zero — check `days_with_data` in that file to tell the difference).
- **Scraper Healthy** — ✅/❌/🟡, whether the state's most recent scrape run completed without a
  masked failure (no `::warning::`/`::error::` annotation beyond benign out-of-session codes).
  🟡 marks a known issue with a fix already in flight. This is a point-in-time check, not
  itself automated yet — see "Last Checked" for when it was last verified, and the state's own
  file in `tamara-notes/state-specific/` (if one exists) for what "unhealthy" actually means.
- **Last Checked** — the date "Scraper Healthy" was last verified. A row with an old date here
  is the signal to re-check, not to trust the ✅/❌ as current.
- **Details** — link to the state's file in `tamara-notes/state-specific/`, if one exists.

For the specific failure-type codes (`N1`, `H3`, `S6`, etc.) behind a ❌, see
`tamara-notes/archived_docs/scrape-failure-types.md` or the state's own detail file — this
table only tracks the boolean.

## Reference table

Checked 2026-10-03 (all 56 rows, via a full review of the 9 then-active states plus the 47
then-paused states' last runs — see `tamara-notes/archived_docs/paused-states-audit-2026-10.md`
and `tamara-notes/state-specific/README.md` for the methodology). `Weekly Bill Count` reflects
the newly-added `new_bills_seen` signal, which only has 1-2 days of history for most states so
far (PR #188, merged 2026-10-02) — most `—` entries will fill in over the next week as the
histogram accumulates, not because nothing is happening.

| State | In Session | Scraper Active | Weekly Bill Count | Scraper Healthy | Last Checked | Details |
|---|---|---|---|---|---|---|
| AK | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| AL | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| AR | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| AZ | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| CA | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| CO | ❌ | ❌ | — | ❌ | 2026-10-03 | [`co.md`](../../tamara-notes/state-specific/co.md) |
| CT | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| DC | ✅ | ✅ | 11 | ✅ | 2026-10-03 | — |
| DE | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| FL | ❌ | ❌ | — | ❌ | 2026-10-03 | [`fl.md`](../../tamara-notes/state-specific/fl.md) |
| GA | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| GU | ✅ | ✅ | — | ❌ | 2026-10-03 | [`gu.md`](../../tamara-notes/state-specific/gu.md) |
| HI | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| IA | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| ID | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| IL | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| IN | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| KS | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| KY | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| LA | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| MA | ❌ | ❌ | — | ❌ | 2026-10-03 | [`ma.md`](../../tamara-notes/state-specific/ma.md) |
| MD | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| ME | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| MI | ✅ | ✅ | 16 | ✅ | 2026-10-03 | — |
| MN | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| MO | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| MP | ✅ | ✅ | — | ✅ | 2026-10-03 | — |
| MS | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| MT | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| NC | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| ND | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| NE | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| NH | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| NJ | ✅ | ✅ | 82 | ✅ | 2026-10-03 | — |
| NM | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| NV | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| NY | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| OH | ✅ | ✅ | 3 | ✅ | 2026-10-03 | — |
| OK | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| OR | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| PA | ✅ | ✅ | — | ❌ | 2026-10-03 | [`pa.md`](../../tamara-notes/state-specific/pa.md) |
| PR | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| RI | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| SC | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| SD | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| TN | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| TX | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| USA | ✅ | ✅ | — | ✅ | 2026-10-03 | [`usa.md`](../../tamara-notes/state-specific/usa.md) |
| UT | ❌ | ❌ | — | ❌ | 2026-10-03 | [`ut.md`](../../tamara-notes/state-specific/ut.md) |
| VA | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| VI | ✅ | ✅ | — | ❌ | 2026-10-03 | [`vi.md`](../../tamara-notes/state-specific/vi.md) |
| VT | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| WA | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| WI | ❌ | ❌ | — | ❌ | 2026-10-03 | [`wi.md`](../../tamara-notes/state-specific/wi.md) |
| WV | ❌ | ❌ | — | ✅ | 2026-10-03 | — |
| WY | ❌ | ❌ | — | ✅ | 2026-10-03 | — |

## Machine-Readable Bill Text (from the 2026-07-02 bill-format audit, not re-verified since)

Kept separate from the main table above — this is a one-time snapshot (file formats rarely
change) rather than a recurring health check, so it doesn't share the main table's cadence.

| State | Formats | State | Formats | State | Formats |
|---|---|---|---|---|---|
| AK | ✅ text/html, pdf | MA | ❌ pdf only | SC | ✅ text/html, docx |
| AL | ❌ pdf only | MD | ❌ pdf only | SD | ✅ text/html, pdf |
| AR | ❌ no bills yet as of audit | ME | ❌ pdf only | TN | ❌ pdf only |
| AZ | TBD | MI | ✅ pdf, text/html | TX | ✅ text/html, pdf |
| CA | ✅ text/html, pdf | MN | ✅ text/html | USA | ✅ text/xml, pdf |
| CO | ❌ pdf only | MO | ❌ pdf only | UT | ✅ text/xml, pdf |
| CT | ❌ pdf only | MP | ❌ pdf only | VA | ❌ no bills yet as of audit |
| DC | ❌ pdf only | MS | ✅ text/html, pdf | VI | ❌ pdf only |
| DE | ✅ pdf, text/html | MT | ❌ no version links | VT | ❌ pdf only |
| FL | ❌ pdf only | NC | ❌ pdf only | WA | ❌ no version links |
| GA | ❌ pdf only | ND | ❌ pdf only | WI | ✅ pdf, text/html |
| GU | ❌ pdf only | NE | ❌ pdf only | WV | ✅ text/html |
| HI | ❌ no bills yet as of audit | NH | ❌ no version links | WY | ❌ pdf only |
| IA | ❌ pdf only | NJ | ✅ text/html, pdf | | |
| ID | ❌ pdf only | NM | ❌ no bills yet as of audit | | |
| IL | ✅ pdf, text/html | NV | ❌ pdf only | | |
| IN | ❌ pdf only | NY | ✅ text/html, pdf | | |
| KS | ✅ pdf, text/html | OH | ✅ pdf, text/html | | |
| KY | ❌ pdf only | OK | ❌ pdf only | | |
| LA | ❌ pdf only | OR | ❌ pdf only | | |
| | | PA | ✅ pdf, text/html, msword | | |
| | | PR | ✅ msword | | |
| | | RI | ❌ pdf only | | |

## Hosting Path History (archival — audited 2026-07-24, not part of the current system)

For every state without a confirmed-healthy scraper as of that date, pulled the last 10 scrape
workflow runs and determined the **actual** hosting path each one used (not what config
claims — verified directly from each run's job log). Kept for historical reference; not
maintained going forward, and several of these findings (hosting path per state) have likely
drifted since — check `tamara-notes/state-specific/` for current status on any state listed
here.

| State | Paths Tried | Clean Runs (per path) | Best Path So Far | Notes |
|---|---|---|---|---|
| AR | Tinyproxy, MacBookPro | Tinyproxy 6/6, MacBookPro 0/1 | Tinyproxy | MacBookPro has only one real (non-cancelled) data point, and it failed — not enough to judge that path yet |
| AZ | Tinyproxy, MacBookPro, GitHub-hosted-plain | 0/6, 0/1, 0/2 pre-fix; ✅ clean on Tinyproxy post-fix | Tinyproxy | Not a hosting issue at all — was `--fastmode` cache poisoning, identical failure on every path was the tell. Fixed 2026-07-24, PR [#5742](https://github.com/openstates/openstates-scrapers/pull/5742) |
| CT | Tinyproxy, MacBookPro, GitHub-hosted-plain | Tinyproxy 4/5, MacBookPro 2/3, GitHub-hosted-plain 0/1 | Tinyproxy or MacBookPro | GitHub-hosted-plain's one real data point was `S1_OUT_OF_SESSION` — a soft/expected failure, not evidence the path itself is broken |
| FL | Tinyproxy, MacBookPro | 0/6, 0/3 | None confirmed yet | See `tamara-notes/state-specific/fl.md` — streaming/timeout/resilience fixes confirmed working since |
| GA | GitHub-hosted-plain only | 2/10 (+4 no clear signal) | Only path tried | Never tried Tinyproxy or MacBookPro |
| MA | MacBookPro only (2 real runs) | 0/2 | Neither confirmed | No real Tinyproxy data at all; both real MacBookPro runs failed. Known runner-uptime gaps explain most of this state's `cancelled` runs |
| MI | Tinyproxy, MacBookPro | 0/6, 0/2 | None — fails everywhere | Root cause confirmed unrelated to hosting: `legislature.mi.gov` doesn't serve its full TLS cert chain, fails identically on every path including genuine self-hosted |
| MN | GitHub-hosted-plain only | 5/10 (+3 no clear signal) | Only path tried | Never tried Tinyproxy or MacBookPro |
| MO | GitHub-hosted-plain only | 4/9 (+2 no clear signal) | Only path tried | Repeated `P1` shrink-guard hits, not a hosting problem; MacBookPro's only entry was cancelled (discarded) |
| MP | GitHub-hosted-plain only | 0/10 | None — fails every time | Never tried Tinyproxy or MacBookPro. `S6_VALIDATION`/`H3_RATE_LIMITED` — known blank-title crash + rate limiting |
| MT | GitHub-hosted-plain, MacBookPro (1 real run) | GitHub-hosted-plain 3/9, MacBookPro 1/1 | MacBookPro (only one data point, but clean) | GitHub-hosted-plain repeatedly hits the disputed `P1` shrink-guard — see `tamara-notes/archived_docs/state-problems.md` for full MT writeup |
| NE | Tinyproxy, MacBookPro | 0/5, 0/3 | None confirmed yet | Both paths failing — Tinyproxy hits shrink-guard/rate-limit, MacBookPro's 3 real runs all failed outright, worth investigating |
| NH | GitHub-hosted-plain, MacBookPro (1 real run) | 0/8, 0/1 | None — fails everywhere | `H3_RATE_LIMITED` on both paths — known site blocks scraping 6am-9pm ET, likely a scheduling/timing issue rather than hosting |
| NM | Tinyproxy, MacBookPro | 0/6, 0/2 | None confirmed yet | Known intermittent FTP server issue (confirmed via direct `curl` testing), not hosting-related |
| NV | Tinyproxy, MacBookPro (1 real run) | Tinyproxy 5/5, MacBookPro 0/1 | Tinyproxy | Strong Tinyproxy track record; MacBookPro's one real run had no clear success/fail signal |
| OH | Tinyproxy, MacBookPro | Tinyproxy 2/5, MacBookPro 1/2 | Mixed, no clear winner | Both paths hit shrink-guard/failures sometimes |
| OR | GitHub-hosted-plain only | 6/10 (+4 no clear signal) | Only path tried | Good track record on the only path tried |
| PA | Tinyproxy, MacBookPro | Tinyproxy 2/5 (3 unclear), MacBookPro 1/2 | Mixed, no clear winner | See `tamara-notes/state-specific/pa.md` for the current, very different diagnosis (confirmed IP-reputation block, not a duplicate/shrink-guard issue) |
| PR | GitHub-hosted-plain, MacBookPro (1 real run) | GitHub-hosted-plain 2/9, MacBookPro 1/1 | MacBookPro (only one data point, but clean) | GitHub-hosted-plain repeatedly hits `P1` shrink-guard |
| USA | Tinyproxy, MacBookPro | Tinyproxy 3/5, MacBookPro 0/2 | Tinyproxy | MacBookPro's 2 real runs both failed outright |
| VI | Tinyproxy, MacBookPro (1 real run) | 0/6, 0/1 | None — fails everywhere | See `tamara-notes/state-specific/vi.md` for the current diagnosis (confirmed genuine destination-server outage) |
| WA | GitHub-hosted-plain only | 5/10 (+4 no clear signal) | Only path tried | Never tried Tinyproxy or MacBookPro |

## Related docs

- `tamara-notes/state-specific/README.md` — the current index of every state with an open
  issue, with one file per state for full history (started 2026-10-03). The authoritative
  place to check/update first; this table is downstream of it, not the other way around.
- `actions/openstates-scrape-audits/` — the automated weekly/daily checks; the weekly one now
  also feeds this table's "Weekly Bill Count" column directly (`output/weekly_bill_counts.json`)
- `actions/pipeline-manager/chn-openstates-scrape.yml` — the actual per-state config this
  doc's "Scraper Active" column reads directly, not hand-tracked
- `tamara-notes/session-dates/session-calendar-2026.md` — the source for "In Session"
- `tamara-notes/archived_docs/` — `bill-format-audit.md`, `scraper-health.md`,
  `error-tracking.md`, `state-problems.md` and others: archived predecessors of this system
