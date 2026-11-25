# Master state list (goal 5)

**Folder:** `~/my_work/govbot-master-list` · **Branch:** `docs/master-state-list`

## Kickoff prompt

> Read `tamara-notes/processes/handoff-2026-11-24.md` and
> `tamara-notes/processes/workstreams/master-state-list.md`, then work on the master state list.
> Stay in this folder and on the `docs/master-state-list` branch. This is docs only.

## Goal

The team needs one place to look up the status of all 56 jurisdictions. Today several
overlapping docs disagree. Pick one, merge the others into it, and retire the rest.

## Candidates

- `docs/src/state-status-reference.md` — the 56-row table, published on the site. The likely
  winner.
- `tamara-notes/scraper-status/not-working.md`, `working-in-session.md`,
  `working-out-of-session.md`
- `tamara-notes/archived_docs/` (`state-problems.md`, `scraper-health.md`, `error-tracking.md`, …)
- `tamara-notes/state-specific/` (one file per state). Keep these for detail and link to them
  from the master list.

## Open item: four tracking files committed unverified (resolved 2026-11-24)

These were committed as-is on Nov 24 (PR #304) without re-checking:
`not-working.md`, `critical-merge-conflict-corruption.md`, `morning-todo.md`,
`session-calendar-2026.md`. All four were checked against current data on 2026-11-24; see
"Status" below for what held up.

## Deliverables

1. One master list with a clear "Last checked" date per row.
2. The other docs either merged in and deleted, or reduced to a one-line pointer to the master.
3. A pull request.

## Out of scope

- Fixing scrapers. Record what's broken; the scraper-fixes chat fixes it.

## Status: done 2026-11-24, in review

**PR:** [#307](https://github.com/chihacknight/govbot/pull/307) (branch `docs/master-state-list`).

**The master list:** [`docs/src/state-status-reference.md`](https://github.com/chihacknight/govbot/blob/docs/master-state-list/docs/src/state-status-reference.md).
It goes on the site (State Status Reference) once the PR merges. Every one of the 56 rows was
checked on 2026-11-24 against each state's GitHub run history, the raw repos' scrape commits and
the local clones on the `govbot-data` drive.

### Most important finding

**No scraper has run since 2026-10-29.** All 9 active scrapers (DC, GU, MI, MP, NJ, OH, PA, USA,
VI) have failed every day since 2026-10-30. GitHub's `ubuntu-latest` runner is now Ubuntu 26.04,
which has no Python 3.9, and `actions/scrape/action.yml` line 54 asks for `python-version: "3.9"`.
The run stops at "Setup Python" before anything is scraped. The daily digest (#202) has listed
all 9 every day, but no issue exists yet. **This needs to go to the scraper-fixes work.**

### What happened to the old docs

- The 7 files in `tamara-notes/scraper-status/` moved to `tamara-notes/archived_docs/`, each with
  a "superseded" note at the top: `not-working.md`, `working-in-session.md`,
  `working-out-of-session.md`, `morning-todo.md`, `critical-merge-conflict-corruption.md`,
  `pending-branches.md`, `upstream-pr-todo.md`.
- `scraper-status/not-working.md` stays as a one-line pointer, because code comments link to it.
- The July "Hosting Path History" table moved to `archived_docs/hosting-path-history-2026-07.md`.
- `tamara-notes/state-specific/` stays as the place for each state's detail. Added `az.md`;
  updated `pa.md`, `fl.md` and the index.

### What checking the old claims turned up

| Claim | Finding |
|---|---|
| NM is broken (July FTP outage) | Wrong. NM's last run (Sept 29) was clean: 812 bills, over HTTPS, no FTP. |
| Conflict markers may have corrupted more states | No data is corrupted: none in any of the 112 repos. The bug is still in `action.yml`, though. Its fix (#100) was reverted the day it merged, with no reason given. |
| FL and AZ are waiting on upstream PRs | Wrong. Both (#5724, #5742) were closed unmerged. AZ will break again when unpaused (see `az.md`). |
| PA is blocked by our proxy | No longer. The Oct 29 run scraped 5,259 bills; the shrink guard held them back (5,264 already saved). |
| TX needs our own machines | Its config doesn't ask for one. Check before unpausing. |
| Session dates | USA is still in session (lame duck since Nov 9). No other special sessions found. |

### Hand-offs

- **Scraper fixes:** the Python 3.9 outage; GU's empty `note` crash; VI's unreachable site;
  AZ's image before unpausing; FL, MA and WI's runner and timeout problems; UT's "no sessions" error.
- **Open question for Tamara:** why was the conflict-marker fix (#100) reverted?
- **Keeping it current:** when a state's status changes, update its row and its "Last checked"
  date. Put the long version in its `state-specific/` file.
