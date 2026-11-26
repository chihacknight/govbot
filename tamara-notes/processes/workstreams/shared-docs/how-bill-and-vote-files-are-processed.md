# How bill and vote files become the activity logs

How each nightly scrape's `bill_*.json` and `vote_event_*.json` files turn into a bill's
`metadata.json`, `action_logs.jsonl` and `vote_event_logs.jsonl`. This describes how things work
once the conversion is finished (54 repos pushed by 25 Nov 2026, ND the last to follow) and
PR #308 is merged. It was written from the code on `backfill-logs` at `b3acaf26`.

Short version:

- Every night, the scrape is the whole dataset. The logs record only what's **new** since the
  last scrape, appended at the end of each bill's two files.
- Lines are never edited, reordered or deleted. A change to something already logged is
  appended again **under the same `id`**, and readers take **the last line per `id`**.
- An action changes only when the scraper rewords it. A vote changes when its result, counts,
  voters or motion change.
- `first_seen` is when the raw scrape that first held the entry was committed, not when the
  formatter ran.

## Where the files come from

The OpenStates scraper writes one JSON file per bill and per vote into the raw scraper repo
(`govbot-openstates-scrapers/<state>-legislation`, `_data/<state>/`). File names are random
for each scrape, so the formatter works from what's in the files, never from their names.

- `bill_*.json`: one bill with all of its actions, sponsors, versions, sources and so on.
- `vote_event_*.json`: one roll call. It names its bill through `bill_identifier` +
  `legislative_session`.
- `event_*.json`: hearings and other events (only USA has them). They are archived raw and
  not covered here.

The formatter (`actions/format/main.py`, run by `actions/format/action.yml`) reads one scrape
and writes into the data repo, under
`country:us/state:<st>/sessions/<session>/bills/<bill id>/`:

| File | What it holds | How it changes |
|---|---|---|
| `metadata.json` | The bill as of the latest scrape that changed it | Overwritten |
| `action_logs.jsonl` | Every action the bill has had, one per line | Appended only |
| `vote_event_logs.jsonl` | Every roll call on the bill, one version per line | Appended only |

`action.yml` sets `first_seen` to the raw scrape's commit time (`OSDF_FIRST_SEEN`). If it's
missing, as in a local run, `main.py` uses the current time. Before writing anything, `main.py`
refuses to run on a repo that still has old-layout `logs/` folders (`has_legacy_logs`).

## Three ways lines get written

All three use the same rules in `actions/format/utils/log_jsonl.py`, so a line means the same
thing whichever one wrote it.

1. **Nightly formatter** (from now on): one scrape per run.
2. **Backfill** (`backfill_logs.py`, done once per repo): replays every scrape in the raw
   history, oldest first, as if the nightly formatter had used this layout all along. It
   writes only the two `.jsonl` files and only into bill folders that already exist.
3. **Conversion** (`convert_logs.py`, done once per repo, after the backfill): folds the old
   `bills/<id>/logs/*.json` files into the `.jsonl` files and deletes them. This is the only
   time a `.jsonl` file is rewritten instead of appended to.

The rest of this document describes the nightly path, then where the backfill and conversion
differ.

## Bill files, nightly

For each `bill_*.json` in the scrape:

**1. Every bill, every night.** There is no skip check. (Until option C, Nov 2026, a bill whose
`metadata.json` had **the same number of actions** was skipped entirely that night. That lost
GA HB69's new cosponsor, SR3's new version and HR13's title fix, missed rewordings, and let
`metadata.json` fall behind.)

