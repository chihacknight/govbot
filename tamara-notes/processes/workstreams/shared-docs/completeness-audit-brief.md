# Completeness audit: every bill we have, for every state

Brief for the chat that does this. Written 2026-11-26 by the reviewing chat, from a discussion
with Tamara.

> **The goal of the whole project:** know whether we hold a complete set of legislation data for
> each state for 2026, and maybe 2025.
>
> **This phase:** build the complete list of what we have, everywhere we have it: every bill, in
> every repo and every generation of the data, including repos nobody has cloned yet and cloned
> data nobody has looked at. No judging completeness yet: no outside counts, no fixing. Stop for
> review when the list exists.

## Ground rules

- **Read-only everywhere.** Never push, never open a PR in a data repo, never change a repo's
  settings. `raw-scrapers/`, `govbot_data/full/`, `govbot-archive/` and `windy-civi/` on the SSD
  are read-only: no `git pull` or checkout there either. If a clone looks out of date, record
  that; to get a fresh copy, clone into your own scratch folder.
- **The windy-civi orgs:** reading and cloning them read-only is fine (Tamara asked for it).
  Cleaning them up is a later job; don't touch them otherwise.
- **SSD only.** Tamara's laptop disk is full. New clones go in
  `/Volumes/govbot-data/windy-civi/<org>/` (that folder has a README; keep its rules) or
  `/Volumes/govbot-data/scratch/completeness/clones/`. Work files and output go in
  `/Volumes/govbot-data/scratch/completeness/`.
- **Don't collide with the other chat.** The session-status chat rebuilds tables in
  `history.sqlite` on every run. Copy it to your folder and use the copy. Don't edit its brief,
  `session-status-brief.md`, or `history-analysis-plan.md`. Write only to this brief's Progress
  section.
- **Per-state rules, not one rule for all.** Bill numbers and session names differ by state and by
  generation. Record each mapping you make; never guess one.
- **Output as SQLite plus CSV:** Tamara reads them in DBeaver.
- Commit nothing. Tamara is the only person maintaining this data, in her free time: keep what
  she has to review short.

## Where the data is (checked 2026-11-26)

| Where | Repos | On the SSD | What it holds |
|---|---|---|---|
| `govbot-openstates-scrapers` | 56 `<st>-legislation` | all, `raw-scrapers/` (31 GB) | Raw scrapes since 2025-11-26. Each scrape replaces `_data/<st>/` wholesale, so older sessions exist only in git history. **Already listed:** `history.sqlite` table `bills`, 261,660 bills (every bill in any scrape, first and last seen, whether the data repo and the July archive have it). |
| `govbot-data` | 56 `<st>-legislation` | 55, `govbot_data/full/` (86 GB). **`pr-legislation` was never cloned.** | Today's formatted data, created 2026-07-21 with each state's current session only. Layout: `country:us/state:<st>/sessions/<s>/bills/<id>/metadata.json` plus the JSONL logs. The clones date from about 11-24; record each one's HEAD against GitHub's. |
| `govbot-archive` | 112: 56 `<st>-legislation` (July 2026) + 56 `-pre-rebuild-2026-07-21` | all, `govbot-archive/` (56 GB) | The formatted generation before the 07-21 rebuild. Older sessions (AR `2025`, GA `2025_26`, TX `89R`, `891`) are only in the July `<st>-legislation` copies. Only checked so far for bills that are also in the raw history; **anything only here hasn't been listed.** |
| `windy-civi-pipelines` | 60, mostly `<st>-data-pipeline` | FL and TX only, `windy-civi/windy-civi-pipelines/` | The generation before govbot (scrape and format in one repo). Last pushed 2025-10 to 2026-06. **Most likely where 2025 lives.** About 1.8 GB on GitHub. |
| `windy-civi-pipelines-V1-archived` | 94, including test and `-old` copies | TX only, `windy-civi/windy-civi-pipelines-V1-archived/` | An earlier version, from about July 2025. About 1.6 GB. |
| `windy-civi` | 7, archived (toolkit, docs, …) | no | Probably not bill data. Check names only; `usa-legislation-daily-news` is 8 KB. |
| `govbot-test` | **0 visible now** (there were 56 extraction-test repos) | no | Ask Tamara whether it was emptied on purpose. |
| Local leftovers | | `govbot_data/repos/` (56, old CLI clones: mostly the archive generation, plus live az, ct, dc, tx, va), `old-laptop-clones/` (`current`, `gb-practice`) | Probably copies of the above. Check that, and list anything that isn't. |

## The steps

1. **Inventory.** One table, `repos`: org, repo, state, path on the SSD (or "not cloned"), HEAD
   commit and date, GitHub's last push, size, layout (raw `_data/`, formatted `country:us/…`,
   windy-civi pipeline, other), and the sessions found. Every repo in every row above.
2. **Clone what's missing,** read-only, to the folders above:
   - `govbot-data/pr-legislation`;
   - every legislation repo in `windy-civi-pipelines` and `windy-civi-pipelines-V1-archived`
     (skip `.github`, bots and templates; list what you skipped).
   
   Full clones are fine at these sizes. Log every clone and its size.
3. **Learn each layout before reading it.** The windy-civi repos are older and may differ by
   state. For each layout, write down in Progress how a bill is stored (path pattern, the file
   that holds its id, session and title), with one real example path.
4. **List every bill, at HEAD and in history.** For each formatted or pipeline repo:
   - the bills present at HEAD;
   - every bill path ever added in its git history (`git log --diff-filter=A --name-only` is
     cheap), so bills that were later deleted count too, with the first and last commit date they
     were present.
   
   Raw repos are already done (`bills` in `history.sqlite`); reuse that, don't redo it.
