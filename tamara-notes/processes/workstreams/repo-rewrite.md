# Repo rewrite (goals 1, 2 and 4) — start after JSONL is settled

**Folder:** `~/my_work/govbot-repo-rewrite` · **Branch:** `repo-rewrite`

## Kickoff prompt

> Read `tamara-notes/processes/handoff-2026-11-24.md`,
> `tamara-notes/processes/workstreams/repo-rewrite.md` and
> `tamara-notes/processes/workstreams/jsonl-logs.md`, then work on the repo rewrite. Stay in
> this folder and on the `repo-rewrite` branch. Rebase on `origin/main` first.

## Why these three are one chat

Each goal rewrites the same `govbot-data` repos. Done together, every repo is rewritten once
instead of three or four times. That matters because git history is the tamper-evident record:
no history rewriting, ever.

## The three goals

1. **One repo per state per session** (goal 1). `actions/pipeline-manager/close_session.py`
   already does this but has never run at scale. Resolve the collision first:
   `govbot-archive` already holds an orphaned `<state>-legislation` repo for most states, and
   `close_session.py` writes into that org by name.
2. **Clean up the early data** (goal 2). Follow
   `tamara-notes/processes/session-data-cleanup-plan-2026-10.md`. Pilot on CT; its clone is on
   the external SSD at `/Volumes/SSK SSD/govbot-data-cleanup/ct/live`. Plug the SSD in and
   confirm the clone is still there.
3. **Remove the Windy Civi brand** (goal 4). Rename the `.windycivi/` folder in every repo. Its
   writers and readers are `actions/scrape`, `actions/format` and
   `actions/openstates-scrape-audits/`; they must change together.

## Depends on

- The JSONL layout from the JSONL-logs chat. Fold its conversion into the CT pilot.

## Deliverables

1. A CT pilot that applies all changes to one repo, with a before/after diff.
2. A runbook for the other 55.

## Status

- 2026-11-24: waiting on the JSONL layout.
