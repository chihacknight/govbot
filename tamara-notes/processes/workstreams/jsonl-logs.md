# JSONL logs (goal 3) — PRIORITY

**Folder:** `~/my_work/govbot-jsonl` · **Branch:** `jsonl-logs`

## Kickoff prompt

> Read `tamara-notes/processes/handoff-2026-11-24.md` and
> `tamara-notes/processes/workstreams/jsonl-logs.md`, then work on the JSONL logs goal. Stay in
> this folder and on the `jsonl-logs` branch.

## Goal

Each bill's `logs/` folder holds one JSON file per action and vote, which means thousands of
files per repo. Replace them with one `.jsonl` file per bill, then plan converting every
`govbot-data` repo to that layout.

## What already exists

- Taha Husain's unmerged branch `origin/jsonl-action-logs` (Aug 18, 3 commits). It changes only
  `write_action_logs` in `actions/format/utils/file_utils.py` to append each action as one line
  of `logs/action_logs.jsonl`. It merges into `main` with no conflicts. Build on it and keep
  Taha's commits (merge his branch in) so the credit stays.
- No `govbot-data` repo uses JSONL yet. Live repos still write per-action files, e.g.
  `bills/HB6439/logs/20261028T000000Z_read_a_first_time.json` in `mi-legislation`.

## Gaps in Taha's branch

1. Vote events still write one file each (`write_vote_event_log`).
2. `Path(log_folder / "action_logs.jsonl")` breaks when `log_folder` is a string.
3. It appends, so a re-run that treats an action as new adds a duplicate line. Pipelines must be
   idempotent.
4. No snapshot updates in `actions/format`.
5. The per-file filenames carried meaning (timestamp, classification, chamber). Decide whether
   each line needs those fields so readers don't lose them.

## Everything that reads the old layout (check each one)

- `govbot logs` and `govbot load` (DuckDB) in `actions/govbot`
- `scripts/build_site_slices.py`
- `actions/format/symlink_logs.py` and `actions/format/postprocessors/cleanup_placeholders.py`
- The weekly audit's activity checks in `actions/openstates-scrape-audits/`
- `actions/pipeline-manager/scripts/audit-last-real-activity*.sh`
- `llms.txt` and `catalog.json` at the repo root, which describe the data layout to AI agents

## Deliverables

1. A pull request that finishes the writer (actions and votes, idempotent, snapshots updated) and
   updates every reader above.
2. A written conversion plan for the existing repos. Coordinate with the repo-rewrite chat: the
   conversion should run during the CT pilot so each repo is rewritten only once.

## Out of scope

- Rewriting live `govbot-data` repos. That belongs to the repo-rewrite chat.
- Unpausing scrapers.

## Status

- 2026-11-24: code located and reviewed (see above). Nothing changed yet.