5. **Match the same bill across sources, per state.** Bill numbers ("HB 1", "HB1", "HB0001") and
   session names ("2025", "2025-2026", "2025_26") differ. Build a mapping table per state
   (`id_rules`, `session_map`): each rule, its reason and an example. Where a match isn't certain,
   keep both and flag it.
6. **Combine into two tables:**
   - `bill_copies`: one row per bill per source: state, session, bill, source repo, at HEAD or
     only in history, first and last date present;
   - `holdings`: one row per state and session: the count in each source, the union, and how
     many are in only one source.
7. **Report in Progress:**
   - a per-state table for 2025 and 2026 sessions (other sessions found go in the tables, not the
     report);
   - the biggest gaps, with first explanations. Start with the 55,529 raw-history bills that
     aren't in the data repos: how many are sessions the 07-21 rebuild didn't carry over, how
     many are really missing;
   - anything surprising about where the data lives.
8. **Stop for review.**

## Output

`/Volumes/govbot-data/scratch/completeness/completeness.sqlite` (tables `repos`, `bill_copies`,
`holdings`, `id_rules`, `session_map`) plus a CSV of each in `…/completeness/csv/`.

## Not in this phase

- Outside counts: the OpenStates API (shows whether *we* lost bills, not whether OpenStates
  missed any), LegiScan (API key still pending), state sites.
- Fixing, restoring or backfilling anything.
- Bill text, votes and actions: this phase is about which bills exist. Record where actions and
  votes are, if it's cheap, but don't compare them.

## Open questions (Tamara's)

- **Answered 2026-11-26:** `govbot-test` never held anything; skip it.
- **Answered 2026-11-26:** every year we have. Tamara started in 2025, so expect 2025 onward; list
  anything older too.

## Progress

(The completeness chat adds dated entries here.)

### 2026-11-26: steps 1–7 done, stopped for review

**Output:** `/Volumes/govbot-data/scratch/completeness/completeness.sqlite` (tables `repos`,
`bill_copies`, `holdings`, `id_rules`, `session_map`; 224 MB) and the same as CSVs in
`…/completeness/csv/`. Scripts are in `…/completeness/scripts/` (`extract_bills.py`,
`extract_raw_files.py`, `inventory.py`, `combine.py`, `schema.sql`), and work files are in `…/work/`
(including my copy of `history.sqlite`, taken 19:10 on 11-26). I committed nothing, pushed
nothing, and ran no pull or checkout in the read-only folders.

**Step 1: inventory.** `repos` has 546 rows: 385 GitHub repos (56 raw + 56 govbot-data + 112
archive + 60 windy-civi-pipelines + 94 V1 + 7 windy-civi), 2 older SSD copies, 158 local
leftovers and 1 row for govbot-test (the org shows 0 repos, public and private). Every SSD clone's
HEAD equals GitHub's HEAD, so none are out of date. The windy-civi-pipelines repos show "pushed
2026-06", but their last commits are 2025-10-30 to 2025-12-14 (V1: to 2026-03-28, usa only).
GitHub's pushed date is not the data date.

**Step 2: clones.** 140 full clones, all succeeded, 45 GB on disk with checkouts (log:
`work/clone.log`):
- `govbot-data/pr-legislation`, in `scratch/completeness/clones/govbot-data/` (12 GB);
- 57 windy-civi-pipelines and 81 V1 repos, in `windy-civi/<org>/`;
- fresh FL and TX copies in `scratch/completeness/clones/windy-civi-pipelines/`. They turned out
  identical to the SSD copies.

Skipped, listed in `work/skipped.tsv` and `repos`: both `.github` repos,
`windy-civi-bluesky-bots`, `dev-repo-sync` and `test-pipeline`, plus 7 templates. Three of the
templates are big enough to hold data: `STATE-windy-civi-data-pipeline` (115 MB),
`windy-civi-template-no-scraper-data` (117 MB) and `template-data-pipeline-NSD` /
`-with-saved-scraper-data` (60 MB each). Say if you want them listed. `windy-civi` holds no bill
data; `usa-legislation-daily-news` is private and holds only `.github`.

**Step 3: layouts.** Each is shown with one real example path.
- *Raw* (`govbot-openstates-scrapers`): `_data/<st>/bill_<uuid>.json`; the id, session and title
  are inside the file. Reused `history.sqlite` `bills`.
- *Formatted* (govbot-data and both archive generations):
  `country:us/state:<st>/sessions/<session id>/bills/<id without spaces>/metadata.json`
  (`identifier`, `legislative_session`, `title`). Example:
  `country:us/state:tx/sessions/892/bills/HB1/metadata.json`.
- *windy-civi-pipelines:* the same layout, e.g.
  `country:us/state:ak/sessions/34/bills/HB1/metadata.json`, plus `files/` (bill text) and
  `logs/`. `.windycivi/sessions.json` maps session id → name.
- *V1:* `data_output/data_processed/country:us/state:<st>/sessions/ocd-session/country:us/state:<st>/<date_folder>/<session name>/bills/<id with spaces>/logs/*_entire_bill.json`.
  The `entire_bill.json` holds `identifier`, `legislative_session` and `title`. Example:
  `…/state:ar/2025-2025/2025 Regular Session/bills/HB 1001/logs/20250113T203909Z_entire_bill.json`.
  The session name maps back to the id through the repo's own `sessions/<st>.json`; all mapped.
  Some V1 repos instead use the plain `sessions/<id>/bills/<id>/` form.
