# Converting the govbot-data repos to JSONL activity logs: results

*25 Nov 2026*

## Review and next steps (25 Nov 2026, Tamara + Claude)

Reviewed after the overnight run. The flip-flop fix below is agreed. The review also found a
second problem of the same kind, in the action logs, and it affects pushed repos too.

### 1. Flip-flops: agreed, with two additions

Go with the proposed fix: log a version of a vote only if it differs from *every* version
already logged for that vote. Losing a genuine A → B → A revert is acceptable.

- Re-run the 16 held repos from scratch with the fix; don't patch the current output.
- Check what's left after the re-run. ND has 16,268 corrections, but only 9,265 are returns to
  an earlier version, so about 7,000 corrections on 2,180 votes would remain. Look at the most-corrected votes to confirm
  the changes are real and not noise the vote comparison is missing.

### 2. New finding: reworded actions are logged as new actions

When a scraper rewords an action it already published, the log treats the new wording as a
new action and stamps it with that night's date. Example: on 2026-08-10 the MT scraper renamed
"(H) First Reading" to "(H) 1st Reading" on every past bill. MT HB794's first reading
(2025-02-26) now has two lines: the old wording (first seen 2025-11-27) and the new one
(first seen 2026-08-10). A reader asking "what's new since yesterday" on 2026-08-10 would see
thousands of old actions as new. KS shows another pattern: "Referred to Committee on
Judiciary" became "Referred to Senate Committee on Judiciary".

The count below is of lines whose wording is no longer in the latest raw scrape, on bills that still have an action
on that date. Each one has a twin with the new wording, logged later. Measured 25 Nov on the
converted clones in `govbot_data/full/`.

| State | Reworded lines | Share of action lines | Status |
|---|---|---|---|
| MT | 13,683 | 17% | held |
| CA | 5,115 | 5.5% | held |
| NH | 3,506 | 18% | pushed |
| KS | 3,183 | 19% | pushed |
| MO | 1,581 | 6% | held |
| USA | 1,104 | 1.8% | pushed |
| IL | 977 | 0.6% | held |
| IA | 652 | 2.4% | pushed |
| DC | 502 | 3.6% | held |
| FL | 461 | 1.7% | pushed |
| AK | 422 | 1.9% | pushed |
| MA | 283 | 0.5% | pushed |
| RI | 277 | 1.9% | held |
| VT | 219 | 1.6% | pushed |

The rest are about 100 or fewer per repo. This is also why KS's action count jumped from 11,067 to 16,456: the
old one-file-per-action layout overwrote a reworded action, while the backfill keeps both
wordings. The nightly formatter uses the same rule, so this would keep happening once the
scrapers are unpaused.

A separate, smaller pattern: some actions kept their wording but moved to a different date
(MO 1,159 lines, e.g. calendar entries). These are left alone for now.

**Agreed rule (settled 25 Nov with the conversion chat):**

- **"Before" is the previous scrape, not the log.**
  - The nightly writer reads it from the bill's existing `metadata.json`. The formatter already
    loads it in `io_utils.py` (`load_existing_metadata`). A check of 400 KS bills found
    `metadata.json` keeps the scrape's action order exactly.
  - The backfill uses the previous raw commit's version of the bill.
  - A count taken from the log won't work. The log keeps actions the scraper later dropped (KS:
    1,138 lines), so those dates would never match again.
  - A new bill (no `metadata.json`) has nothing to reword.
- **When it's a rewording.** For each bill, date and chamber, compare the previous scrape's
  actions with tonight's. It's a rewording when:
  - the counts match; and
  - the actions whose wording didn't change are in the same relative order in both.

  The changed ones are then paired slot by slot: `[A, B, C]` → `[A, B', C']` pairs B with B'
  and C with C'.
- **When not to pair.** If either test fails, log the new wording as a new action, as today.
  No text-similarity matching: it's harder to explain.
  - The one case the test can't catch is a whole date reworded *and* reordered the same night.
    It should be rare.
  - A wrong pairing does little harm: each old id still ends with one current wording.
