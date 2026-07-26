---
name: scraper-fix-plan
description: Planning table for every state without a confirmed-healthy scraper -- what's been tried, what to try next. Getting thoughts organized tonight; execution starts tomorrow.
metadata:
  type: project
---

# Scraper Fix Plan

Getting organized, not executing yet -- today is thoughts-in-order, tomorrow is action.

**Priority rule for what to try next:** for any state failing on the normal (plain, no-proxy)
GitHub-hosted path, **Tinyproxy is the first thing to try, your MacBookPro (self-hosted) is the
last resort** -- it doesn't require your laptop to be on, and tonight's audit shows it performs
at least as well as self-hosted everywhere it's actually been tried.

Source data: `docs/src/state-status-reference.md`'s Hosting Path History table (2026-07-24
audit of the last 10 scrape runs per state) and tonight's investigation notes in
`tamara-notes/state-problems.md`.

---

| State | What We've Tried | What We Should Try Next |
|---|---|---|
| AR | Tinyproxy 6/6 clean; MacBookPro only 1 real run (failed) | Looks basically fine already on Tinyproxy — confirm with a couple more real (non-cancelled) runs, then probably just relabel `working` like CT/TX |
| AZ | Fails identically on all three paths (`S3_SESSION_CONFIG`) | Hosting isn't the lever here — real fix is the upstream PR [#5722](https://github.com/openstates/openstates-scrapers/pull/5722) merging |
| FL | Tinyproxy 0/6, MacBookPro 0/3 — but root cause identified: two distinct bugs, both fixed in PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724), awaiting merge | Nothing to try hosting-wise until the PR merges and a new `openstates/scrapers` image ships; re-test then |
| GA | Only ever tried plain GitHub-hosted (2/10 clean) | Never tried Tinyproxy — try that first before assuming anything else is wrong |
| MA | Almost no real data — mostly cancelled runs on every path, known runner-uptime gaps | Need real (non-cancelled) attempts on Tinyproxy specifically before concluding anything; nothing conclusively tried yet |
| MI | Fails identically on Tinyproxy and MacBookPro — root cause confirmed: `legislature.mi.gov` doesn't serve its full TLS cert chain | Hosting isn't the lever — needs the missing DigiCert intermediate bundled into the scraper's Docker CA store, or an upstream/site-side fix |
| MN | Only ever tried plain GitHub-hosted (5/10 clean, decent) | Never tried Tinyproxy — try it, but current plain-path performance isn't alarming |
| MO | Only ever tried plain GitHub-hosted (4/9 clean, repeated `P1` shrink-guard) | Try Tinyproxy, but the shrink-guard pattern looks more like the same disputed-dedup issue MT has than a hosting problem — worth checking bill identifiers before assuming a hosting fix would help |
| MP | Fails every time on the only path tried (plain GitHub-hosted; `S6_VALIDATION`/`H3_RATE_LIMITED`) | Hosting isn't the lever — real fixes are the blank-title OCD validation crash (fix identified, not yet filed upstream) and possibly easing the request rate |
| MT | Disputed — see `state-problems.md` for full writeup. GitHub-hosted-plain 3/9 clean (`P1`); one MacBookPro run, clean | Try Tinyproxy as a cheap experiment, but the real open question (why format's output is ~2,500 bills short of the raw scrape count) probably isn't a hosting problem at all |
| NE | Fails on every real (non-cancelled) run on both Tinyproxy and MacBookPro | Neither tried path works yet — worth a fresh look at what's actually failing before just trying more hosting combinations |
| NH | Fails on both paths tried (`H3_RATE_LIMITED`) — known cause: site blocks scraping 6am-9pm ET | Hosting isn't the lever — the real fix is `scrape_cron` timing, not which path runs it |
| NM | Fails on both paths tried — known cause: intermittent FTP server outage on their end (confirmed via direct `curl` testing) | Hosting isn't the lever — nothing to try except retrying later when their server's actually up |
| NV | Tinyproxy 5/5 clean; MacBookPro only 1 real run (unclear signal) | Looks basically fine already on Tinyproxy — same situation as AR, confirm with more real runs then probably relabel `working` |
| OH | Mixed results on both Tinyproxy (2/5) and MacBookPro (1/2), same `P1` shrink-guard pattern on both | Try confirming whether this is a hosting issue or the same dedup/duplicate-bill pattern as MT/MO before picking a path |
| OR | Only ever tried plain GitHub-hosted (6/10 clean, decent) | Never tried Tinyproxy — try it, but current performance isn't alarming |
| PA | Mixed results on both Tinyproxy (2/5) and MacBookPro (1/2) | Known duplicate-cruft history (see archived `scraper-status.md` notes) — likely the same dedup pattern as MT, not purely hosting |
| PR | GitHub-hosted-plain 2/9 clean (`P1`); one MacBookPro run, clean | Try Tinyproxy as a cheap experiment, same caveat as MT — might be a dedup issue, not hosting |
| USA | Tinyproxy 3/5 clean; MacBookPro 0/2 (both failed) | Tinyproxy already looks like the better path — worth a few more runs to confirm before relabeling |
| VI | Fails on every path tried — root cause confirmed: source server itself offline (`billtracking.legvi.org:8082`) | Hosting isn't the lever — nothing fixable client-side, just needs the server to come back |

## Open cross-state question

MT, MO, OH, PA, PR all show the same shape: repeated `P1_SHRINKING_OUTPUT` hits on GitHub-hosted-plain,
with at most one clean self-hosted/Tinyproxy data point. Before spending effort re-hosting all five,
worth checking whether they share MT's actual root cause (disputed duplicate-bill count, not a hosting
problem at all) rather than assuming hosting is the fix for each one individually.