**2. Guard (a): an empty field never replaces a filled one** (`utils/bill_guards.py`). For
`title`, `sponsorships`, `actions`, `versions`, `documents`, `abstracts`, `other_titles`,
`subject` and `sources`, a field tonight's scrape has empty or missing keeps the value in
`metadata.json` until it comes back. Each bill and field kept is listed in
`.windycivi/errors/kept_empty_fields.json` with the scrape it was first kept on (only that,
so the file doesn't change every night a field stays missing).
Scrapers lose a field on every bill at once and sometimes never get it back: IL's scrape has had
no abstracts since 2026-07-13 (8,648 bills), KY's no sponsors since 2026-08-20 (1,707). If guard
(a) keeps `actions`, the kept list is also what the next night's rewording check compares
against.
**3. Rewordings** (`find_rewordings`). Scrapers sometimes reword actions they already published.
Two examples: on 2026-08-10, MT changed "(H) First Reading" to "(H) 1st Reading" on every past
bill, and KS changed "Referred to Committee on Judiciary" to "Referred to Senate Committee on
Judiciary". To catch these, the formatter compares the previous scrape's actions with
tonight's, grouped by date and chamber. A group's changed actions pair up only when:

- both scrapes have the same number of actions on that date and chamber, and
- the actions that didn't change are in the same relative order.

The changed ones then pair slot by slot: `[A, B, C] → [A, B', C']` pairs B with B' and C with
C'. If either condition fails, nothing in that group is paired and each new wording is logged
as a new action. There is no text-similarity matching.

**4. Dedupe against the log and append** (`append_actions` → `select_new_actions`). Every
scraped action is checked against the bill's `action_logs.jsonl` (there is no pre-filter against
`metadata.json` any more). Two actions are the same action
when date, description (ignoring whitespace) and chamber all match. The ones that aren't
already there:

- A **rewording** is appended under the `id` of the action it rewords: a correction.
- A **new action** gets an `id` built the way the old filenames were
  (`20250114T210515Z.classification.introduction.upper` or `20250114T210515Z_referred_to_…`).
  If another entry already has that `id`, a short hash is added (`…~1a2b3c4d`).

The night's new lines are sorted by the government's date before being appended, so a new
bill's history reads forwards. Lines already in the file are not touched.