- **Corrections.** A rewording is appended as a correction under the paired action's `id`.
- **Report.** Count fallbacks ("logged as new") per repo, separately from corrections. If KS
  falls back often, revisit the rule.
- **Depends on bill-skip option C.** Today the formatter skips a bill whose action count is
  unchanged, so a night that only rewords actions is never seen by the nightly writer, though
  the backfill sees it. The nightly writer and the backfill only agree once option C (always
  process every bill) is in, and that has to happen before the scrapers are unpaused.

**What readers show for a corrected entry (settled):**

- **One entry per id, in the current wording,** in `govbot logs`, the Python readers and the
  weekly audit. `audit_states.py` counts distinct ids, not lines.
- **Which `first_seen` it carries:**
  - **Actions** keep the *first* line's `first_seen`: a rewording isn't news.
  - **Votes** keep the correction's `first_seen`, as the Rust reader does today: a change in
    result, counts or member votes is news.
  - Today the Rust reader (`logs_jsonl.rs`) replaces the whole record on a correction. If that is
    simply extended to actions, every reworded action would look new again.
- **`check_conversion.py`.** Replace the duplicate-id failure with a narrower check: an id may
  repeat only if all its lines share bill, date and chamber. A repeat across dates is a pairing
  bug and should still fail the repo.
- **Nothing is lost.** The `.jsonl` file keeps every wording in order, and git shows the night
  each arrived. `govbot logs` is "what's true now"; the file is the history. No flag for showing
  old wordings.
- **Docs to update.** `DATA_STRUCTURES.md`, `llms.txt`, the line schema descriptions and
  CLAUDE.md's "Bill activity logs" section should say that the last line per id is the current
  wording and earlier lines are history.

The script used for the count is `/Volumes/govbot-data/scratch/backfill/reworded_actions.py`.
To run it, start in `/Volumes/govbot-data` and run `python3 scratch/backfill/reworded_actions.py <state code>`.
It prints the state, its action lines, its reworded lines, their share, and the night with the most of them.

### 3. Run 2 review: the last line can stay on a bad version (25 Nov)

Run 2 (both fixes in, report in `/Volumes/govbot-data/scratch/backfill/reports/run2.md`) cut
vote corrections sharply (IL 2,387 → 3, CO 1,303 → 9). Action counts are unchanged and
rewordings are paired. But the every-version rule from section 1 has a flaw: **when a vote goes
back to a version already logged, nothing is appended, so the last line, which is what readers
show, stays on the old one.**

Each held repo's last line per vote was compared with the latest raw scrape:

| State | Votes | Last line differs from today's scrape | What it is |
|---|---|---|---|
| ND | 2,180 | 1,169 | ND's site was down: a voter came back as "Service Unavailable". 6 bad nights (2025-12-30, 2026-04-22, 04-30, 06-20, 06-24, 08-11), about 1,150 votes each. |
| TN | 19,062 | 6,964 | Roll calls went from names to empty (HB6005: `['Baum', 'Boyd', …] → []`). 6,787 votes over 63 nights, 5,839 of them on 2026-07-02. Today's scrape has the names again. |
| DE | 2,063 | 1 | SB315: pass → fail → pass. The reader shows `fail`; the scrape says `pass`. |
| MI | 1,628 | 7 | "O’Neal" alternates between a broken apostrophe (`\x92`) and `’`. The broken one is shown. |
| The other 12 | | 0 | |

Pushing ND and TN as they are would publish more than 8,000 wrong roll calls as current.
None of the 16 is pushed.

The check script is `/Volumes/govbot-data/scratch/backfill/stale_last_line.py`. To run it, use
`python3 stale_last_line.py <folder holding actions/format/utils> <state code>`. It prints the
number of votes whose last line matches, differs from, or is missing from the latest raw scrape.

**Agreed fix.** Two parts.

