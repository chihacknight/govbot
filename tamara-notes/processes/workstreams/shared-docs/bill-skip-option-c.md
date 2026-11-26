# Bill-skip option C: process every bill every night

The working doc for option C. The implementing chat writes its progress and results here, and
the reviewing chat (the one that ran the JSONL conversion review) adds reviews here, so Tamara
doesn't have to relay messages between them. Newest entries at the bottom of each section.

## Setup

- **Worktree:** `/Users/tamara/my_work/govbot-bill-skip`, branch `bill-skip-option-c`, made
  from `main` at `4a645850` (#308 merged). Work only here. Don't touch
  `~/my_work/govbot-jsonl`: the SSD scripts run code from that folder.
- **Rules:**
  - **Disk: SSD only.** The laptop has almost no free space (the dry run filled it on 25 Nov).
    Put every clone, copy, report and scratch file under `/Volumes/govbot-data/scratch/`
    (option C dry run: `/Volumes/govbot-data/scratch/option-c-dry/`), never in the session
    scratchpad or `/tmp`, and never inside `govbot_data/full/`. Only the code worktree stays on
    the laptop.
  - Commit and push only when Tamara says so.
  - Never push to a `govbot-data` repo.
  - Don't unpause the scrapers.
  - `chihacknight/govbot` squash-merges PRs: after a PR merges, start new work on a fresh
    branch.
- **Read first:**
  - `shared-docs/how-bill-and-vote-files-are-processed.md`: how a scrape becomes
    `metadata.json` and the two `.jsonl` logs today, and the known gaps.
  - The "Bill skip" decision in `tamara-notes/processes/workstreams/jsonl-logs.md`, with its
    evidence (GA, KY).
  - `actions/format/utils/log_jsonl.py`, `handlers/bill.py`, `utils/io_utils.py`,
    `utils/processing_tracker.py`.

## Why

The nightly formatter skips a bill completely when its action count matches `metadata.json`
(`compare_action_counts` in `utils/io_utils.py`). That loses real updates. Three Georgia bills
are examples:

- HB69: a new cosponsor was never recorded.
- SR3: a new version was never recorded.
- HR13: a title fix was never recorded.

It also misses rewordings, and lets `metadata.json` fall behind, which is what tomorrow's
rewording check compares against. Every converted repo was rebuilt by the backfill, which never
skips, so the nightly formatter has to match it before the scrapers are unpaused.

## Decided (Tamara, 25 Nov 2026)

1. **Process every bill every night.** Remove the action-count skip.
2. **Check new actions against the log, not `metadata.json`.**
   - Remove the description + date pre-filter (`find_new_actions`) and pass every scraped
     action to `append_actions`, which already ignores what's in the log (date + description
     ignoring whitespace + chamber).
   - This closes the chamber gap. Today the pre-filter ignores chamber, so a same-date,
     same-wording action from the other chamber that arrives on a later night is never logged.
   - `find_rewordings` keeps comparing with `metadata.json`.