- *Federal, both windy-civi orgs:* `country:us/congress/sessions/119/bills/…`, with no `state:`
  part.
- *Raw files inside V1 repos:* 252,263 `_data/<st>/bill_*.json` files at HEAD, all readable,
  133,417 distinct bills. Each file was read for its id and session and listed as
  part = 'raw _data'.

**Step 4: listing.** HEAD tree plus `git log --all --no-renames --diff-filter=AD` per repo.
**No formatted or pipeline repo, in any org, ever deleted a bill folder**, so history adds no
bills beyond HEAD. All 158 local leftovers (`govbot_data/repos/`, `old-laptop-clones/`) are clean,
and each one's HEAD is an ancestor of its govbot-archive or govbot-data repo. They hold nothing
the listed repos don't, so they are listed as covered, not listed bill by bill.

**Step 5: matching rules** (`id_rules`, `session_map`):
- All states: strip whitespace from the id (raw "HB 1" = folder "HB1").
- **co:** older OpenStates ids "HB25B-1001" / "SB25-001" equal "HB 1001" / "SB 001". I checked:
  same title and the same leg.colorado.gov source URL. The co windy-civi repo holds 2025B under
  both names.
- **usa:** compared case-insensitively. Folders differ only by case: govbot-data holds 95 bills
  twice ("HConRes14" and "HCONRES14"), which is why it showed 19,877 against raw's 19,782.
- Leading zeros: checked, and no state needed a rule.
- Copies that need a second look are flagged in `bill_copies.flag`.

**Step 6: totals.** `bill_copies` has 1,383,749 rows covering **272,462 distinct bills**:

| Source | Distinct bills |
|---|--:|
| Raw | 261,660 |
| govbot-data | 206,130 |
| Archive, July | 250,254 |
| Archive, pre-rebuild | 181,387 |
| windy-civi-pipelines | 110,441 |
| windy-civi V1 | 127,085 |

`holdings` has 96 state-session rows.

**Step 7: report.**

*The 55,529 raw bills not in govbot-data* (55,530 with PR's one; PR wasn't cloned before). **Every
one of them is in another copy, so none are lost:**
- 55,362 are in **25 sessions the 07-21 rebuild didn't carry over**. All 25 are complete in the
  July archive: ar 2025, co 2025B, ct 2025, fl 2026D, ga 2025_26, hi 2025, id 2025, ky 2025RS,
  la 2025s1, md 2025, mn 2025s1, mo 2025S2, ms 20251E, nh 2025, nj 221, nm 2025S2, ok 2025,
  or 2025S1, ri 2025, sd 2025s, tx 891, tx 89R, ut 2025S1, wv 2025, wy 2025.
- 168 are in 8 current sessions. Each one left the scrape for good while its session went on
  (OpenStates stopped returning it), and the rebuild only kept bills in the current scrape:
  - ma: 81 HD/SD docket numbers;
  - mo: 47, mostly substitutes ("SCS SB 1001", "SS SB 834");
  - fl: 19 proposed bills (SPB);
  - nh: 7; ri: 6;
  - ok: 5 "Test bill. Please disregard";
  - mn: 2 ("HF 1", "SF 1");
  - pr: 1.

  All 168 are in the July archive.