The logs mean the same thing in every state. Readers (`govbot logs`, `llms.txt`, Sartaj's
tagging, local agents) rely on "the last line per id is the current version", so this part of
the rule is the same for all 56 states:

1. If tonight's scrape contains the version that's already the vote's last logged line, log
   nothing. This keeps the flip-flop fix: the flip-flops come from one scrape holding two
   versions of one vote.
2. Otherwise, if tonight's version differs from the last logged line, log it, even if it matches
   an earlier version. A real revert is logged, so the last line always matches the current
   scrape.

Scraper failures are caught per state, not by a general rule. A general rule like "skip a roll
call that becomes empty" would be wrong elsewhere: in OK
(`HB2374 ['STRIKE THE TITLE - ADOPTED'] → []`) and HI (`GM730 ['Senator(s'] → []`), the same
kind of change is the scraper fixing its parsing. The fix is one small table in `log_jsonl.py`,
one entry per state, each with its evidence, date and the OpenStates issue in a comment:

- `nd`: treat a vote version as not scraped if any voter is named "Service Unavailable" (or
  "Proxy Error", added after run 3, see section 4).
- `tn`: treat a vote version as not scraped if its roll call is empty while the last logged
  version has voters.

States with no entry get the default rule. Each entry is a stopgap for an OpenStates scraper
bug. When OpenStates fixes it, delete the entry. The bugs and their fix status are tracked in
`tamara-notes/state-specific/nd.md` and `tn.md`. DE and MI need no entry: rule 2 alone fixes
them.

### 4. Run 3 review (25 Nov): approved, plus one more ND error string

Run 3 put all 16 held repos on rules 1–2 and the ND/TN table. Every check is clean, and in
every repo each vote's last line matches the latest raw scrape. Report:
`/Volumes/govbot-data/scratch/backfill/reports/run3.md`. ND skipped 5,818 versions and TN
skipped 6,787, the counts in `nd.md` and `tn.md`. The large single nights in OH, MO, SC, MT, OK
and HI are the same as in run 2: one real change each, which the rule leaves alone.

**ND also saves "Proxy Error" as a voter.** I scanned all 16 converted repos for voter names
that look like error text rather than people. ND has 1,181 lines with a single voter named
"Proxy Error", over two nights: 2026-08-29 (1,166 votes) and 2026-09-19 (15). The other chat
found the first night. Each vote's next scrape has the real names, so those lines are junk
followed by a "revert". That accounts for almost all of ND's 1,183 reverts. It's the same bug as
"Service Unavailable" (a different error page from the same site). The fix: ND's table entry
treats a version as not scraped if any voter is named "Service Unavailable" or "Proxy Error",
using an explicit list, not a pattern match. After the re-run, ND should show about 7,000
skipped, about 0 reverts, and 0 "Proxy Error" lines.

None of the other 15 repos has error-page voters. A few have text parsed from the page as a
voter. These are scraper parsing bugs, not failed scrapes, so they don't belong in the table
(the logs show what OpenStates scraped):

- OK: 667 lines with amendment text as voters ("AMD SB1794 CA1 - ADOPTED"). The scraper later
  fixed all of them, so none is a current version.
- TN SB1414: one current vote with a voter named "Lafferty -- 1. HB1242 by Helton-Haynes".
- MI HB5697: one current vote with a voter named "sections 279 and 679.".

These go in the OpenStates reports alongside ND and TN, as low priority.

TN's 1,158 reverts and 5,630 lines with `first_seen: null` are expected. They're old-layout vote
files from before the raw history began, with empty roll calls, each followed by the version
with voters. The schema allows `null` for exactly this case.

**Pushing:** the ND change affects only ND, so the other 15 repos come out the same. Push those
15 now, one at a time, as planned. Push ND after its re-run shows the numbers above.

### What to do next, in order

Steps 1–3 below were done on 25 Nov (run 2). Step 3a replaces the push in step 3.