3. **Guard (a): never replace a non-empty field with an empty one.**
   - Fields: `sponsorships`, `actions`, `versions`, `documents`, `abstracts`, `other_titles`,
     `subject`, `sources`, and `title` (only when tonight's is empty).
   - Keep last night's value until the field comes back, and write a warning every night it's
     kept, to `.windycivi/errors/`. Use a clear name, and record bill, field and the night first
     kept.
   - Example: KY's 2026-09-29 scrape had empty sponsors on 1,707 of 1,737 bills.
4. **Guard (b): a whitespace-only description change is the same action** in `metadata.json`
   too. `merge_actions` matches with whitespace ignored, so KY's line breaks inside
   descriptions don't create new actions or lose an action's `_processing.log_file_created`.
5. **Guard (c): a field vanishing from most of a state's bills in one night is a scraper
   regression.**
   - Print a GitHub `::warning::` and write a summary file the daily audit can show.
   - Don't stop the run: guard (a) already protects the data.
   - Write the summary file as plain JSON with one entry per field that fired: state,
     night, field, bills that lost it, bills that had it. The state auditor (the daily digest
     in `actions/openstates-scrape-audits/`) is meant to read it later; don't build that side
     here.
   - Threshold: start with **more than 50% of the bills that had the field, with at least 20
     bills**. The reviewing chat is checking this against the raw history (see "Review" below)
     and may change it. Keep it a single constant.
6. **Out of scope:**
   - votes with no roll-call number whose counts change (logged as a new vote, not a
     correction); being measured separately, and nothing reads the vote logs yet;
   - full-text extraction;
   - the auto-merge conflict-marker fix.

## Work

1. `utils/io_utils.py`: remove the skip and its imports.
2. `handlers/bill.py`:
   - pass all scraped actions to `append_actions` with
     `rewordings=find_rewordings(existing_actions, actions)`;
   - keep `logs_latest_update` gated on lines actually being added (use `append_actions`'
     return value);
   - keep `_processing.log_file_created` stamps.
3. Guards (a), (b), (c), with the government-data reasons written as comments beside the code,
   like `SCRAPER_FAILURES` in `log_jsonl.py`.
4. Delete what's left unused, such as `compare_action_counts` and `find_new_actions`, if nothing
   else calls them. Grep `actions/` and `scripts/` first: `audit-last-real-activity.sh` and
   `timestamp_tracker.py` mention `find_new_actions` in comments.
5. Docs:
   - the CLAUDE.md "Bill activity logs" section;
   - the "Action and vote logs" part of `actions/format/docs/DATA_STRUCTURES.md`;
   - the bill section and "Still open" in `how-bill-and-vote-files-are-processed.md`;
   - the option C bullet in `jsonl-logs.md`.

## Things to check (known risks)

- **A night with no changes must leave `metadata.json` byte-for-byte unchanged.** Every bill is
  now rewritten every night, so anything run-dependent in it (a timestamp, key order, a set)
  would make every bill show up in `git diff`. Test it.
- **Runtime.** `append_actions` now reads each bill's action log every night. Time a full night
  on a big repo (IL: about 150k action lines; TN: about 140k) against today's code.
- **`find_rewordings` after guard (a).** If guard (a) kept last night's actions because tonight's
  are empty, the next night must still compare against the kept list, not an empty one.
- **New bills, placeholders and `errors/` routing:** unchanged.

## Tests

- **Unit tests** in `actions/format/` (next to `test_log_jsonl.py`), for:
  - the GA cosponsor case (same action count, `metadata.json` updates);
  - the chamber gap;
  - each guard;
  - a rewording on a night with an unchanged count, logged as a correction;
  - a no-change night writing nothing.

  Run `python3 test_log_jsonl.py && python3 test_backfill_logs.py`, plus the new tests.
- **Snapshots:** `actions/format` snapshot tests (`render-snapshots.sh`). Update them only where
  the change is intended, and say which and why.
- **Dry run on real data, copies only.**
  - States: WY, KY, GA, MT, IL (IL added after the guard (c) measurement, see Review).
  - Clone each converted repo from `/Volumes/govbot-data/govbot_data/full/<st>-legislation`
    into scratch (never work in that folder: those are the pushed working copies).
  - Run the new formatter on the latest raw scrape from
    `/Volumes/govbot-data/raw-scrapers/<st>-legislation`.
  - Expect:
    - **0 new log lines** (the backfill already logged everything in that scrape);
    - `metadata.json` changes only where the skip had hidden real updates. Count them by field,
      with 3 examples per state.
  - Then run it a second time: expect **0 changes of any kind** (idempotent).

## Reporting

Add a "Progress" entry below when the code and tests are done, then a "Dry run" entry with a
table:

| State | Bills | New log lines | Bills with a `metadata.json` change, by field | Guard (a) kept | Guard (c) fired | Second run changes | Runtime, old vs new |
|---|---|---|---|---|---|---|---|

Then stop and wait for review before committing.

## Progress

(implementing chat)

- **25 Nov, code and tests done** (uncommitted, in this worktree).
  - **Skip removed.** `utils/io_utils.py` no longer gates `bill_*.json` (its two now-unused
    parameters are gone too, and `main.py`'s call with them).
  - **New actions checked against the log** (`handlers/bill.py`). Every scraped action goes to
    `append_actions(..., rewordings=find_rewordings(existing_actions, actions))`.
    `append_actions` got an optional `added` list that returns the appended lines. From it:
    - the actions logged tonight get `_processing.log_file_created`;
    - `actions` and `action_log_files_created` in `latest_timestamp_seen.txt` count only those;
    - `logs_latest_update` moves only when a line was appended.

    An action already in the log but missing from `metadata.json` (which the skip could leave
    behind) gets no new stamp, because tonight's run didn't log it.
  - **`metadata.json` is written only when its text changed**, so a quiet night leaves every
    file byte-for-byte untouched, mtime included.
  - **Guard (a)** is `BillGuards.keep_nonempty` in the new `utils/bill_guards.py`. It covers the
    nine fields; `title` counts as empty only when blank. It runs before the log step, so kept
    `actions` are what gets passed on and saved, and the next night's `find_rewordings`
    compares against them (tested).
    - The record is one file, `.windycivi/errors/kept_empty_fields.json`:
      `{"<session>/<bill>": {"<field>": {"first_kept"}}}` (`last_kept` dropped after review,
      see below).
    - The night is the scrape's commit time (`first_seen`), so re-running a scrape writes
      the same bytes.
    - A field's entry is dropped when the field comes back, and the file is deleted when
      nothing is kept.
    - One `⚠️ Kept last night's <field> on N bills` line is printed per field per night.
  - **Guard (b)** is in `merge_actions`, which now matches on `raw_action_key`, the log's own
    key (date, description ignoring whitespace, chamber).
    - Chamber in the key also fixes a merge bug: two chambers' identical actions on one date
      both collapsed onto one existing action.
    - A reworded action takes tonight's wording and keeps the `_processing` of the action it
      rewords. The dry run found this case: WY HB0144's rewording had been logged by the
      backfill, but `metadata.json` still had the old wording.
  - **Guard (c)** is `BillGuards.finish`, run after all bills.
    - The threshold is the single constant `FIELD_REGRESSION_THRESHOLD = (0.5, 20)`: more than
      50% of the bills that had the field, with at least 20 of them.
    - When it fires, the run prints `::warning::` and writes
      `.windycivi/errors/field_regressions.json`, a JSON list with one entry per field:
      `state`, `night`, `field`, `bills_lost`, `bills_had`.
    - The file is deleted on a night nothing fires, and the run never stops.
    - "Had" counts last night's kept values, so it fires again every night the scraper stays
      broken.
  - **Deleted:** `compare_action_counts`, `find_new_actions`, `create_action_identifier`. Their
    mentions in comments in `timestamp_tracker.py` and `audit-last-real-activity.sh` are
    updated. `actions/openstates-scrape-audits/internal/what-does-healthy-mean.md` still names
    `find_new_actions`, but as a past concern, so I left it.
  - **Tests:** new `actions/format/test_bill_nightly.py`, 15 tests that run whole nights
    through `load_json_files` + `process_and_save`:
    - the GA cosponsor, version and title-fix cases;
    - the chamber gap;
    - a rewording on a same-count night, logged as a correction;
    - a rewording already in the log keeping its stamp;
    - new-action stamps;
    - a no-change night (every file identical, mtime too);
    - guard (a): kept and recorded, file unchanged while still missing, comes back, missing field, blank
      title, a field that was already empty, rewording after kept actions;
    - guard (b): a line break in a description;
    - guard (c): 52% fires, 50% doesn't, 19 bills don't, fires again the next night, cleared
      when fixed.

    `python3 test_log_jsonl.py` (44), `test_backfill_logs.py` (4) and `test_bill_nightly.py`
    (15) all pass.
  - **Snapshot:** I rendered `snapshots/wy` the way `render_snapshot.sh` does (jq sanitize,
    then `main.py` with `first_seen` 2025-11-25) into scratch. Masking the run-time stamps
    (`log_file_created`, `logs_latest_update` and the day keys in `latest_timestamp_seen.txt`,
    which differ on every render), it is identical to the committed one. The snapshot is a
    single first night, so every bill takes the new-bill path, which is unchanged. **No
    snapshot update.**
  - **Docs updated:**
    - CLAUDE.md "Bill activity logs";
    - `DATA_STRUCTURES.md` (new "Every bill, every night" paragraph under `action_logs.jsonl`);
    - `how-bill-and-vote-files-are-processed.md` (bill steps 1–6, the chamber-gap note
      removed, "Still open" item 1);
    - the option C bullet in `jsonl-logs.md`.
  - **Not done, for whoever picks it up:**
    - `tamara-notes/state-specific/il.md` and a new `ky.md` for the two regressions, and the
      OpenStates reports (outward-facing, so Tamara's call).
    - `audit-last-real-activity.sh` still counts `logs/*.json` filenames, so it has been stale
      since the JSONL layout (#306), apart from this change.
- **25 Nov, review change made: `last_kept` dropped.** `kept_empty_fields.json` now holds only
  `{"first_kept": <scrape>}` per bill and field, so it changes only when a field is first kept
  or comes back. The nightly "Kept last night's <field> on N bills" line is counted from the
  bills kept tonight. The test now checks that a still-missing night leaves the file's bytes
  unchanged and prints the line. `DATA_STRUCTURES.md` and `how-bill-and-vote-files-are-processed.md`
  updated. All three test suites pass (44 + 4 + 15).
  - **`.windycivi/errors/` is committed** in the data repos: IL, KY and WY each track files
    under `.windycivi/errors/missing_session/` (`git ls-files .windycivi` on the SSD copies).
    So the change does keep the nightly diff clean.
- **25 Nov, dry run.** Five states, on the latest raw scrape (the last commit touching
  `_data/<st>/`, `first_seen` = its commit time, jq-sanitized as `main.sh` does). Each ran on two
  fresh clones of `/Volumes/govbot-data/govbot_data/full/<st>-legislation` (`origin` removed),
  one with today's code (`4a645850`) and one with the new code, then a second new-code run
  after committing the first in the clone. Everything is under
  `/Volumes/govbot-data/scratch/option-c-dry/` (script `dryrun.sh`, `dryrun_report.py`,
  `classify.py`; per-state reports in `<st>/report1.json`; clones kept for inspection). The
  first attempt filled the laptop disk on MT's clone; it was deleted and everything re-run on
  the SSD with the final code.

| State | Bills | New log lines | Bills with a `metadata.json` change, by field | Guard (a) kept | Guard (c) fired | Second run changes | Runtime, old vs new |
|---|---|---|---|---|---|---|---|
| WY | 335 | 0 | 3: `actions` 3 | — | no | 0 | 1.1 s vs 1.0 s |
| KY | 1,737 | 0 | 1: `abstracts` 1 | `sponsorships` 1,707 | `sponsorships` 1,707 / 1,707 | 0 | 1.6 s vs 2.5 s |
| GA | 176 | 0 | 0 | — | no | 0 | 0.6 s vs 0.6 s |
| IL | 12,809 | 0 | 729: `sponsorships` 706, `actions` 704, `documents` 3, `title` 1 | — (see below) | no (see below) | 0 | 24.2 s vs 41.4 s |
| MT | 4,495 | 0 | 1,732: `actions` 1,732 | — | no | 0 | 11.5 s vs 16.4 s |

  - **0 new log lines everywhere**: the backfill had logged everything in these scrapes. **0
    changes of any kind on the second run** everywhere (idempotent; `metadata.json` untouched).
  - **What the `metadata.json` changes are** (all things the skip had hidden; the log already had
    them):
    - **WY**: 3 rewordings, now in `metadata.json` with the old stamp. HB0144 "H COW:H Motion to
      move Bill up for Consideration Failed…" → "H Motion to move Bill up in General File
      Failed…"; SF0124 "Amend and Do Not Pass" → "Amend and Do Pass Failed" (and
      `committee-failure` classification); SJ0006 "Recommend Amend and Do Pass" → "Recommend Do
      Pass".
    - **KY**: SB4's abstract, whitespace only (`\r\n` and indentation added). Guard (b) covers
      action descriptions only, so this rewrites `metadata.json`. If KY flip-flops it nightly
      it would churn; it didn't between these two runs. Your call whether abstracts need the same
      rule.
    - **IL**: a legislator renamed in the scraper, on every bill they touch: 716 sponsorships
      "Dan Ugaste" → "Daniel J. Ugaste" (name + `person_id`) and 771 matching actions "Added
      Co-Sponsor Rep. Dan Ugaste" → "…Daniel J. Ugaste" (HB1016, HB1023, HB1035). 5 actions
      with a new date or wording (HB3275 2026-08-11 → 08-07; HB2783; SB4040 "Senate Floor
      Amendment No. 1 Adopted" → "…Withdrawn"). 3 bills gained a document (HB3659, HB4587,
      SB3925). HB5813's title "EVICTION-NONPAYMENT OF RENT" → "FAIR RENTAL ENFORCEMENT ACT".
    - **MT**: the 2026-08-10 rewording: 10,976 actions "(H) First Reading" → "(H) 1st Reading"
      (classification `reading-1` dropped too), and 2,334 "(S) Committee Executive Action--Bill
      Concurred as Amended - …" → "(S) Committee Executive Action - …" (HB1, HB10, HB100).
    - Counts by field are bills; the action/sponsor counts above are entries.
  - **IL abstracts: guard (a) kept none, and that's correct on this data.** The IL repo was
    created on 2026-07-21 (first commit), eight days after the scrape lost abstracts on 07-13,
    so no IL `metadata.json` has ever had one: 0 of 12,809 now, HB1016's whole history has 0, and
    0 of 300 sampled bills in the latest scrape. Nothing to keep, and guard (c) can't fire (0
    bills had it). Getting them back would mean reading them from the raw history before
    07-13; not option C's job. Worth noting in `il.md`.
  - **KY** matches the review exactly: guard (a) kept `sponsorships` on 1,707 bills (all with
    `first_kept` = the 2026-09-29 scrape, since today's skip had been protecting them until
    now), and `field_regressions.json` holds one entry: `{"state": "ky", "night":
    "2026-09-29T10:33:32+00:00", "field": "sponsorships", "bills_lost": 1707, "bills_had":
    1707}`.
  - **Pre-existing, same with today's code:** every run rewrites
    `.windycivi/bill_session_mapping.json` (key order follows the folder listing, so it differs
    between machines) and `latest_timestamp_seen.txt`. Both identical between old and new code.
  - **Runtime:** at most 1.7× (IL 24 s → 41 s), from reading each bill's action log every night.

## Review

(reviewing chat)

- **25 Nov, in progress:** measuring nightly field losses in the raw history of KY, GA, WY, MT,
  TN, IL, CA and NH to set guard (c)'s threshold, and counting no-identifier votes split across
  ids in all repos. Results will be added here.
- **25 Nov, item 4 (out of scope) measured: keep it out.**
  - **Method:** in every converted repo, I took each vote's current version, kept those with no
    roll-call identifier, and grouped them by bill + date + motion + chamber. A group with
    two or more ids and different counts is either two real roll calls (like PA HB 1549) or
    one vote whose counts were corrected and got logged as a new vote.
  - **Result:** 1,190 such groups (2,633 ids) out of 129,812 no-identifier votes, about 0.9%.
    Most are in NY (286), AZ (218), MI (209), NH (183) and IL (132).
  - **Both kinds are in there.** Some are clearly separate votes (DE HB445 "SM": 15–26 and
    26–8). Some look like corrections:
    - NH HB131: "other" 52, then 53, then 56;
    - MI SB0989: yes 105, then 108;
    - AZ HB2380: all zeros, then 32–23.
  - Telling them apart would need the raw history: is the earlier version still in the
    latest scrape?
  - Nothing reads the vote logs yet, so this stays a known gap. Revisit it when something
    starts using `vote_event_logs.jsonl`. Script:
    `/Volumes/govbot-data/scratch/backfill/count_split_votes.py`.
- **25 Nov, guard (c) threshold measured: keep 50% with at least 20 bills.**
  - **Method:** I replayed every scrape in the raw history of KY, GA, WY, MT, TN, IL, CA and
    NH. For each night and field, I counted the bills that had the field in their previous
    version and have it empty tonight (script:
    `/Volumes/govbot-data/scratch/backfill/field_loss.py`).
  - **Losses are rare:** only 40 night/field rows with any loss in 8 states.
  - **The gap is wide.** Among rows with 20+ bills, every real failure lost 69–100% of the
    field, and everything else lost under 20%. Nothing fell between 20% and 50%. The 50%
    threshold catches all of these:

| State | Night | Field | Bills that lost it / had it |
|---|---|---|---|
| IL | 2026-07-13 | abstracts | 8,648 / 8,648 |
| KY | 2026-08-20 | sponsorships | 1,707 / 1,707 |
| NH | 2025-12-25 and 12-30 | sponsorships | 1,143 / 1,143 (each night) |
| NH | 2026-08-21 | versions | 1,126 / 1,155 |
| NH | 2026-01-28 | documents | 33 / 33 |
| TN | 2026-06-26 and 06-27 | subject, documents | 25–61 bills, 69–100% |

  - **Two never came back, so guard (a) matters a lot.** In each state's latest raw scrape
    (IL 2026-09-25, KY 2026-09-29), 0 of 400 sampled bills have IL `abstracts` or KY
    `sponsorships`. NH and TN recovered.
  - **Without guard (a), option C would wipe** every IL abstract and every KY sponsor from
    `metadata.json` on the first night. Today's skip protects only the bills whose action count
    hasn't changed.
  - **Add to the dry run:** run IL as a fifth state. Guard (a) should keep abstracts on about
    8,600 bills and guard (c) should fire for `abstracts`. KY should do the same for
    `sponsorships`.
  - Both are scraper regressions to record in `tamara-notes/state-specific/` (see below).
- **25 Nov, code review: good, with one change before committing.** The diff and
  `utils/bill_guards.py` match the plan, the tests cover the right cases, and the early dry-run
  numbers (0 new log lines, 0 second-run changes, KY guard (a) + (c) as expected) are what we
  wanted.
  - **Change: drop `last_kept` from `kept_empty_fields.json`; keep only `first_kept`.**
    - Today every kept entry's `last_kept` moves forward every night. With IL (about 8,600
      bills) and KY (1,707) that's about 10,000 changed lines in the data repo's commit every
      night, even when nothing happened. That breaks "a night's diff is exactly its new
      activity".
    - With only `first_kept`, the file changes only when a field is first kept or comes back.
    - The nightly printed "Kept last night's … on N bills" line already shows it's still
      ongoing. Count from the bills kept tonight, not from `last_kept`.
    - Update the test that checks `last_kept`.
  - **Check:** whether `.windycivi/errors/` is committed in the data repos (look at
    `git ls-files .windycivi` in an SSD copy). The change is right either way, but say which.
  - **Expected, not a bug:** `field_regressions.json` and its `::warning::` repeat every night
    for as long as IL abstracts and KY sponsors stay missing. That's a one-entry diff per night.
  - **Runtime:** IL 28 s → 51 s and KY 1.6 s → 3.1 s are fine for a nightly job.
- **Not part of option C:** record the IL abstracts and KY sponsors regressions in
  `tamara-notes/state-specific/` (`il.md`, a new `ky.md`). Reporting them to OpenStates is
  Tamara's call. The reviewing chat can write the state files.
- **25 Nov, dry run reviewed: approved to commit (Tamara decides when).**
  - Everything matches: 0 new log lines and 0 second-run changes in all five states; KY
    exactly as predicted; the `metadata.json` changes are all updates the skip had hidden.
  - IL abstracts: right that nothing was kept, since the repo never had them. Recovering them
    from the raw history before 07-13 is separate work, to note in `il.md`.
  - KY SB4's whitespace-only abstract change: leave it. It's a one-time rewrite. Extend the
    whitespace rule to abstracts only if the auditor later shows it changing back and forth
    nightly.
  - `.windycivi/bill_session_mapping.json` key-order churn: already there before option C, but
    it adds noise to every nightly diff. A separate one-line PR (sorted keys), not this one.
  - The PR description should cover: the skip removed, new actions checked against the log
    (the chamber gap closed), guards (a)–(c) with the measured threshold, the IL/KY/NH
    evidence, and the dry-run table.
