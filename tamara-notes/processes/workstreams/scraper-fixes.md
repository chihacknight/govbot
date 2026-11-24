# Scraper fixes (goal 6)

**Folder:** `~/my_work/govbot-scrapers` · **Branch:** `scraper-triage`

## Kickoff prompt

> Read `tamara-notes/processes/handoff-2026-11-24.md` and
> `tamara-notes/processes/workstreams/scraper-fixes.md`, then triage the scraper fixes. Stay in
> this folder and on the `scraper-triage` branch.

## Goal

Get the broken scrapers working before sessions reopen. Scrapers are paused on purpose since
2026-09-30 (PR #180). Don't unpause a state to "fix" missing bills.

## Known status (as of Oct 13 — re-check each before acting)

| State | Problem | Likely next step |
|---|---|---|
| PA | `palegis.us` blocks the proxy VM's IP | Needs a different egress IP |
| GU | A bill version's empty `note` fails schema validation | Trace in `scrapers/gu/bills.py`, fix upstream |
| MI | `H2_AUTH_FAILURE` on Oct 11, 258 warnings | Pull the job log; may be a classifier false positive. Also fix `error_summary` extraction in `actions/scrape/scrape.sh` |
| UT | `no sessions from Utah.get_session_list()` | Root-cause |
| WI | Hit the 6-hour GitHub-hosted cap | `runner: self-hosted` + longer `scrape_timeout_minutes`, like FL |
| FL, MA | Cancelled after 24h waiting for a self-hosted runner | Check runner capacity |
| VI | `billtracking.legvi.org:8082` unreachable | Probably their outage; re-test |
| CO | Real 429 rate limit | Low priority |
| USA | Fixed (PR #226 merged Nov 24) | Delete stale image `ghcr.io/tamara-builds/openstates-scrapers:usa-fix-test` |

## Splitting this chat

States are independent. A teammate can take one state into its own chat and worktree:

```
cd ~/my_work/govbot
git worktree add ../govbot-gu -b gu-fix origin/main
```

Upstream fixes go to `~/my_work/openstates-scrapers`, following
`tamara-notes/processes/openstates-pr-conventions.md` (jurisdiction-prefixed titles, companion
issue in `openstates/issues`, filed as `tamara-builds`).

## Out of scope

- Unpausing scrapers or re-enabling `check-sessions.yml`.

## Status

- 2026-11-24: not started.
