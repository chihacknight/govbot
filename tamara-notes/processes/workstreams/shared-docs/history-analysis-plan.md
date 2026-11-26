# State history analysis: plan

A plan for replaying every state's full raw scrape history (on the SSD) to find out **what silently
went wrong, when, how badly, and whether it came back**, and **what structured information each
state gives us about its bills**. Written section by section with Tamara and approved by her on
2026-11-25. Execution goes to fresh chats, with this doc as their brief.

Started 2026-11-25, branch `history-analysis-plan`, `/Users/tamara/my_work/govbot-bill-skip`.

> **What this work is: finding the patterns, so we can build the audit next.**
>
> - **This step:** look back over the year of raw scrapes and learn:
>   - how each state's data normally behaves;
>   - how it behaved when it was broken;
>   - which signals would have warned us.
> - **The next step, built from this:** the state auditor, a scheduled early-warning system that
>   lists the states that may not be working.
> - **Not this step:**
>   - building or scheduling the auditor;
>   - fixing scrapers;
>   - restoring data.
>
>   Findings that point to those (a bug to report, data to recover) are written down and handed
>   on, not acted on here.

## 0. Why

For much of the past year, scrapers reported green while bills, fields and votes went missing.
Examples:

- 16 states and USA froze for 7 months from 2025-12-14.
- IL lost its synopsis on 07-13 and KY its sponsors on 08-20.
- ND saved error pages as voters.

Nobody knew until someone looked by hand. The SSD now holds every raw scrape for all 56
jurisdictions, so for the first time we can check the whole year systematically.

**The main purpose (Tamara, 2026-11-25): an early-warning system for next year.** A state
auditor, a new system run on a schedule, that produces a list of the states that may not be
working, so a silent failure in the 2027 sessions is caught in days, not months. This analysis is
how we build and test that system:

- what to check;
- what "normal" is for each state;
- whether each check would have caught this year's real failures without false alarms on
  healthy stretches.

**Normal is different in each state, so checks are per state.** For example, some states file
all their bills on the first day of session, so "the bill count stopped growing" is normal for
them and a failure elsewhere. The existing weekly audit already hard-codes GU, OR and NV as
exceptions for this reason. That's not most states, but the system must allow it. So the
analysis works out each state's **profile**:

- its filing pattern;
- its usual nightly activity;
- its quiet periods, in and out of session;
- which fields it normally fills.

The auditor then compares each state with its own profile. Separate rules for separate states
are expected where the data shows they're needed. What the data means stays the same everywhere;
only the checks differ.

The analysis also feeds two other things:

1. **The state auditor's design:** above.
2. **The next major project: as much information about each bill as possible, non-PDF first.**
   That needs an inventory of the structured fields each state provides, used to provide, or lost.
   IL's synopsis is the first example.
3. **Recoveries.** Data that's still in the raw history can be restored, for example IL's 8,648
   synopses (already wanted).

**A later source, not used in this run:** the old `windy-civi-pipelines` orgs hold formatted data
from before our raw history begins (2025-11-27). Example: `windy-civi-pipelines/ar-data-pipeline`
has AR's `sessions/2025/bills`, and the 2025 session ran January–May 2025. Once this analysis
shows what's missing, compare against those repos to see what they can fill in (earlier versions,
earlier dates, bills our raw history never saw), before they're cleaned up.

They're also the fallback when **a state's history here is too thin to build its profile**: for
example, a state whose data starts late, has long empty stretches (AR, 03-13 to 07-12), or never
had a full session in our history. Then those repos can supply another year of that state's
rhythm. Expect a lot of overlap with the newer repos. Use them per state, as needed, not as a
bulk import. A state's profile records which source it was built from.

**TX will likely need them first:** its raw history here has only 41 scrapes in the year (most
states have about 300), 15 MB in all. Tamara's TX repos (2026-11-25). The formatting differs from
the current layout:

- https://github.com/windy-civi-pipelines/tx-data-pipeline
- https://github.com/windy-civi-pipelines-V1-archived/tx-data-pipeline-old
- https://github.com/windy-civi-pipelines-V1-archived/tx-data-pipeline_old
- https://github.com/windy-civi-pipelines-V1-archived/tx-data-pipeline

Cloned read-only to `/Volumes/govbot-data/windy-civi/` (2026-11-25). What they hold:

| Repo | Contents |
|---|---|
| `windy-civi-pipelines/tx-data-pipeline` | TX session 892 (2nd special, 2025): 692 bills, 2025-10-23 to 11-11. The same 692 as today's data repo. |
| `V1-archived/tx-data-pipeline-old` | Session 892: 311 bills, an earlier partial copy (2025-10-21 to 10-23). |
| `V1-archived/tx-data-pipeline_old` | Nearly empty (4 files). |
| `V1-archived/tx-data-pipeline` | **Idaho, not Texas:** ID's 2025 regular session, 790 bills (2025-07-28/29). Misnamed. |

So for TX they mostly repeat what we have (some earlier October dates for the 892 bills). They
don't hold the 89R regular session. Those 11,503 bills are in our own raw history's early scrapes.
TX's thin history (41 scrapes) stays thin, and its profile may need the 2027 session to fill in.
The misnamed repo holds **ID data from before our raw history began**, which may help with ID's
possible undercount. Tamara thinks it was a wrong state code when the repo was made, and probably
the only one.

**FL:** `windy-civi-pipelines/fl-data-pipeline`, also cloned. It has the 2026 session, 649 bills
in the old layout (2,189 action files, 25 vote files), scraped **2025-10-23 to 11-26**. Our raw FL
history starts on **11-27**, the next day, so this covers the pre-filing month right before ours:
earlier first-seen dates for the first 2026 bills, and possibly votes or actions from before the
bot blocking got bad. It doesn't fill FL's real gap (House committee votes lost during 2026). Our
data repo has 1,897 bills for 2026.

**Not in scope:**

- unpausing the scrapers (no pressure);
- fixing scrapers;
- PDF and full-text extraction;
- the old `windy-civi-pipelines` orgs (a later cleanup).

## 1. Which states first

All 56 states get tested eventually. The first run uses a targeted set, chosen so each check can
be **calibrated** on states believed good and **validated** on problems we already know about,
dates included. A check that doesn't flag IL's synopsis or KY's sponsors is broken.

The problem states have changed over time. In July they were the states that couldn't run (IP
blocks, crashes, timeouts). By November, nearly all of those are fixed or worked around. What's
left are **data problems in states that look healthy**, which the master list
(`docs/src/state-status-reference.md`, 2026-11-24) mostly marks ✅. So the old notes are treated as
**claims to check, not facts**. A helper's read of all of `tamara-notes/` found 21 places where
they contradict each other. Summary:
`/Volumes/govbot-data/scratch/claude-review/notes-by-state.md`.

### First wave: 15 states