*What only windy-civi holds* (about 10,800 bills found nowhere in govbot's own generations):
- **The 2025 regular sessions of al (2025rs, 1,422), co (2025A, 733), la (2025, 1,695),
  mo (2025, 2,690), nm (2025, 1,328), sd (2025, 571) and ut (2025, 959) exist only in V1**, as
  snapshots from 2025-07-28/29. Whether those are complete is the next phase's question.
- nv 83 (2025 regular, 1,210 bills) exists only in windy-civi-pipelines.
- Small extras: nm 2025S1 (11); ia 79 prefiled XD/DP drafts; ma 82 dockets; fl 5 SPB.
- These states have **no copy anywhere** of a session that may have existed in 2025: az (57th
  1st regular), fl 2025, in 2025, ms 2025 regular, or 2025 regular, va 2025. The windy-civi repos
  for az, ca, ct, dc, in, ny, va, and V1 fl, in, nv, or, pa, va, hold no bill data. Confirming
  which sessions existed is for the next phase (outside counts).
- Raw history starts 2025-11-26, so these windy-civi copies are the only 2025 data from before
  that date.

*Surprises about where the data lives:*
- V1 repos named for one state can hold another state's data. `tx-data-pipeline` and
  `ia-data-pipeline` both hold **Idaho**. `mp-data-pipeline` also holds 858 federal bills. The
  `repos.state` column is taken from the data, not the name.
- On a case-insensitive Mac disk, git can't check out both case-variant folders. Clones of pr and
  usa warn about colliding paths. All listing here was done from git, not the working tree, so
  nothing was missed.
- `pr-legislation` is 5.7 GB on GitHub and 12 GB checked out.

**Questions for Tamara:**
1. govbot-test is empty. Was that on purpose?
2. Should the three large template repos be listed?
3. Is V1's July-2025 copy the 2025 source to judge, for the 7 states where it's the only one?

**Per-state table, all sessions found.** Every session found is a 2025 or 2026 session, apart from
nj 221 (2024-2025) and pr 2025-2028. Columns are distinct bills; "WC" = windy-civi. Reproduce it with
`select * from holdings`.

| State | Session | Bills (all sources) | Raw | govbot-data | Archive July | WC pipelines | WC V1 | Note |
|---|---|--:|--:|--:|--:|--:|--:|---|
| ak | 34 | 856 | 856 | 856 | 856 | 514 | 507 |  |
| al | 2025rs | 1,422 | 0 | 0 | 0 | 0 | 1,422 | V1 only (July 2025) |
| al | 2026rs | 1,507 | 1,507 | 1,507 | 1,507 | 91 | 0 |  |
| ar | 2025 | 1,928 | 1,928 | 0 | 1,928 | 1,928 | 1,928 | not carried over by the 07-21 rebuild |
| ar | 2026S1 | 2 | 2 | 2 | 2 | 0 | 0 |  |
| az | 57th-2nd-regular | 2,190 | 2,190 | 2,190 | 0 | 0 | 0 |  |
| ca | 20252026 | 5,041 | 5,041 | 5,041 | 4,995 | 0 | 0 |  |
| ca | 20252026 Special Session 1 | 24 | 24 | 24 | 24 | 0 | 0 |  |
| co | 2025A | 733 | 0 | 0 | 0 | 0 | 733 | V1 only (July 2025) |
| co | 2025B | 35 | 35 | 0 | 35 | 35 | 0 | not carried over by the 07-21 rebuild; id format changed (id_rules) |
| co | 2026A | 714 | 714 | 714 | 714 | 0 | 0 |  |
| ct | 2025 | 4,076 | 4,076 | 0 | 4,076 | 0 | 0 | not carried over by the 07-21 rebuild |
| ct | 2026 | 1,283 | 1,283 | 1,283 | 1,283 | 0 | 0 |  |
| dc | 26 | 1,937 | 1,937 | 1,937 | 1,752 | 0 | 699 |  |
| de | 153 | 1,296 | 1,296 | 1,296 | 1,294 | 697 | 676 |  |
| fl | 2026 | 1,921 | 1,916 | 1,897 | 1,916 | 649 | 0 | 5 SPB only in windy-civi |
| fl | 2026D | 6 | 6 | 0 | 6 | 0 | 0 | not carried over by the 07-21 rebuild |
| fl | 2026F | 5 | 5 | 5 | 5 | 0 | 0 |  |
| ga | 2025_26 | 5,480 | 5,480 | 0 | 5,480 | 2,860 | 2,860 | not carried over by the 07-21 rebuild |
| ga | 2026_ss | 176 | 176 | 176 | 176 | 0 | 0 |  |
| gu | 38th | 277 | 277 | 277 | 277 | 100 | 100 |  |
| hi | 2025 | 4,704 | 4,704 | 0 | 4,704 | 4,704 | 4,704 | not carried over by the 07-21 rebuild |
| hi | 2026 | 6,728 | 6,728 | 6,728 | 6,716 | 0 | 0 |  |
| ia | 2025-2026 | 4,363 | 4,284 | 4,284 | 3,744 | 2,446 | 0 | 79 prefiled XD/DP drafts only in windy-civi |
| id | 2025 | 790 | 790 | 0 | 790 | 790 | 790 | not carried over by the 07-21 rebuild |
| id | 2026 | 817 | 817 | 817 | 817 | 0 | 0 |  |
| il | 104th | 12,809 | 12,809 | 12,809 | 12,753 | 8,511 | 8,494 |  |
| in | 2026 | 935 | 935 | 935 | 935 | 0 | 0 |  |
| ks | 2025-2026 | 1,483 | 1,483 | 1,483 | 1,483 | 778 | 778 |  |
| ky | 2025RS | 1,441 | 1,441 | 0 | 1,441 | 1,441 | 1,441 | not carried over by the 07-21 rebuild |
| ky | 2026RS | 1,737 | 1,737 | 1,737 | 1,737 | 0 | 0 |  |
| la | 2025 | 1,695 | 0 | 0 | 0 | 0 | 1,695 | V1 only (July 2025) |
| la | 2025s1 | 12 | 12 | 0 | 12 | 10 | 0 | not carried over by the 07-21 rebuild |
| la | 2026 | 2,616 | 2,616 | 2,616 | 2,616 | 0 | 0 |  |
| ma | 194th | 11,467 | 11,368 | 11,287 | 11,167 | 8,655 | 7,897 | 82 HD/SD dockets only in windy-civi |
| md | 2025 | 2,617 | 2,617 | 0 | 2,617 | 2,617 | 2,617 | not carried over by the 07-21 rebuild |
| md | 2026 | 2,677 | 2,677 | 2,677 | 2,671 | 0 | 0 |  |
| me | 132 | 2,451 | 2,451 | 2,451 | 2,451 | 2,140 | 2,140 |  |
| mi | 2025-2026 | 4,242 | 4,242 | 4,242 | 3,848 | 2,070 | 1,464 |  |
| mn | 2025-2026 | 10,590 | 10,590 | 10,588 | 10,590 | 6,958 | 6,958 |  |
| mn | 2025s1 | 48 | 48 | 0 | 48 | 48 | 48 | not carried over by the 07-21 rebuild |
| mo | 2025 | 2,690 | 0 | 0 | 0 | 0 | 2,690 | V1 only (July 2025) |
| mo | 2025S2 | 15 | 15 | 0 | 15 | 15 | 0 | not carried over by the 07-21 rebuild |
| mo | 2026 | 3,208 | 3,208 | 3,161 | 3,206 | 0 | 0 |  |
| mp | 24 | 353 | 353 | 353 | 302 | 212 | 134 |  |
| ms | 20251E | 106 | 106 | 0 | 106 | 106 | 106 | not carried over by the 07-21 rebuild |
| ms | 2026 | 4,116 | 4,116 | 4,116 | 4,116 | 0 | 0 |  |
| ms | 20261E | 8 | 8 | 8 | 0 | 0 | 0 |  |
| mt | 2025 | 4,495 | 4,495 | 4,495 | 4,495 | 4,495 | 4,495 |  |
| nc | 2025 | 2,338 | 2,338 | 2,338 | 2,334 | 1,794 | 1,787 |  |
| nd | 69 | 1,106 | 1,106 | 1,106 | 1,101 | 1,089 | 1,089 |  |
| ne | 109 | 1,847 | 1,847 | 1,847 | 1,632 | 1,037 | 1,037 |  |
| nh | 2025 | 1,072 | 1,072 | 0 | 1,072 | 1,072 | 0 | not carried over by the 07-21 rebuild |
| nh | 2026 | 1,394 | 1,394 | 1,387 | 1,393 | 0 | 0 |  |
| nj | 221 | 11,795 | 11,795 | 0 | 11,795 | 11,446 | 11,377 | 2024-2025 session; not carried over by the 07-21 rebuild |
| nj | 222 | 11,392 | 11,392 | 11,392 | 7,661 | 0 | 0 |  |
| nm | 2025 | 1,328 | 0 | 0 | 0 | 0 | 1,328 | V1 only (July 2025) |
| nm | 2025S1 | 11 | 0 | 0 | 0 | 11 | 11 | windy-civi only |
| nm | 2025S2 | 2 | 2 | 0 | 2 | 0 | 0 | not carried over by the 07-21 rebuild |
| nm | 2026 | 812 | 812 | 812 | 812 | 0 | 0 |  |
| nv | 2025Special36 | 27 | 27 | 27 | 27 | 27 | 0 |  |
| nv | 83 | 1,210 | 0 | 0 | 0 | 1,210 | 0 | windy-civi pipeline only |
| ny | 2025-2026 | 25,503 | 25,503 | 25,503 | 25,321 | 0 | 18,918 |  |
| oh | 136 | 2,614 | 2,614 | 2,614 | 2,439 | 1,380 | 1,057 |  |
| ok | 2025 | 3,257 | 3,257 | 0 | 3,257 | 3,257 | 3,257 | not carried over by the 07-21 rebuild |
| ok | 2026 | 6,011 | 6,011 | 6,006 | 6,010 | 0 | 0 |  |
| or | 2025S1 | 3 | 3 | 0 | 3 | 3 | 0 | not carried over by the 07-21 rebuild |
| or | 2026R1 | 304 | 304 | 304 | 304 | 0 | 0 |  |
| pa | 2025-2026 | 5,266 | 5,266 | 5,266 | 4,862 | 3,449 | 0 |  |
| pr | 2025-2028 | 5,570 | 5,570 | 5,569 | 5,117 | 3,471 | 2,545 |  |
| ri | 2025 | 2,595 | 2,595 | 0 | 2,595 | 2,595 | 2,595 | not carried over by the 07-21 rebuild |
| ri | 2026 | 3,017 | 3,017 | 3,011 | 3,017 | 0 | 0 |  |
| sc | 2025-2026 | 4,046 | 4,046 | 4,046 | 3,957 | 2,244 | 2,244 |  |
| sd | 2025 | 571 | 0 | 0 | 0 | 0 | 571 | V1 only (July 2025) |
| sd | 2025s | 2 | 2 | 0 | 2 | 2 | 0 | not carried over by the 07-21 rebuild |
| sd | 2026 | 666 | 666 | 666 | 666 | 0 | 0 |  |
| tn | 114 | 9,092 | 9,092 | 9,092 | 9,092 | 4,551 | 4,550 |  |
| tn | 114S1 | 20 | 20 | 20 | 20 | 20 | 20 |  |
| tx | 891 | 592 | 592 | 0 | 592 | 0 | 0 | not carried over by the 07-21 rebuild |
| tx | 892 | 692 | 692 | 692 | 692 | 692 | 311 |  |
| tx | 89R | 11,503 | 11,503 | 0 | 11,503 | 0 | 0 | not carried over by the 07-21 rebuild |
| usa | 119 | 19,782 | 19,782 | 19,782 | 17,329 | 10,403 | 10,429 | ~95 held twice by case (id_rules) |
| ut | 2025 | 959 | 0 | 0 | 0 | 0 | 959 | V1 only (July 2025) |
| ut | 2025S1 | 18 | 18 | 0 | 18 | 18 | 0 | not carried over by the 07-21 rebuild |
| ut | 2025S2 | 5 | 5 | 5 | 5 | 0 | 0 |  |
| ut | 2026 | 1,016 | 1,016 | 1,016 | 1,016 | 0 | 0 |  |
| va | 2026S1 | 299 | 299 | 299 | 299 | 0 | 0 |  |
| vi | 36 | 148 | 148 | 148 | 148 | 148 | 130 |  |
| vt | 2025-2026 | 1,718 | 1,718 | 1,718 | 1,718 | 898 | 898 |  |
| wa | 2025-2026 | 3,411 | 3,411 | 3,411 | 3,411 | 2,075 | 2,075 |  |
| wi | 2025 | 2,749 | 2,749 | 2,749 | 2,749 | 1,414 | 1,256 |  |
| wi | 2026S1 | 2 | 2 | 2 | 2 | 0 | 0 |  |
| wv | 2025 | 2,709 | 2,709 | 0 | 2,709 | 2,709 | 2,709 | not carried over by the 07-21 rebuild |
| wv | 2026 | 2,975 | 2,975 | 2,975 | 2,975 | 0 | 0 |  |
| wy | 2025 | 556 | 556 | 0 | 556 | 556 | 556 | not carried over by the 07-21 rebuild |
| wy | 2026 | 335 | 335 | 335 | 335 | 0 | 0 |  |

### 2026-11-26 (2): Sessions missing from the live data

Tamara's answers to the questions above: (1) govbot-test never held anything, so it's skipped.
(2) The template repos aren't listed. (3) V1's copy is the 2025 source to judge for al, co, la,
mo, nm, sd and ut, marked as a late-July 2025 snapshot.

**Method** (`scripts/calendar_check.py`, writing table `calendar_sessions` and
`csv/calendar_sessions.csv`):
- *The calendar.* I used a copy of `tamara-notes/session-dates/sessions.csv` taken 11-26 (in
  `work/`), rows for 2025 and 2026 of type regular or special. Veto, reconvene and the other
  kinds are left out. Where LegiScan and MultiState list the same session, their rows are merged
  into one.
- *The OpenStates id.* Each calendar session is matched to the OpenStates session id whose
  `start_date..end_date` overlaps its dates, taken from the session list in each raw repo's
  `jurisdiction_*.json` at HEAD. When several overlap, the id containing the year wins, then
  the one with most days of overlap.
- *Fallbacks.* Each one is flagged in `match_how`:
  - Biennium ids whose OpenStates dates cover only 2025 (ak 34, ia, il 104th, ks, sc, vt) are
    taken to cover 2026 as well.
  - ms `2026`, which OpenStates dates as 2025, is matched by its id.
  - me 2026 → `132` is a manual match: 217 of 132's bills first appeared in 2026 scrapes.
  - sd 2025-09-23 special → `2025s` is a manual match. OpenStates dates `2025s` 09-03 to 09-10,
    but every action of its 2 bills (SB 1, SB 2) is dated 2025-09-23. The calendar's 09-25
    special stays unmatched (in no copy).
  - Tamara accepted all these mappings on 2026-11-26.
- *Status.* The matched id is then looked up in `holdings`.

The result: **141 calendar sessions. 88 are in govbot-data, 30 are only in other copies and 23
are in no copy.** Of the 23, 13 are sessions OpenStates doesn't list at all, all of them
specials, so no OpenStates-based copy could hold them.

**The reviewer's three, confirmed:**
- **GA 2025_26** (the 2025 and 2026 regular sessions): only in other copies. The raw history
  holds 5,480 bills from 11-27 to 06-16. The July archive holds all 5,480; windy-civi
  (pipelines and V1) holds 2,860, the 2025 part. govbot-data has only `2026_ss` (176 bills),
  because the 07-21 rebuild took the scrape of that day, which held only the special session.
- **VA 2026 regular** (01-14 to 03-14, OpenStates id `2026`): in no copy. **No VA scrape was
  committed between 2025-12-02 and 2026-07-02.** The 6 scrapes before that gap and the 3 on
  07-02 held 0 bills. The first VA bills (`2026S1`, 299) came on 07-14. VA 2025 regular and the
  Oct 2025 special are in no copy either.
- **AR 2026 fiscal session** (04-08 to 04-29; the calendar types it "regular", OpenStates id
  `2026F`, 04-08 to 05-01): in no copy. The AR scraper ran daily the whole time, but **every scrape
  from 03-05 to 07-14 held 0 bills.** AR 2025 was last seen 03-05; `2026S1` (2 bills) from
  07-14.

**Also in no copy, not raised before:**
- 2025 regular sessions: az, fl, in, ms, or, va. They ended before raw history began
  (2025-11-26), and windy-civi holds nothing for them.
- **tn `114S2`** (the May 2026 special): OpenStates lists it, but no scrape ever held it.
- fl `2025A` (the Jan 2025 special).
- 13 specials OpenStates doesn't list.

**OpenStates sessions the calendar doesn't list** (2025 and 2026; not in the tables):
- In govbot-data: fl `2026F` (5 bills) and tn `114S1` (20).
- Only in other copies: fl `2026D` (6), mn `2025s1` (48), ms `20251E` (106), nm `2025S2` (2) and
  ut `2025S1` (18).
- In no copy: fl `2025B`, `2025C` and `2026E`, mo `2025S1`, nc `2025E1`.

**In no copy: 23**

| State | Year | Type | Dates | OpenStates id | Where | Note |
|---|---|---|---|---|---|---|
| ak | 2026 | special | 2026-05-21 – 2026-06-19 | — | — | OpenStates lists no such session |
| ak | 2026 | special | 2026-06-20 – 2026-07-16 | — | — | OpenStates lists no such session |
| ak | 2026 | special | 2026-07-27 – 2026-08-25 | — | — | OpenStates lists no such session |
| al | 2026 | special | 2026-05-04 – 2026-05-08 | — | — | OpenStates lists no such session |
| ar | 2026 | regular | 2026-04-08 – 2026-04-29 | 2026F | — |  |
| az | 2025 | regular | 2025-01-13 – 2025-06-27 | 57th-1st-regular | — |  |
| ct | 2025 | special | 2025-11-12 – 2025-11-13 | — | — | OpenStates lists no such session |
| fl | 2025 | special | 2025-01-27 – 2025-01-27 | 2025A | — | also overlapped 2025B |
| fl | 2025 | regular | 2025-03-04 – 2025-06-16 | 2025 | — |  |
| ia | 2026 | special | 2026-10-02 – 2026-10-02 | — | — | OpenStates lists no such session |
| in | 2025 | regular | 2025-01-08 – 2025-04-24 | 2025 | — |  |
| md | 2025 | special | 2025-12-16 – 2025-12-16 | — | — | OpenStates lists no such session |
| md | 2026 | special | 2026-08-03 – 2026-08-05 | — | — | OpenStates lists no such session |
| ms | 2025 | regular | 2025-01-07 – 2025-04-03 | 2025 | — | also overlapped 2026 |
| nd | 2026 | special | 2026-01-21 – 2026-01-21 | — | — | OpenStates lists no such session |
| nd | 2026 | special | 2026-09-02 – 2026-09-02 | — | — | OpenStates lists no such session |
| or | 2025 | regular | 2025-01-21 – 2025-06-27 | 2025R1 | — |  |
| sc | 2026 | special | 2026-05-15 – 2026-05-15 | — | — | OpenStates lists no such session |
| sd | 2025 | special | 2025-09-25 – 2025-09-25 | — | — | OpenStates lists no such session |
| tn | 2026 | special | 2026-05-05 – 2026-05-07 | 114S2 | — |  |
| va | 2025 | regular | 2025-01-08 – 2025-02-22 | 2025 | — |  |
| va | 2025 | special | 2025-10-27 – 2025-10-31 | — | — | OpenStates lists no such session |
| va | 2026 | regular | 2026-01-14 – 2026-03-14 | 2026 | — |  |

**Only in other copies (not in govbot-data): 30**

| State | Year | Type | Dates | OpenStates id | Where | Note |
|---|---|---|---|---|---|---|
| al | 2025 | regular | 2025-02-04 – 2025-05-14 | 2025rs | windy-civi V1 1,422 (late-July 2025 snapshot) |  |
| ar | 2025 | regular | 2025-01-13 – 2025-05-05 | 2025 | raw history 1,928, July archive 1,928, windy-civi-pipelines 1,928, windy-civi V1 1,928 |  |
| co | 2025 | regular | 2025-01-08 – 2025-05-07 | 2025A | windy-civi V1 733 (late-July 2025 snapshot) |  |
| co | 2025 | special | 2025-08-21 – 2025-08-26 | 2025B | raw history 35, July archive 35, windy-civi-pipelines 35 |  |
| ct | 2025 | regular | 2025-01-08 – 2025-06-04 | 2025 | raw history 4,076, July archive 4,076 |  |
| ga | 2025 | regular | 2025-01-13 – 2025-04-04 | 2025_26 | raw history 5,480, July archive 5,480, windy-civi-pipelines 2,860, windy-civi V1 2,860 |  |
| ga | 2026 | regular | 2026-01-12 – 2026-04-02 | 2025_26 | raw history 5,480, July archive 5,480, windy-civi-pipelines 2,860, windy-civi V1 2,860 |  |
| hi | 2025 | regular | 2025-01-15 – 2025-05-02 | 2025 | raw history 4,704, July archive 4,704, windy-civi-pipelines 4,704, windy-civi V1 4,704 |  |
| id | 2025 | regular | 2025-01-06 – 2025-04-04 | 2025 | raw history 790, July archive 790, windy-civi-pipelines 790, windy-civi V1 790 |  |
| ky | 2025 | regular | 2025-01-07 – 2025-03-28 | 2025RS | raw history 1,441, July archive 1,441, windy-civi-pipelines 1,441, windy-civi V1 1,441 |  |
| la | 2025 | regular | 2025-04-14 – 2025-06-12 | 2025 | windy-civi V1 1,695 (late-July 2025 snapshot) |  |
| la | 2025 | special | 2025-10-23 – 2025-10-29 | 2025s1 | raw history 12, July archive 12, windy-civi-pipelines 10 |  |
| md | 2025 | regular | 2025-01-08 – 2025-04-08 | 2025 | raw history 2,617, July archive 2,617, windy-civi-pipelines 2,617, windy-civi V1 2,617 |  |
| mo | 2025 | regular | 2025-01-08 – 2025-05-30 | 2025 | windy-civi V1 2,690 (late-July 2025 snapshot) |  |
| mo | 2025 | special | 2025-09-03 – 2025-09-12 | 2025S2 | raw history 15, July archive 15, windy-civi-pipelines 15 | OpenStates calls it primary |
| nh | 2025 | regular | 2025-01-08 – 2025-06-26 | 2025 | raw history 1,072, July archive 1,072, windy-civi-pipelines 1,072 |  |
| nj | 2025 | regular | 2025-01-14 – 2026-01-13 | 221 | raw history 11,795, July archive 11,795, windy-civi-pipelines 11,446, windy-civi V1 11,377 | also overlapped 222 |
| nm | 2025 | regular | 2025-01-21 – 2025-03-22 | 2025 | windy-civi V1 1,328 (late-July 2025 snapshot) |  |
| nm | 2025 | special | 2025-10-01 – 2025-10-02 | 2025S1 | windy-civi-pipelines 11, windy-civi V1 11 |  |
| nv | 2025 | regular | 2025-02-03 – 2025-06-02 | 83 | windy-civi-pipelines 1,210 |  |
| ok | 2025 | regular | 2025-02-03 – 2025-05-30 | 2025 | raw history 3,257, July archive 3,257, windy-civi-pipelines 3,257, windy-civi V1 3,257 |  |
| or | 2025 | special | 2025-08-29 – 2025-10-01 | 2025S1 | raw history 3, July archive 3, windy-civi-pipelines 3 |  |
| ri | 2025 | regular | 2025-01-07 – 2025-06-20 | 2025 | raw history 2,595, July archive 2,595, windy-civi-pipelines 2,595, windy-civi V1 2,595 |  |
| sd | 2025 | regular | 2025-01-14 – 2025-03-31 | 2025 | windy-civi V1 571 (late-July 2025 snapshot) |  |
| sd | 2025 | special | 2025-09-23 – 2025-09-23 | 2025s | raw history 2, July archive 2, windy-civi-pipelines 2 | manual: all actions dated 09-23 |
| tx | 2025 | regular | 2025-01-14 – 2025-06-02 | 89R | raw history 11,503, July archive 11,503 |  |
| tx | 2025 | special | 2025-07-21 – 2025-08-15 | 891 | raw history 592, July archive 592, pre-rebuild archive 592 |  |
| ut | 2025 | regular | 2025-01-21 – 2025-03-07 | 2025 | windy-civi V1 959 (late-July 2025 snapshot) |  |
| wv | 2025 | regular | 2025-01-08 – 2025-04-12 | 2025 | raw history 2,709, July archive 2,709, windy-civi-pipelines 2,709, windy-civi V1 2,709 |  |
| wy | 2025 | regular | 2025-01-14 – 2025-03-06 | 2025 | raw history 556, July archive 556, windy-civi-pipelines 556, windy-civi V1 556 |  |

**In govbot-data: 88** (state: year type id, flags in brackets)

- **ak:** 2025 reg. `34`; 2026 reg. `34` [biennium id; OpenStates dates cover 2025 only]
- **al:** 2026 reg. `2026rs`
- **ar:** 2026 spe. `2026S1`
- **az:** 2026 reg. `57th-2nd-regular`
- **ca:** 2025 reg. `20252026`; 2026 reg. `20252026`
- **co:** 2026 reg. `2026A`
- **ct:** 2026 reg. `2026`
- **dc:** 2025 reg. `26`; 2026 reg. `26`
- **de:** 2025 reg. `153`; 2025 spe. `153` [no separate OpenStates id; assumed inside it]; 2025 spe. `153` [no separate OpenStates id; assumed inside it]; 2025 spe. `153` [no separate OpenStates id; assumed inside it]; 2026 reg. `153`
- **fl:** 2026 reg. `2026`
- **ga:** 2026 spe. `2026_ss`
- **gu:** 2026 reg. `38th`
- **hi:** 2026 reg. `2026`
- **ia:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026` [biennium id; OpenStates dates cover 2025 only]
- **id:** 2026 reg. `2026`
- **il:** 2025 reg. `104th`; 2026 reg. `104th` [biennium id; OpenStates dates cover 2025 only]
- **in:** 2026 reg. `2026`
- **ks:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026` [biennium id; OpenStates dates cover 2025 only]
- **ky:** 2026 reg. `2026RS`
- **la:** 2026 reg. `2026`
- **ma:** 2025 reg. `194th`; 2026 reg. `194th`
- **md:** 2026 reg. `2026`
- **me:** 2025 reg. `132`; 2025 spe. `132` [no separate OpenStates id; assumed inside it]; 2026 reg. `132` [manual: 217 bills of 132 first seen in 2026]
- **mi:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026`
- **mn:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026`
- **mo:** 2026 reg. `2026`
- **mp:** 2026 reg. `24`
- **ms:** 2026 reg. `2026` [matched by id; OpenStates dates say 2025]; 2026 spe. `20261E` [OpenStates calls it primary]
- **mt:** 2025 reg. `2025`
- **nc:** 2025 reg. `2025`; 2026 reg. `2025`
- **nd:** 2025 reg. `69`
- **ne:** 2025 reg. `109`; 2026 reg. `109`
- **nh:** 2026 reg. `2026`
- **nj:** 2026 reg. `222`
- **nm:** 2026 reg. `2026`
- **nv:** 2025 spe. `2025Special36`
- **ny:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026`
- **oh:** 2025 reg. `136`; 2026 reg. `136`
- **ok:** 2026 reg. `2026`
- **or:** 2026 reg. `2026R1`
- **pa:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026`
- **pr:** 2025 reg. `2025-2028`; 2025 reg. `2025-2028`; 2026 reg. `2025-2028`; 2026 reg. `2025-2028`
- **ri:** 2026 reg. `2026`
- **sc:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026` [biennium id; OpenStates dates cover 2025 only]
- **sd:** 2026 reg. `2026`
- **tn:** 2025 reg. `114`; 2026 reg. `114`
- **tx:** 2025 spe. `892`
- **usa:** 2025 reg. `119`; 2026 reg. `119`
- **ut:** 2025 spe. `2025S2`; 2026 reg. `2026`
- **va:** 2026 spe. `2026S1`
- **vi:** 2026 reg. `36`
- **vt:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026` [biennium id; OpenStates dates cover 2025 only]
- **wa:** 2025 reg. `2025-2026`; 2026 reg. `2025-2026`
- **wi:** 2025 reg. `2025`; 2026 reg. `2025`; 2026 spe. `2026S1`
- **wv:** 2026 reg. `2026`
- **wy:** 2026 reg. `2026`

**Stopped here (2026-11-26).** The next phase waits for Tamara's decisions. Nothing below has
been started:
- outside counts, which need her OpenStates API key;
- restoring the sessions held only in other copies, GA `2025_26` first;
- a list of past sessions to re-scrape: VA `2026`, AR `2026F`, TN `114S2`.
