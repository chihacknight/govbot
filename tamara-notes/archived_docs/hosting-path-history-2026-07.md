> **Archived 2026-11-24.** Moved out of `docs/src/state-status-reference.md` (the master state list) when it was
> rebuilt. Never maintained after 2026-07-24; current status is in the master list.

# Hosting Path History (audited 2026-07-24)

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