| Group | State | Why |
|---|---|---|
| **Baseline: believed good** | CA | Tamara: a clean database dump, "super easy". Note: it rewords old actions a lot (5,088), which is harmless but worth knowing. |
| | DE | Small. Nothing in the notes beyond one vote that flip-flopped and was corrected. A second baseline of a different size. |
| **Known data losses, with dates** | IL | Synopsis (`abstracts`) gone from all 8,648 bills since 07-13. Two committed scrapes with 0 bills (07-03, 07-13). Frozen Dec 2025 to July. Lost 18,970 files to an overwrite on 07-21. |
| | KY | Sponsors gone from 1,707 bills since 08-20. Whitespace inside actions and abstracts. |
| | ND | Error pages saved as voters on 8 nights, up to ~1,170 votes each. |
| | TN | 6,787 roll calls emptied (worst 07-02). 7,181 votes dropped by the old date gate. Only 37 of ~5,400 bills before July's IP-block fix. |
| | NH | Sponsors lost twice (12-25, 12-30), versions once (08-21), all came back. A rate-limited run wiped 436 files. Blocks scraping 6am–9pm ET. |
| **Hard or adversarial sources** | FL | `flhouse.gov` bot detection: House committee votes lost on 78% of bills (08-07). A later run can delete a vote captured earlier (HB 755). Tamara: "they lie to us to prevent scraping". |
| | MA | A "Server Error" warning silently dropped about 210 bills per run, 07-01 to 08-07. Worst duplicate bloat (4.5×). 3 bills dropped on 07-27, never identified. |
| | TX | Blocks GitHub's IP addresses (self-hosted only). Conflict markers on 06-26. A whole session (89R, 11,503 bills) is in the raw data but not in the data repo. Tamara: "a pia". |
| **Missing sessions, undercounts, near-zero data** | GA | Every bill file corrupted by conflict markers for 5 days (07-21). The 5,480-bill regular session is missing from the data repo. The old bill skip lost real updates. |
| | WY | Undercount confirmed in July: the API leaves out signed bills, and three budget bills are missing. Not re-checked since. |
| | AR | Almost no data, and nobody knew for a long time (Tamara). In the raw history: 1,928 bills (session `2025`) until 2026-03-12, then **0 bill files in 119 committed scrapes** from 03-13 to 07-12, so the 2026 Fiscal Session (April 8–29) was never captured. Then 2 bills (`2026S1`). The data repo (created 07-21) has only those 2 bills; the 1,928 from 2025 aren't in it. Also a duplicate pile-up in Nov 2025 (1,928 → 13,496 files, then cleaned). |
| **The Dec 2025 freeze** | NC | Frozen from 12-14 for 7 months while green, then fixed in July (it never had `runner: self-hosted`). Stands in for the freeze group. |

### Second wave (after the method works on the first)

- NJ: a session missing from the data repo (11,795 bills).
- CT: a session missing (4,076 bills); 0 bills for the 2026 session.

- NV: ~1,000 bills from 2025 never backfilled.
- MT: the 6,900 vs 4,495 unique-bill dispute; 13,683 reworded actions.
- PA: IP block, each vote written ~5×, 853 count corrections, 5 bills dropped on 10-29.
- UT, ID, MD: possible undercounts, likely stale claims. UT also had 6 days of byte-identical
  output.
- IN: HB 1001–1010 and Senate bills possibly missing.
- HI, AZ: 0 bills for the whole 2026 session.
- OR: sponsors on only 56% of bills.
- GU: 0 actions and 0 documents on every bill.
- KS, MO, DC: mass rewording.
- VA: one roll-call number reused across votes.

### Third wave: everyone else

The ~25 states with no known problems. "No known problems" means nobody has looked closely, not
that they're clean.

## 2. Questions to answer

What the analysis must answer for each state, over its whole raw history. Each question names a
known example (so we can tell the answer is right) and who uses the answer: **A** = the state
auditor, **B** = the bill-information project, **R** = recoveries.

### Bills: are they all there?

1. **Did the number of bills ever drop, go to zero, or stop changing?** When, for how long, and did
   it come back? Examples:
   - AR: 0 bill files in 119 committed scrapes (03-13 to 07-12).
   - IL: two committed 0-bill scrapes.
   - MA: about 210 bills dropped per run (07-01 to 08-07).
   - PA: 5 bills dropped on 10-29.

   (A, R)
2. **Are whole sessions in the raw history missing from the data repo?** Examples: GA 5,480 bills,
   TX 11,503, NJ 11,795, CT 4,076, AR 1,928. Also why: by design (one session per repo, older
   sessions archived elsewhere) or lost? (R, A)
3. **Did individual bills disappear and never come back?** Bills present in some scrapes and
   absent from every later one, while the session continued. (A, R)