**5. Save `metadata.json`**. This is the full bill as scraped tonight, after guard (a). Its
`actions` list keeps each action's `_processing.log_file_created` stamp from earlier nights,
matched the way the log matches (guard (b): whitespace ignored, chamber included, so KY's line
breaks inside descriptions don't drop a stamp); a reworded action takes tonight's wording and
the stamp of the action it rewords. Actions appended tonight get a new stamp, and
`_processing.logs_latest_update` moves only when a line was appended. The file is written only
when its content changed, so a quiet night leaves it byte-for-byte untouched. It is what
tomorrow night's step 3 compares against.

**6. Guard (c): a field vanishing from most bills** (`BillGuards.finish`, after all bills).
When more than 50% of the bills that had a field in `metadata.json` (at least 20 bills) have it
empty tonight, the run prints a GitHub `::warning::` and writes
`.windycivi/errors/field_regressions.json`: one entry per field with state, night, field,
`bills_lost` and `bills_had`, for the daily audit to read. The file is removed on a night nothing
fires, and the run carries on. The threshold (`FIELD_REGRESSION_THRESHOLD`) was measured on the
raw history of eight states: real failures lose 69–100% of a field, everything else under 20%.

One action line:

```json
{"id": "20250114T210515Z.classification.introduction.upper",
 "first_seen": "2026-09-29T10:33:32+00:00",
 "chamber": "upper",
 "action": {"description": "...", "occurred_at": "2025-01-14T21:05:15+00:00",
            "jurisdiction_id": "~{\"classification\": \"upper\"}", "session_id": "2025",
            "entity_type": "bill", "classifications": ["introduction"],
            "related_entities": [], "sources": [...]},
 "bill_id": "SF0015"}
```

The `action` object has the same shape the old per-action files had, so readers of it didn't
change. It includes the bill's `sources`, so a single line leads back to the bill.

## Vote files, nightly

Every `vote_event_*.json` is processed. There is no skip check and no date check; the old
"newer than the newest vote" check silently dropped 10,476 late-arriving votes across 14
states.

**1. Find the bill folder** (`handlers/vote_event.py`). If the bill has no folder yet, one is
created with a `placeholder.json` (the bill's own file may arrive later). The vote is queued,
not written yet.

**2. One batch per bill.** After the whole scrape is read, each bill's queued votes go to
`append_votes` together (`process_and_save`). That way the rules below see every version of a
vote the scrape holds at once.

**3. Is it a vote we already have?** (`vote_keys`, `_find_vote`). Two votes are the same vote
when:

- both have a roll-call `identifier` and identifier + date + motion match, or
- date + motion + chamber + counts match.

Identifier alone isn't enough, because VA and MT reuse one identifier across different votes.
Date + motion + chamber alone isn't enough either: PA HB 1549 had two roll calls on one motion
at the same time.

**4. Did it change?** (`vote_substance`). A vote's substance is its date, motion, motion
classification, chamber, result, counts and voter list, with voter rows and counts sorted so a
reordering isn't a change. URLs and other fields don't count.

**5. Decide** (`select_new_votes`). For each of tonight's versions, in order:

1. **Scraper-failure check.** If the state has an entry in `SCRAPER_FAILURES` and it flags
   this version, the version is treated as not scraped. It is not logged and is counted as
   skipped (see the next section).
2. **New vote** (no match in the log): appended with a new `id`, built like the old
   filenames (`20250205T173055Z_vote_event_fail`, `….vote_event.pass.lower`), with a hash added
   if that `id` is taken.
3. **Known vote, and tonight's scrape includes the version that's already its last line:** log
   nothing. Some scrapes hold two versions of one vote (OH HB 14: one 6-0 "Reported" vote as
   both pass and fail; MT: "Sen Elect Gregg Hunter" in one copy, "Gregg Hunter" in the other).
   Comparing each copy with the last line used to log A, B, A, B… every night.
4. **Known vote, changed:** appended under the vote's `id` (a correction), even if it matches an
   earlier version. A real revert is logged (DE SB 315 pass → fail → pass). At most one
   correction per vote per night.

The result: **each vote's last line matches the latest scrape.** Run 3 checked this on all 16
repos that had been held back: 0 differences.

One vote line:

```json
{"id": "20250205T173055Z_vote_event_fail",
 "first_seen": "2026-09-29T10:33:32+00:00",
 "chamber": "upper",
 "vote_event": {...the OpenStates vote event exactly as scraped...},
 "bill_id": "SF0001"}
```

## Per-state scraper failures

The logs mean the same in every state, but scrapers fail in different ways, so failures are
caught per state, in one table in `log_jsonl.py`:

| State | Treated as not scraped | Why | Tracked in |
|---|---|---|---|
| ND | Any voter named "Service Unavailable" or "Proxy Error" (an exact list, `_ND_ERROR_PAGES`) | When `ndlegis.gov` is down, the scraper saves the error page's title as a voter. 8 nights, up to ~1,170 votes each | `tamara-notes/state-specific/nd.md` |
| TN | An empty roll call while the last logged version has voters | The scraper sometimes saves roll calls with no voters, and the names come back later. 6,787 votes, mostly 2026-07-02 | `tamara-notes/state-specific/tn.md` |

A state with no entry gets only the uniform rules. A general "empty roll call = failure" rule
would be wrong: in OK and HI the same change is the scraper fixing its own parsing. Each entry
is a stopgap. When OpenStates fixes the bug, delete the entry and its test, and update the
state file.

## How the backfill differs

`backfill_logs.py <data repo> <raw scraper repo> --report-dir <dir>` replays each raw commit as
one night, with `first_seen` = that commit's time:

- **No skip check.** Every bill file is compared with the log itself, so actions the shortcut
  lost are recovered.
- **"Previous scrape" for rewordings** is the previous version of that bill it replayed,
  instead of `metadata.json`.
- **Writes only the two `.jsonl` files.** No `metadata.json`, no placeholders. A bill in the raw
  history with no folder in the data repo is listed in the report, not created.
- **Re-runs resume.** The last replayed commit is recorded in
  `<report-dir>/log_backfill-<state>.json`, outside the repo, so no scrape is replayed twice.
  Nothing is written until the whole replay succeeds.

The raw history starts in November 2025. Anything older comes from the old files in the next
step.

## How the conversion differs

`convert_logs.py <repo>`, per bill:

- Each old `logs/*.json` file becomes a line with the same `id` (the filename without `.json`).
  Old action files come in two shapes (OpenStates' `date`/`organization_id`/`classification`,
  and the writer's `occurred_at`/`jurisdiction_id`/`classifications`). All are rewritten to the
  second shape.
- `first_seen` for an old action comes from `metadata.json`
  (`actions[]._processing.log_file_created`). Old vote files have no such record, so their
  `first_seen` is `null`; the schema allows it. This is the 5,630 `null` lines in TN.
- **When an old file and a backfilled line are the same entry, the backfilled line wins**: it
  has the scrape's commit time. It keeps the earlier of the two `first_seen` values and takes
  the old file's `id`, the name people and tools already know.
- An old vote file with the same identity as a backfilled vote but **different substance**
  is an older version from before the raw history. It goes first, under the vote's `id`, as the
  start of its history. (TN's empty-roll-call old files followed by the real version are this
  case.)
- Old lines go before the backfilled ones, the old files and the session-level symlinks are
  deleted, and anything that can't be read is left in place and reported, never deleted.

## Reading the logs

Readers show **the last line per `id`**; earlier lines are history.

- An **action** shows its current wording but keeps its **first** line's `first_seen` (when it
  first happened, not when it was reworded).
- A **vote** shows its latest version with **that** line's `first_seen` (when the correction
  appeared).

The Rust reader (`actions/govbot/src/logs_jsonl.rs`, behind `govbot logs`) and the Python
reader in `log_jsonl.py` both handle the old layout too, so `govbot logs` prints the same shape
for any repo: one entry per action and per vote.

What a night's commit looks like: `git diff` shows `metadata.json` changes plus only added lines
at the end of `.jsonl` files. A night's new activity is those added lines.

## Things to know (from reading the code, not measured)

- **A vote without an identifier whose counts change is logged as a new vote, not a
  correction.** Counts are part of the fallback identity (because of PA HB 1549), so the new
  version doesn't match the old one. Both then show as current. A voter-list or result change
  with the same counts is still a correction. This matters in states whose votes have no
  `identifier` (ND's are empty, for example).
- **A vote or action that drops out of the scrape stays in the log.** Nothing is ever removed.
  Run 3 found such votes in every repo (OH: 16, DE: 126), mostly from older sessions.
- **Parsing errors from the scraper are logged as scraped.** For example, TN SB1414 has a voter
  named "Lafferty -- 1. HB1242 by Helton-Haynes", and MI HB5697 has one named "sections 279 and
  679.". The logs show what OpenStates published; such errors are reported upstream rather than
  filtered.

## Still open before the scrapers are unpaused

1. **Bill-skip option C**: implemented, in review (branch `bill-skip-option-c`, see
   `shared-docs/bill-skip-option-c.md`); this document already describes it. Every bill is processed every night, new actions are
   checked against the log (closing the old chamber gap), with the three guards above.
2. **The auto-merge step** that saved conflict markers into raw commits (first find out why #100
   was reverted).

Decided not to do (25 Nov): rebuild the logs of repos pushed before the rewording rule (KS, NH,
USA and others). Their past reworded actions stay as duplicates under two ids; future nights
are correct. Their votes correct themselves on the first nightly run (rule 2).

## Where things are

| What | Where |
|---|---|
| The rules | `actions/format/utils/log_jsonl.py` |
| Nightly bill / vote handling | `actions/format/handlers/bill.py`, `handlers/vote_event.py`, `utils/process_utils.py`, `utils/io_utils.py` |
| Backfill / conversion | `actions/format/backfill_logs.py`, `convert_logs.py` |
| Line schemas | `actions/format/schemas/action_log.schema.json`, `vote_event_log.schema.json` (copies in `/schemas`) |
| Reference docs | "Action and vote logs" in `actions/format/docs/DATA_STRUCTURES.md`; CLAUDE.md "Bill activity logs" |
| Tests | `cd actions/format && python3 test_log_jsonl.py && python3 test_backfill_logs.py`; `actions/govbot/tests/logs_layout_snaps.rs` |
| Decisions and evidence | `tamara-notes/processes/workstreams/jsonl-logs.md`, `shared-docs/jsonl-log-conversion-results.md` |
| Conversion reports | `/Volumes/govbot-data/scratch/backfill/reports/` (`run3.md` is the final one for the 16) |
