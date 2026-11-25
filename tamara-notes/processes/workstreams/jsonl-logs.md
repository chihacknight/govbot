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

## Decisions (2026-11-24, Tamara + Claude)

Worked out top-down from what the logs are *for*: every night's scrape is the whole
dataset, and the logs mark what is new, for people and simple local AI agents (and
Sartaj's vector tagging, which reads `govbot logs`).

- **Per bill, two files, directly in the bill folder:** `bills/<id>/action_logs.jsonl`
  (source: the bill's `actions`) and `bills/<id>/vote_event_logs.jsonl` (source: the
  `vote_event_*` scrape files). No `logs/` subfolder. A per-night file was considered and
  rejected.
- **Append-only:** a night's new entries go at the end (that batch in government-date
  order); existing lines are never edited, reordered or removed. `git diff` of a night =
  exactly the new lines.
- **Each line:** `id` (old filename stem, `~hash` on collision), `first_seen`, plain
  `chamber`, the action/vote as published, `bill_id`. Actions keep the bill's `sources` on
  purpose: a lone log line always leads back to the bill.
- **`first_seen` = the raw scrape's commit time**, not the formatter's run time, so the
  backfill gets the right night. `scraped_at` stays out of `metadata.json` (it changes
  every night and would make every bill look changed).
- **Votes:** no date watermark; dedupe by roll-call `identifier`, else date + motion +
  chamber + counts. A change in substance (result, counts, member votes, motion) is
  appended as a correction under the same `id`; readers take the last line per `id`.
  Cosmetic changes (URL format, roll-call number filled in later, voter order) aren't.
- **Session symlinks (`sessions/<s>/logs/`) removed**, with `symlink_logs.py`. They doubled
  the file count and made `govbot logs` emit every action twice (GA: 61,256 lines for
  30,628 actions) and the weekly audit count double.
- **USA events** (`event_*`, 711 raw, USA only) stay raw-only; the formatter's event code is
  untouched.
- **The formatter refuses an unconverted repo** (old `logs/` folders) and now fails the
  step on any formatter error (it used to be swallowed by `|| true`).
- Not in this PR: **bill skip, option C** (always process every bill; never replace a
  non-empty field with an empty one; whitespace-only action differences are the same
  action; a field vanishing on most bills goes to the error digest). Evidence: GA lost real
  updates; KY's 2026-09-29 scrape has no sponsors on 1,707/1,737 bills.

### Evidence (local copies on `/Volumes/govbot-data`, 2026-11-24)

- 14 states, 94,527 distinct raw votes in the latest scrape: 21,818 (23%) never reached the
  formatted data. 6,662 lost to old-filename collisions, 10,476 to the date watermark
  (TN 7,181), 4,680 newer than the watermark in PA/CA/NJ (formatting there looks stalled
  since July — separate issue). PA's scraper writes each vote ~5×.
- Old action files come in two shapes (current `occurred_at`/`jurisdiction_id`, and
  OpenStates' `date`/`organization_id`); 36 repos hold both. The converter normalizes to
  the current shape.

## Conversion plan (for the repo-rewrite / CT pilot)

Raw scraper history (`govbot-openstates-scrapers`, full clones in
`/Volumes/govbot-data/raw-scrapers/`) starts 2025-11-26/27 for every state (290–690
scrape commits each). Each scrape is the whole dataset, so replaying it recovers the lost
votes and gives every entry a real `first_seen`.

Per repo, on the SSD, as part of the same rewrite as the session split (goal 1), the
cleanup (goal 2) and the `.windycivi` rename (goal 4), so each repo is rewritten once:

1. Full-history clone of the formatted repo; record counts (bills, old log files).
2. **Backfill first:** replay the raw history oldest → newest, appending each scrape's
   actions and votes with `first_seen` = that scrape's commit time (the writer's dedupe
   and correction rules do the rest): `python3 actions/format/backfill_logs.py <repo>
   <raw-repo> --report-dir <dir>`. It touches only the two log files, writes only into
   existing bill folders (the rest are listed in the report) and keeps its re-run cursor
   in `<dir>/log_backfill-<state>.json`, not in the repo.
3. **Then fold in the old files:** `python3 actions/format/convert_logs.py <repo>`. Entries
   already recovered from the raw history are dropped as duplicates (the backfilled line
   keeps the earlier `first_seen` of the two and the old file's id); the rest (older than
   the raw history, or no longer in the scrapes) go first in each file, with `first_seen`
   from `metadata.json`'s `_processing.log_file_created`, else null. An old vote matching
   a backfilled vote's identity but none of its versions goes first under the same id. It also deletes the
   session symlinks. Anything it can't recognise is listed and left in place: stop and look.
4. Validate every line against `actions/format/schemas/*.schema.json`; compare counts with
   step 1 (no action lost; votes ≥ before):
   `/Volumes/govbot-data/scratch/backfill/check_conversion.py <original> <converted> <govbot>`
   (run with that folder's `venv/bin/python`, which has jsonschema).
5. One commit, pushed. After that the formatter accepts the repo.

Order: CT pilot first, then the rest **before the scrapers are unpaused**: an unconverted
repo makes the formatter stop as soon as it gets new data.

## Status

- 2026-11-24: code located and reviewed. Decisions above made. PR in progress on
  `jsonl-logs`: writer (`actions/format/utils/log_jsonl.py`), handlers, vote gate removed,
  `first_seen` from the scrape commit, converter (`convert_logs.py`), symlink step and
  `symlink_logs.py` removed, Python readers (cleanup_placeholders, weekly audit, IL field
  audit, last-activity scripts), schemas, CI validation, snapshots, docs (`llms.txt`,
  README, about, DATA_STRUCTURES, data-repo README template). Still to do: the Rust readers
  (`govbot logs`, `govbot query votes`, library API + snapshots; needs Rust, to be
  installed on the SSD), the backfill tool.
- 2026-11-24 (later): PR #306 merged. On `backfill-logs`: `backfill_logs.py` (+
  `test_backfill_logs.py`), `log_jsonl.py`'s is-this-new rules split into
  `select_new_actions` / `select_new_votes` / `order_batch` (pure refactor), and
  `convert_bill` fixed to keep the backfilled line on a duplicate (it used to keep the
  old file, losing the scrape dates). Tested on SSD copies (`scratch/backfill/`):
  - KY: 290 scrapes, 73 s. 22,204 actions, 2,290 votes (old layout 1,588) + 116
    corrections (the scraper dropped duplicate House member rows on 2026-09-19). Every
    old file was in the raw history; no `first_seen` null; schema clean.
  - GA: 280 scrapes, 6 min. 28,190 actions, 2,798 votes (old 2,510) + 756 corrections,
    all one change: on 2026-01-01 the scraper renamed voter "ISLAM PARKES" to "PARKES"
    across past roll calls. 912 raw files in the 2026-07-21 "Auto-merge: kept scraped
    data" commit hold committed git conflict markers (unparseable; both parent scrapes
    are replayed, so nothing lost). Every old file covered; schema clean.
