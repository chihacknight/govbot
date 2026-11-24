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

## Open item: four tracking files committed unverified

These were committed as-is on Nov 24 (PR #304) and their claims have not been re-checked:
`not-working.md`, `critical-merge-conflict-corruption.md`, `morning-todo.md`,
`session-calendar-2026.md`. `not-working.md` contains a correction that suggests the New Mexico
row in the committed table is wrong. Verify each claim against current data before it goes into
the master list.

## Deliverables

1. One master list with a clear "Last checked" date per row.
2. The other docs either merged in and deleted, or reduced to a one-line pointer to the master.
3. A pull request.

## Out of scope

- Fixing scrapers. Record what's broken; the scraper-fixes chat fixes it.

## Status

- 2026-11-24: not started.
