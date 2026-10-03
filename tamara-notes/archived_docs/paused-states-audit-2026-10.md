---
name: paused-states-audit-2026-10
description: Audit of all 47 paused OpenStates scrapers' last run before going dormant -- did any go quiet while already broken? 5 of 47 did. Companion to pa-vi-proxy-connectivity-2026-10.md (the active-state half of the same review). The 5 problem states' current status moved to per-state files; this doc remains the authoritative record of the full 47-state methodology and clean list.
metadata:
  type: project
---

> **Partially superseded 2026-10-03.** The 5 states found with issues here (`co`, `ut`, `wi`,
> `fl`, `ma`) now each have their own canonical file under `tamara-notes/state-specific/`,
> indexed in `tamara-notes/state-specific/README.md` — check those for current status. This
> doc remains the authoritative record of the full audit methodology and the 42-state clean
> list, which isn't duplicated anywhere else.

# Paused-state audit: did any go dormant while already broken? (2026-10-03)

## Why this exists

Prompted by finding real masked failures in the 9 currently-active scrapers (see
`pa-vi-proxy-connectivity-2026-10.md`) — if active states can silently fail for weeks behind
a green checkmark, it's worth checking whether any of the 47 *paused* states went quiet
while already broken, rather than after a clean final run. A paused state's last run is
permanent until it's un-paused for a future session — there's no scheduled re-run to
self-correct a bad final state the way an active state might.

## Method

Pulled the latest run (`gh run list --limit 1`) for all 47 states marked `paused` in
`chn-openstates-scrape.yml`, then grepped each run's annotations for a masked
`scrape failed (...)`/`actively blocked (...)` warning, or a non-`success` conclusion
(cancelled/failed outright). All 47 last-ran on 2026-09-29 except `pr` (2026-10-01).

## Results: 42 clean, 5 with issues

**Clean (42):** ak, al, ar, az, ca, ct, de, ga, hi, ia, id, il, in, ks, ky, la, md, me, mn,
mo, ms, mt, nc, nd, ne, nh, nm, nv, ny, ok, or, pr, ri, sc, sd, tn, tx, va, vt, wa, wv, wy —
no masked-failure annotation, no cancellation.

**With issues on their final run (5):**

| State | Run | Issue | Real cause |
|---|---|---|---|
| `co` | [36564841132](https://github.com/govbot-openstates-scrapers/co-legislation/actions/runs/36564841132) | `H3_RATE_LIMITED` | **Correctly classified** — a real `scrapelib.HTTPError: 429` fetching a committee vote from `leg.colorado.gov`. Unlike USA's false-positive 429 match (a coincidental bill number), this is a genuine rate-limit response. Lowest priority of the five — will very likely clear on its own next dispatch. |
| `ut` | [36567835074](https://github.com/govbot-openstates-scrapers/ut-legislation/actions/runs/36567835074) | `UNKNOWN` | `openstates.exceptions.CommandError: no sessions from Utah.get_session_list()` — falls into the catch-all bucket since nothing in `scrape.sh`'s classifier recognizes this specific exception. Not yet root-caused *why* the session list came back empty on this run. |
| `wi` | [36558777664](https://github.com/govbot-openstates-scrapers/wi-legislation/actions/runs/36558777664) | Cancelled — **"exceeded maximum execution time of 6h0m0s"** | A new pattern, distinct from FL/MA (see below): WI's job actually *started and ran*, then was killed by GitHub-hosted runners' hard 6-hour cap partway through. No `audit-summary.json` was produced at all, meaning the run likely has nothing recoverable from it. This is the same shape of problem that got FL moved to `runner: self-hosted` + a raised `scrape_timeout_minutes` — WI may need the identical treatment whenever it comes off pause. Not yet confirmed whether WI's workload genuinely needs >6h, or if this was a one-off slow run. |
| `fl` | [36555150217](https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/36555150217) | Cancelled — "awaiting a runner for 24h0m0s" | Already tracked in detail in `fl-tracking.md`. Job never started at all (different from WI — this is a runner-queue wait, not an execution-time cap). |
| `ma` | [36553854027](https://github.com/govbot-openstates-scrapers/ma-legislation/actions/runs/36553854027) | Cancelled — "awaiting a runner for 24h0m0s" | Same shape as FL — never started, runner-queue wait. |

## The full 56-state picture (combining this audit with the active-state review)

| | Count | States |
|---|---|---|
| Working clean | 47 | 5 active (dc, mi, mp, nj, oh) + 42 paused (listed above) |
| Had a real issue on last run | 8 | 3 active (`gu`, `pa`, `vi` — see `pa-vi-proxy-connectivity-2026-10.md`) + 5 paused (`co`, `ut`, `wi`, `fl`, `ma`) |
| Known bug, fix already in flight | 1 | `usa` (PR #196/#197 — Senate vote KeyError, fix pushed and under live test as of this writing) |

**84% (47/56) clean. 16% (9/56) had a real problem on their most recent run.**

## Not done here

- No fixes attempted for `co`/`ut`/`wi` — this was a documentation pass only, per explicit
  request. Each would need its own investigation the way PA/VI and USA got (reproduce, find
  root cause, verify a fix) before being considered resolved.
- WI's actual scrape duration/data volume wasn't checked — worth confirming before deciding
  whether it needs FL's exact fix (self-hosted + longer timeout) or something else.
- UT's "no sessions" `CommandError` wasn't traced into the actual scraper source the way
  USA's and GU's bugs were — unclear yet whether this is a real scraper defect, a transient
  site issue, or an expected consequence of UT being out of session when this ran.