4. **Does the state have fewer bills than the legislature?** This needs an outside count, so it's
   limited to the totals we already have in the notes (WY's budget bills; UT, MD, ID, IN claims).
   A full outside comparison is out of scope until there's a source (LegiScan key pending). (A)

### Bill content: what does each state give us, and did it change?

5. **Field inventory: which fields does each state fill, and on what share of bills?** Covers
   `abstracts`, `subject`, `sponsorships`, `other_titles`, `related_bills`, `versions` and
   `documents`, including their **media types** (HTML/XML vs PDF only), `actions`, `extras`, and
   anything state-specific. This is the starting inventory for "as much information as possible,
   non-PDF first". (B)
6. **Which fields went empty on many bills at once, and did they come back?** Examples:
   - IL `abstracts` since 07-13;
   - KY `sponsorships` since 08-20;
   - NH sponsors (twice), then versions.

   (A, R)
7. **Which fields changed shape?** That covers reworded actions (MT 13,683, KS, DC, MO, CA),
   renamed people (IL "Dan Ugaste" → "Daniel J. Ugaste" on 716 bills), and whitespace added (KY).
   (A, B)

### Actions and votes

8. **Did actions or votes disappear from a bill after being seen?** Example: FL HB 755's House
   committee vote, gone on 08-07. (A, R)
9. **Are roll calls broken?** Empty roll calls (TN), error pages as voters (ND), page text as voters
   (OK, TN, MI), or vote counts that don't match the voter list. (A)

### Freshness

10. **When did a state stop getting new information while scrapes kept being committed?** This is
    the Dec 2025 freeze (16 states and USA, from 12-14; NC in the first wave), and UT's 6 days of
    byte-identical output. Measured by both "scrape identical to the last" and "no new action or vote
    for N days". (A)
11. **Did a state go quiet during its legislative session, when activity is expected?** This uses
    the session calendar (`tamara-notes/session-dates/`). (A)

### Damage in the raw files

12. **Which scrapes have files that can't be read?** Conflict markers (GA 07-21, TX 06-26, LA
    06-30), invalid JSON, empty files. Which bills, and does the log have a gap there? (A, R)
13. **How bad is duplicate bloat?** Files per bill per scrape. Examples: MA 4.5×, PA 53,685 files
    for 5,264 bills, AR's Nov 2025 pile-up. It doesn't harm published data, but it shows runs that
    never cleaned up. (A)

### Checking the notes, and setting the auditor's limits

14. **Which of the 25 claims in the notes hold up?** For example: WY's budget bills, NV's ~1,000
    unbackfilled bills, IN HB 1001–1010, MT 6,900 vs 4,495. True, false or can't tell, with the
    evidence. (A)
15. **What is each state's normal: its profile?** Over its healthy stretches (and for the
    baseline states CA and DE):
    - its **filing pattern**: front-loaded (all bills on day one, like GU, OR, NV) or steady;
    - its usual nightly new bills, actions and votes, in session and out;
    - how long it normally goes quiet;
    - which fields it fills, and on what share of bills.

    The auditor checks each state against its own profile, so this sets the per-state thresholds,
    the way option C's 50% rule was measured. (A)
16. **Would each check have worked this year?** Replay the year through each proposed check, state
    by state:
    - Did it flag the known failures, and how many days after they started?
    - Did it raise false alarms on healthy stretches?

    A check isn't ready until it passes this on the first-wave states. (A)

### Not asked here

- Whether each state's data matches the legislature's website value by value (the IL field audit
  did this by hand for one state). That's a later, per-state job.
- Bill text quality, or anything from PDFs.

## 3. What gets measured

**A scrape** is one commit in a raw scraper repo
(`/Volumes/govbot-data/raw-scrapers/<st>-legislation`) that touches `_data/<st>/`, dated by its
commit time. That's the same time the logs use as `first_seen`. One pass reads each state's
scrapes oldest to newest. Raw file names are random for each scrape, so each file is identified by
its content (git blob). A blob already read is never parsed again, as `backfill_logs.py` and
`field_loss.py` do. That keeps a full history affordable.