1. In PR #308, add both fixes to `log_jsonl.py`:
   - the vote rule ("differs from every logged version");
   - the action rewording rule.

   Add tests for each: a vote flip-flop A → B → A logs two versions, and the MT
   "First Reading" → "1st Reading" case logs one correction, not a new action. Update the
   decisions in `jsonl-logs.md`, `DATA_STRUCTURES.md` and CLAUDE.md's "Bill activity logs"
   section.
2. Make the Rust reader (`actions/govbot/src/logs_jsonl.rs`) and the Python readers take the
   last line per `id` for actions too, so `govbot logs` shows one entry per action, in its
   latest wording.
3. Re-run the 16 held repos from scratch. For each one, report:
   - before/after action counts;
   - nightly correction counts for votes and actions;
   - the five most-corrected votes and actions.

   Push them one at a time, fetching first and confirming the tree after.

   3a. **Next (conversion chat), from section 3:**
   - Change `select_new_votes` to rules 1–2 and add the ND/TN table.
   - Add tests:
     - an in-scrape A/B flip-flop logs once;
     - A → B → A logs three lines;
     - an ND "Service Unavailable" night logs nothing;
     - a TN empty roll call logs nothing;
     - an OK-style change to an empty roll call is still logged.
   - Update the decisions in `jsonl-logs.md`, `DATA_STRUCTURES.md` and CLAUDE.md.
   - Re-run all 16. The report adds two columns per repo: "last line differs from latest raw
     scrape" (must be 0) and "versions skipped as scraper failures".
   - Bring the table to Tamara before pushing anything.

   Done (run 3). See section 4.

   3b. **Next (conversion chat), from section 4:**
   - Push the 15 non-ND repos one at a time: fetch first, confirm the remote matches after.
   - Add "Proxy Error" to ND's entry in `log_jsonl.py`, as an explicit list alongside
     "Service Unavailable". Add a test for it, and update `nd.md`'s workaround paragraph if the
     function name changes.
   - Re-run ND. Expect about 7,000 skipped, about 0 reverts, 0 "Proxy Error" lines, and 0
     last-line differences. Then push it.

   Done (25 Nov). The 15 were pushed with no remote changes in between; each pushed tree
   matched, with no old `logs/` paths left. "Proxy Error" is in `_ND_ERROR_PAGES`
   (`_nd_error_page`, PR #308 commit b3acaf26). ND's re-run: 6,999 skipped, 2 reverts,
   6 vote corrections (was 2,368), 0 error-page voters, 0 last-line differences; pushed as
   d5a6308c. All 55 repos with logs are now converted and pushed (GU has none).
4. **Decide (Tamara):** whether to fix the pushed repos (KS, NH, USA, IA, FL, AK, MA, VT and the
   smaller ones) with one follow-up commit each that rebuilds their logs under the new rules.
   It would be a normal new commit, not a history rewrite, done before the scrapers are
   unpaused while nothing writes to the repos. Recommended: yes, otherwise those repos keep
   about 2–19% duplicate actions.

   **Decided 25 Nov: no rebuild.** The focus is getting future nights right, and the
   duplicates are now known and documented. What stays:
   - In those repos, actions reworded before the rule appear twice (old and new wording,
     two ids). Rewordings from now on are corrections under one id.
   - Votes need no rebuild: on the first nightly run, any vote whose last line differs from
     that scrape gets the current version appended (rule 2), so it corrects itself. Only votes
     no longer in the scrape keep their old last line.
   Don't reopen this unless a reader or user is actually hurt by the duplicates.
5. Before the scrapers are unpaused: bill-skip option C (always process every bill), so the
   nightly writer sees rewordings the same way the backfill does (see the agreed rule above).
6. Still required before the scrapers are unpaused, unchanged: fix the auto-merge step that
   saved conflict markers into the raw commits (find out first why #100 was reverted).

## Summary

Every `govbot-data` repo has been converted on the SSD to the new per-bill activity logs
(`action_logs.jsonl` and `vote_event_logs.jsonl`, from PR #306). **39 repos are converted and
pushed.** **16 are converted but held**, because of one rule problem in how vote corrections
are logged (see "Decision needed"). GU has no logs, so there was nothing to change. In every
repo:

- no old log entry was lost;
- every line is valid against the line schemas;
- every entry has a real `first_seen` date.

## What the conversion does

For each repo, on a full-history clone:

1. **Backfill.** `actions/format/backfill_logs.py` replays the raw scraper history (every
   nightly scrape since late November 2025) into each bill's two log files. Each entry is
   stamped with the commit time of the scrape that first contained it. This recovers votes
   the old one-file-per-entry layout had lost, and gives every entry the night it first
   appeared.
2. **Convert.** `actions/format/convert_logs.py` folds in the old `logs/*.json` files and
   deletes them, along with the `sessions/<s>/logs/` symlinks. Where an old file and a
   backfilled line are the same entry, the backfilled line stays.
3. **Check** against the untouched original:
   - every line is valid against the schema;
   - every old action, and every old version of each vote, is in the new files;
   - no old `logs/` folders are left.

   A separate check confirms the backfill recovered the bills in the raw commits with
   conflict markers (below).
4. **Commit and push**, one repo at a time. Before each push the repo is fetched and
   re-checked if GitHub had moved. After it, the pushed tree is confirmed to match. Each
   commit message cites chihacknight/govbot#308.

The code is in PR #308. That PR also changes how a vote is identified: by roll-call
identifier **plus date and motion**. VA and MT reuse one identifier across different votes.
With the old rule, VA logged about 600 false "corrections" a night, and 608 old votes
collapsed into 377. With the new rule, VA has 762 votes and 0 corrections a night.

## Decision needed: vote "flip-flops" (16 repos held)

In some states a single scrape contains two versions of the same vote. For example, in OH
HB 14 a 6–0 "Reported" vote appears once as `pass` and once as `fail`. In ND, MT and others
the lists of who voted differ (in MT, one copy says "Sen Elect Gregg Hunter" and the other
"Gregg Hunter"). The current rule compares each version only with the last one logged, so
the log alternates A → B → A every night. TN has the most: 13,276 returns to an earlier
version, across 9,648 votes.

The logs are append-only, so these repos are held until the rule is fixed. The same rule is
used by the nightly formatter, so it needs fixing before the scrapers are unpaused anyway.

**Proposed fix:** log a version only if it differs from *every* version already logged for
that vote, not just the last one. Flip-flops stop, and each real version still appears once.
The trade-off is that a genuine revert (A → B → back to A) isn't logged again. The repos
already pushed have no flip-flops, so this fix would leave them exactly as they are.

Held repos: CA, CO, DC, DE, HI, IL, MI, MO, MT, ND, NJ, OH, OK, RI, SC, TN.

## Other findings

- **Corrupted raw commits.** Six raw scraper repos have an "Auto-merge: kept scraped data"
  commit with git conflict markers saved inside the files: CT, GA, TX, OH, WV and LA
  (2026-06-26 to 2026-07-21). No data was lost, because the backfill also reads both
  scrapes that were merged. The auto-merge step itself still needs a fix, separately,
  before the scrapers are unpaused.
- **Raw bills from other sessions.** Many raw histories include bills from sessions the
  formatted repo doesn't hold (for example TX 89R: 11,503; NJ 221: 11,795). These are listed
  in the reports and not written. They belong to the session split, which comes later.
- **IL.** For a few days in September the formatter wrote 118 IL bills' actions as
  `logs/action_logs.jsonl`. The converter now folds those in too (in PR #308), and IL
  converts cleanly with that fix. It is held for flip-flops.
- **GA.** The live repo was re-created with only the 2026 special session (`2026_ss`), the
  same way CT was. The backfill follows the live repo.
- **PR (Puerto Rico).** Two file names in its `files/` folder differ only in capital
  letters. It was converted on a case-sensitive disk so both are kept as they are.
- **Voter renames count as corrections.** This is deliberate. If a scraper renames a voter
  across old roll calls, each affected vote gets one more line (GA: 756 when "ISLAM PARKES"
  became "PARKES").

## Results by repo

"Votes (old → new)" counts distinct votes; "+N corr." is later corrections to them. The two
rule columns apply to the six states whose votes carry identifiers. "Corrections/night" is
the average, with the largest single night in brackets.

| State | Scrapes | Actions (old → new) | Votes (old → new) | Old files lost | Null first_seen | Schema failures | Votes, old rule → new rule | Corrections/night, old → new | Unusual | Push |
|---|---|---|---|---|---|---|---|---|---|---|
| CT | 155 | 11,599 → 11,611 | 0 → 0 | 0 | 0 | 0 |  |  | pilot; conflict markers 1834 files (2026-07-21), all recovered; 4,076 raw bills in 2025 with no folder | PUSHED 2fd0710a |
| AK | 330 | 21,451 → 22,318 | 671 → 1,109 | 0 | 0 | 0 |  |  |  | PUSHED 8c24b1c4 |
| AL | 256 | 14,427 → 14,718 | 0 → 0 | 0 | 0 | 0 |  |  |  | PUSHED 34f5234c |
| AR | 256 | 28 → 28 | 0 → 0 | 0 | 0 | 0 |  |  | raw bills with no folder: 1928 in 2025 | PUSHED 3ae7791 |
| AZ | 136 | 14,190 → 14,190 | 3,174 → 3,446 | 0 | 0 | 0 |  |  |  | PUSHED f76c503c |
| CA | 302 | 89,043 → 93,479 | 21,331 → 21,566 +202 corr. | 0 | 0 | 0 |  |  | flip-flops: 198 returns on 1 votes | held |
| CO | 270 | 7,666 → 7,690 | 2,270 → 3,798 +1,303 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 35 in 2025B; flip-flops: 1,294 returns on 9 votes | held |
| DC | 327 | 13,062 → 13,798 | 1,136 → 1,698 +11 corr. | 0 | 0 | 0 | 1,697 → 1,698 | 0.0 → 0.0 (max 2 in one night) | flip-flops: 8 returns on 3 votes | held |
| DE | 291 | 6,961 → 7,122 | 1,821 → 2,063 +248 corr. | 0 | 0 | 0 |  |  | flip-flops: 245 returns on 2 votes | held |
| FL | 351 | 26,514 → 27,010 | 13 → 2,709 +453 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 19 in 2026, 6 in 2026D | PUSHED 3587b0ece |
| GA | 280 | 1,045 → 1,046 | 174 → 280 | 0 | 0 | 0 |  |  | conflict markers 914 files (2026-07-21); all recovered; raw bills with no folder: 5480 in 2025_26; live repo re-created with session 2026_ss only | PUSHED 97f37ea |
| GU | 268 | 0 → 0 | 0 → 0 | 0 | 0 | 0 |  |  | no logs at all, nothing to commit | — |
| HI | 241 | 67,879 → 68,034 | 8,173 → 8,895 +4,263 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 4704 in 2025; flip-flops: 1,888 returns on 944 votes | held |
| IA | 363 | 26,360 → 27,069 | 0 → 0 | 0 | 0 | 0 |  |  |  | PUSHED 8c6497f8f |
| ID | 297 | 8,150 → 8,635 | 853 → 853 | 0 | 0 | 0 |  |  | raw bills with no folder: 790 in 2025 | PUSHED 7c161ad6 |
| IL | 455 | 149,678 → 150,647 | 9,300 → 9,842 +2,387 corr. | 0 | 0 | 0 |  |  | flip-flops: 2,384 returns on 3 votes; 118 logs/action_logs.jsonl folded (needs df18c33f) | held |
| IN | 287 | 7,370 → 7,461 | 689 → 690 | 0 | 0 | 0 |  |  |  | PUSHED 8e153030 |
| KS | 295 | 11,067 → 16,456 | 0 → 0 | 0 | 0 | 0 |  |  |  | PUSHED 083976b1 |
| KY | 290 | 12,048 → 12,297 | 886 → 886 +116 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 1441 in 2025RS | PUSHED 5d970063 |
| LA | 252 | 30,413 → 30,524 | 3,135 → 3,172 | 0 | 0 | 0 |  |  | conflict markers 2 files (2026-06-30); all recovered; raw bills with no folder: 12 in 2025s1 | PUSHED dd125a0bd |
| MA | 439 | 51,994 → 52,481 | 0 → 0 | 0 | 0 | 0 |  |  | raw bills with no folder: 81 in 194th | PUSHED b1134da3bc |
| MD | 253 | 21,136 → 21,225 | 0 → 0 | 0 | 0 | 0 |  |  | raw bills with no folder: 2617 in 2025 | PUSHED 6a7ca61b0 |
| ME | 414 | 44,488 → 44,730 | 1,321 → 1,576 | 0 | 0 | 0 |  |  |  | PUSHED 5b19979d5 |
| MI | 562 | 29,101 → 29,283 | 1,267 → 1,628 +938 corr. | 0 | 0 | 0 |  |  | flip-flops: 619 returns on 206 votes | held |
| MN | 298 | 29,104 → 29,319 | 37 → 245 | 0 | 0 | 0 |  |  | raw bills with no folder: 2 in 2025-2026, 48 in 2025s1 | PUSHED cc3d4be92 |
| MO | 419 | 21,996 → 25,539 | 1,410 → 1,491 +4,537 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 15 in 2025S2, 47 in 2026; flip-flops: 4,258 returns on 219 votes | held |
| MP | 299 | 1,041 → 1,116 | 0 → 0 | 0 | 0 | 0 |  |  |  | PUSHED 9c1c79bdce |
| MS | 274 | 17,200 → 17,921 | 1,827 → 1,828 | 0 | 0 | 0 |  |  | raw bills with no folder: 106 in 20251E | PUSHED 5189bdfaa |
| MT | 401 | 66,644 → 79,955 | 8,715 → 8,730 +13,332 corr. | 0 | 0 | 0 | 8,726 → 8,730 | 43.8 → 33.2 (max 6162 in one night) | flip-flops: 6,496 returns on 2,693 votes | held |
| NC | 295 | 19,817 → 19,918 | 779 → 869 | 0 | 0 | 0 |  |  |  | PUSHED b7ec46dbd |
| ND | 288 | 15,399 → 15,489 | 2,170 → 2,180 +16,268 corr. | 0 | 0 | 0 |  |  | flip-flops: 9,265 returns on 1,174 votes | held |
| NE | 449 | 17,812 → 18,153 | 1,287 → 1,774 | 0 | 0 | 0 |  |  |  | PUSHED 1e7a89f6 |
| NH | 148 | 15,724 → 19,127 | 132 → 636 +1,091 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 1072 in 2025, 7 in 2026 | PUSHED 4660fa292 |
| NJ | 186 | 14,573 → 14,596 | 1,207 → 1,823 +5 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 11795 in 221; flip-flops: 4 returns on 1 votes | held |
| NM | 96 | 3,029 → 3,029 | 0 → 0 | 0 | 0 | 0 |  |  | raw bills with no folder: 2 in 2025S2 | PUSHED 7e250595 |
| NV | 291 | 141 → 175 | 33 → 33 | 0 | 0 | 0 |  |  |  | PUSHED 5908357 |
| NY | 573 | 102,858 → 102,935 | 10,139 → 10,850 | 0 | 0 | 0 |  |  |  | PUSHED b1892d8e97 |
| OH | 516 | 6,244 → 6,275 | 1,079 → 1,104 +1,682 corr. | 0 | 0 | 0 |  |  | conflict markers 464 files (2026-07-21); all recovered; flip-flops: 1,066 returns on 453 votes | held |
| OK | 278 | 56,445 → 57,653 | 8,476 → 8,766 +3,985 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 3257 in 2025, 5 in 2026; flip-flops: 1,050 returns on 2 votes | held |
| OR | 291 | 3,912 → 3,926 | 0 → 0 | 0 | 0 | 0 |  |  | raw bills with no folder: 3 in 2025S1 | PUSHED 207ca30 |
| PA | 238 | 17,590 → 17,613 | 5,164 → 6,615 | 0 | 0 | 0 | 6,615 → 6,615 | 0.0 → 0.0 (max 0 in one night) |  | PUSHED 1dc5da8d3 |
| PR | 443 | 53,569 → 54,278 | 0 → 0 | 0 | 0 | 0 |  |  | raw bills with no folder: 1 in 2025-2028; converted on a case-sensitive image (2 case-colliding files) | PUSHED 3ec89eadc |
| RI | 276 | 14,315 → 14,611 | 987 → 1,092 +620 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 2595 in 2025, 6 in 2026; flip-flops: 616 returns on 3 votes | held |
| SC | 357 | 18,518 → 18,597 | 1,022 → 2,051 +3,879 corr. | 0 | 0 | 0 |  |  | flip-flops: 1,956 returns on 262 votes | held |
| SD | 300 | 5,567 → 5,594 | 1,476 → 1,511 | 0 | 0 | 0 |  |  | raw bills with no folder: 2 in 2025s | PUSHED d2dc53e0 |
| TN | 215 | 120,031 → 140,160 | 15,937 → 19,062 +30,155 corr. | 0 | 0 | 0 |  |  | flip-flops: 13,276 returns on 9,648 votes | held |
| TX | 41 | 4,190 → 4,251 | 0 → 0 | 0 | 0 | 0 |  |  | conflict markers 582 files (2026-06-26); all recovered; raw bills with no folder: 592 in 891, 11503 in 89R | PUSHED 89ddd39 |
| USA | 688 | 60,907 → 62,602 | 832 → 852 | 0 | 0 | 0 |  |  |  | PUSHED 1399599530 |
| UT | 261 | 37,340 → 37,396 | 1,917 → 1,917 | 0 | 0 | 0 | 1,917 → 1,917 | 0.0 → 0.0 (max 0 in one night) | raw bills with no folder: 18 in 2025S1 | PUSHED 69fe59391 |
| VA | 85 | 1,314 → 1,314 | 608 → 762 | 0 | 0 | 0 | 377 → 762 | 606.3 → 0.0 (max 0 in one night) |  | PUSHED 80b7fb2 |
| VI | 14 | 689 → 689 | 0 → 0 | 0 | 0 | 0 |  |  |  | PUSHED a152ae8 |
| VT | 405 | 13,451 → 13,692 | 132 → 148 +26 corr. | 0 | 0 | 0 | 148 → 148 | 0.1 → 0.1 (max 26 in one night) |  | PUSHED 6e8e5e5c |
| WA | 420 | 35,089 → 35,867 | 2,070 → 2,302 +673 corr. | 0 | 0 | 0 |  |  |  | PUSHED e12934ad7 |
| WI | 330 | 31,615 → 31,685 | 1,696 → 2,298 | 0 | 0 | 0 |  |  |  | PUSHED 85263f69a |
| WV | 492 | 26,548 → 26,563 | 977 → 1,146 | 0 | 0 | 0 |  |  | conflict markers 14 files (2026-07-14); all recovered; raw bills with no folder: 2709 in 2025 | PUSHED 266c33dd0 |
| WY | 311 | 3,714 → 3,717 | 1,249 → 1,258 +616 corr. | 0 | 0 | 0 |  |  | raw bills with no folder: 556 in 2025 | PUSHED af8554b |