The pass saves **three tables per state**. The profiles (Q15) and the check replays (Q16) are
computed from these tables later, so a new question means a new query, not a new pass over the
history.

### Table 1: one row per scrape (the time series)

| Measurement | Answers |
|---|---|
| Files: total, bill, vote, event, other | Q1, Q13 |
| Distinct bills (session + identifier), total and per session | Q1, Q2 |
| Duplicates: bill files ÷ distinct bills | Q13 |
| Unreadable files: conflict markers (`<<<<<<<`), invalid JSON, empty; which bills where known | Q12 |
| Identical to the previous scrape (same set of blobs) | Q10 |
| Bills new, gone (in the last scrape, not this one) and changed (new blob) | Q1, Q3 |
| Actions new, and actions gone from a bill that's still present | Q8, Q10 |
| Votes new, changed and gone; empty roll calls; voters that are error text or page text; counts that don't match the voter list | Q8, Q9 |
| Per field, for each field in Q5: bills that have it, that lost it and that gained it since the last scrape | Q6 |
| Per field: bills where it changed shape (reworded actions, renamed people, whitespace-only changes) | Q7 |
| Version and document links by media type (HTML, XML, PDF, Word, other, none) | Q5 |

Gaps between scrapes come from the commit times. Whether the night was in session comes from joining
the session calendar later, not from this pass.

### Table 2: one row per bill (its life story)

For each (session, identifier):
- first and last scrape it appeared in;
- how many times it went missing and came back, and for how long;
- how many times its content changed;
- the last scrape where each field was filled.

This answers Q3 (bills that vanished for good) and part of Q8. It's also where recoveries start:
"IL SB2310's last scrape with a synopsis".

### Table 3: one row per session

Sessions seen in the raw history, with their first and last scrape and their bill count, next to
the same session's bill count in the data repo (`govbot_data/full/<st>-legislation`). Zero means
missing (Q2: GA, TX, NJ, CT, AR). Reading the data repo is the only time the pass looks outside the
raw history.

### The field inventory (Q5), also kept per state

- **Coverage:** every top-level bill field, and the main nested ones (`sponsorships[].person_id`
  and `.classification`, `versions[].links[].media_type`, `abstracts[].note`,
  `actions[].classification`), each with the share of bills that fill it in the latest scrape and
  at its best.
- **Unusual fields:** `extras` keys and anything outside the usual OpenStates bill shape, listed with
  examples, since that's where state-specific information hides.

### Not measured in this pass

- Comparisons with the legislature's own website or counts (Q4 uses only the numbers already in the
  notes).
- Bill text or PDF contents.
- Events (`event_*.json`, only USA has them), which are counted but not analyzed.

### Checks against what we already know

Before anything is trusted, the pass must reproduce numbers we already have:

- AR's 119 empty scrapes;
- IL's 8,648 lost synopses and 0-bill commits;
- KY's 1,707 lost sponsors;
- the TN empty roll calls and ND error-page voters (they need the same night counts as `tn.md` and
  `nd.md`);
- the `field_loss.py` rows for the 8 states it covered.

A mismatch means the pass is wrong, not the notes.

## 4. How to run it

### Timing (measured 2026-11-25)

A full pass of `field_loss.py` over **IL's whole raw history** took **3 min 44 s** and **1.5 GB**
of memory. That's 455 scrapes and 2.0 GB of git history; every scrape was listed and every
distinct bill file read once. That pass is close to section 3's, which measures more, so allow
**2–3×: about 10 minutes for IL**.

First-wave history sizes:

| State | Scrapes | Git history |
|---|---|---|
| CA | 302 | 2.8 GB (largest) |
| IL | 455 | 2.0 GB |
| TN | 215 | 0.9 GB |
| MA | 439 | 0.75 GB |
| GA | 280 | 0.46 GB |
| ND, NC | 288, 295 | about 0.35 GB each |
| DE | 291 | 0.22 GB |
| KY, AR, NH, FL, WY | 148–351 | 50–140 MB |
| TX | 41 | 15 MB |

**Estimate:** the first wave is about an hour; all 56 states are an evening. So every scrape is
read: no sampling, and no cleverness beyond reading each blob once.

New findings from the sizes alone:

- **TX has only 41 scrapes in the year.** It's the first candidate for the windy-civi fallback.
- **FL's history is small for a big state** (85 MB), which fits a scraper losing data.

### Where things live

- **Code in the repo,** because the scanner becomes the engine of the scheduled auditor. It goes in
  a new folder next to the existing audits, `actions/openstates-scrape-audits/history/`. It needs
  offline tests (a tiny git repo built in the test) and the "checks against what we already know"
  from section 3 as its acceptance test. Standard library only, plus `git`, as the format action
  does.
- **Data on the SSD only:** `/Volumes/govbot-data/scratch/history-analysis/` (per-state tables,
  logs, reports). The raw repos and `govbot_data/full/` are **read-only**: no checkout, no fetch, no
  writes. Git is read with `git cat-file --batch`, as `backfill_logs.py` does.

### Order

1. **Build and prove it on three small states with known answers:** WY, KY and AR. They take
   minutes each and have AR's 119 empty scrapes, KY's 1,707 lost sponsors and WY's missing budget
   bills. Fix the scanner until it reproduces them.
2. **The rest of the first wave,** four states at a time (memory about 1.5 GB each, well within
   the laptop), biggest last.
3. **Review (Tamara + the reviewing chat):** a findings doc for the first wave (section 5) and the
   first state profiles. Change the measurements here if something's missing, then re-run. That's
   cheap.
4. **Second wave, then everyone else,** the same way.
5. **The windy-civi fallback,** per state, only where step 3 or 4 shows a profile is too thin (TX
   first). It needs its own small reader, since the format differs.

### Later: on a schedule

The same scanner runs incrementally for the auditor:

- it reads only the scrapes since its last run, with a cursor kept outside the repos, like the
  backfill's;
- it appends to the same tables;
- it checks each state against its profile.

How and where it runs on a schedule (GitHub Actions, or the self-hosted runner next to the SSD) is
decided when the checks exist, in the auditor design, not now.

### Who does what

- **A fresh chat builds and runs the scanner,** with this doc as its brief.
- **The reviewing chat checks** each step's results against the known numbers and writes the
  findings up with Tamara.
- **Nothing is committed or pushed without Tamara's OK.**

## 5. Output: what gets saved, and the findings doc

### The tables (machine-readable, on the SSD)

**One SQLite database for all states:** `/Volumes/govbot-data/scratch/history-analysis/history.sqlite`.

- Tamara uses **DBeaver**, which opens SQLite directly.
- Python's built-in `sqlite3` writes it, so the scanner stays standard-library only.
- Every table has a `state` column, so profiles and check replays can query across states and
  the whole year in SQL.
- DBeaver exports any table or query to CSV or Excel when a file is needed.

| Table | What |
|---|---|
| `scrapes` | Table 1, one row per state and scrape |
| `bills` | Table 2, one row per state and bill |
| `sessions` | Table 3, one row per state and session (raw vs data repo) |
| `fields` | The field inventory: state, field, coverage, examples of unusual fields |
| `runs` | Lineage per state: the scanner's git commit, the raw repo's HEAD, the data repo's HEAD, when it ran, how long it took, the cursor (last scrape read) |

Also, per state, `/Volumes/govbot-data/scratch/history-analysis/<st>/report.md`: a generated
one-page summary with counts, simple text charts, and every flagged event with its evidence.

- **Re-running gives the same contents.** Re-scanning a state replaces its rows, in one
  transaction. The database file's bytes can differ, so the check is on contents.
- **The schema is written down in the scanner's code** (one `CREATE TABLE` per table with a
  comment per column), so DBeaver users can read what each column means.
- **Nothing here goes into a repo.** It's derived data, rebuilt from the raw history whenever
  needed, and large for big states.

### The state profiles (machine-readable, later)

`/Volumes/govbot-data/scratch/history-analysis/profiles/<st>.json`, computed from the tables once the first wave is reviewed:

- the filing pattern;
- the normal ranges of each measurement, in session and out;
- the usual quiet stretches;
- the fields it fills;
- which source it was built from (raw history, or a windy-civi repo).

These become the auditor's per-state settings. Small and readable, so they **can** be committed
later, as part of the auditor.

### The findings doc (human-written, in the repo)

`tamara-notes/processes/workstreams/shared-docs/history-analysis-findings.md`, written by the
reviewing chat with Tamara from the generated reports:

- **a summary table:** each state's data health over the year, at a glance;
- **per state:** each finding (section 6) with dates, size, evidence and status, and the notes'
  claims checked (Q14: true, false, can't tell);
- **the field inventory** across states: the starting point of the bill-information project;
- **recoveries proposed,** for Tamara to decide;
- **what the auditor should check** (section 6).

Then the durable parts move into `tamara-notes/state-specific/<st>.md` for each state with a real
finding, and into the master list (`docs/src/state-status-reference.md`), which today only tracks
whether a scraper runs, not whether its data is good. Adding a data-health column there is a
suggestion for Tamara to decide.

## 6. What counts as a finding, and what happens next

### A finding is an event with a start, an end, a size and evidence

| Kind | Example |
|---|---|
| **Outage:** scrapes committed, but empty or frozen | AR 0 bills, 03-13 to 07-12; the Dec 2025 freeze |
| **Loss:** bills, fields, actions or votes that were there and then weren't | IL synopses; KY sponsors; FL HB 755's vote; MA's ~210 bills |
| **Gap:** something in the raw history that never reached the data repo | GA's, TX's, NJ's, CT's and AR's missing sessions |
| **Corruption:** unreadable files, or garbage saved as data | GA conflict markers; ND error pages as voters; TN empty roll calls |
| **Change:** data reshaped in bulk | MT's 13,683 rewordings; IL's renamed legislator |
| **Thin:** too little history to know what normal is | TX's 41 scrapes |

Each finding records:

- the state;
- the kind;
- the first and last scrape affected (or "still ongoing");
- how many bills, fields or votes;
- whether it came back by itself;
- **evidence:** the scrape commits, plus two or three example bills a person can open and check.

A finding without evidence isn't one.

### How a finding is judged

- **Against the state's own normal (its profile), not one rule for all states.** "Bill count
  stopped growing" is a finding only where that isn't the state's pattern.
- **Known findings come first,** and must be reproduced (section 3). Then each is marked:
  - **confirmed:** matches the notes;
  - **corrected:** the notes had it wrong;
  - **new:** not in any note;
  - **false alarm:** a check fired on normal behavior. That's a lesson for the auditor, not a
    finding.

### What happens with each finding

| Finding | Next step | Who decides |
|---|---|---|
| Data still in the raw history (IL synopses, AR's 2025 bills, the missing sessions) | Added to the **recovery list** with what it would take | Tamara, per item |
| A scraper bug still happening | A state file entry, then an **OpenStates report** drafted | Tamara files it |
| A pattern a check could catch | A **candidate auditor check**: what it measures, its per-state threshold, and its replay (Q16) result | Reviewed together |
| A claim in the notes that's wrong | Corrected in the state file or master list | Reviewing chat, with Tamara's OK |

### When the analysis is done

- **The first wave is done when:**
  - every known number is reproduced;
  - each of the 15 states has a reviewed set of findings and a profile;
  - the candidate checks have been replayed over the year, with how many days each took to catch
    each known failure and how many false alarms it raised.
- **Then the auditor design doc** is written from that, separately: which checks, per-state
  settings, how it's scheduled, and where the list of possibly-broken states gets posted.
- **The second and third waves** then run the same scanner and judge it the same way, and refine
  the profiles and checks.
