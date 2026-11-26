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

**Found 2026-11-25: the `govbot-archive` org holds the formatted repos from before the
2026-07-21 rebuild.** Today's `govbot-data` repos were created on 07-21 with only each state's
current session, so the sessions "missing from the data repo" (Q2) are there, not lost. Checked:

- AR `2025`: 1,928 bills;
- GA `2025_26`: 5,480;
- TX `89R`: 11,503 and `891`: 592.

There are 112 repos (~11.5 GB): 56 `<st>-legislation` frozen in mid-July (`chn-openstates-files`
redirects there, and `govbot_data/repos/` on the SSD holds clones of most of them) and 56 archived
`<st>-legislation-pre-rebuild-2026-07-21` snapshots. **The older sessions are only in the July
`<st>-legislation` copies.** The `-pre-rebuild-2026-07-21` snapshots, despite the name, hold only
the current session, like today's data repos: they have 0 bills for AR `2025`, KY `2025RS` and
WY `2025` (section 7, finding 6). For Q2, the session table (Table 3) compares the raw history
with **both** today's data repo and both archive copies. A session in neither is a real
gap. Bringing archived sessions back into the data repos is a later decision.

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
   TX 11,503, NJ 11,795, CT 4,076, AR 1,928. **Partly answered:** the 07-21 rebuild kept only
   current sessions, and AR's, GA's and TX's older sessions are in `govbot-archive` (section 0).
   Still to check for all 56: is every older session in the archive, or are some in neither?
   (R, A)
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
the same session's bill count in the data repo (`govbot_data/full/<st>-legislation`) and in the
`govbot-archive` copies (both the July `<st>-legislation` and the `-pre-rebuild-2026-07-21`
snapshot). Zero in all of them means really missing (Q2). Reading those repos is the only time
the pass looks outside the raw history.

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

## 7. Progress

### 2026-11-25: scanner built and proven on WY, KY, AR (stopped for review)

Branch `history-scanner`, off `origin/main` at `da250c01`. **Nothing is committed yet.**

**Code** (`actions/openstates-scrape-audits/history/`, standard library plus git):

| File | What it does |
|---|---|
| `scan.py` | The scanner, with the schema (one commented `CREATE TABLE` per table) |
| `report.py` | Writes `<st>/report.md` from the database |
| `check_known.py` | Acceptance test against the real history |
| `test_scan.py` | 18 offline tests, using tiny git repos built in the test |
| `README.md` | Usage |

**Data:** `/Volumes/govbot-data/scratch/history-analysis/`:

- `history.sqlite` (16 MB for the three states);
- `wy/`, `ky/`, `ar/report.md`;
- `checks/field_loss_<st>.tsv`: `field_loss.py` re-run on the three states, for the comparison.

**Cost:**

| State | Time | Memory |
|---|---|---|
| WY | 40 s | 186 MB |
| AR | 72 s | not measured |
| KY | 83 s | not measured |

All 112 archive clones were complete when used.

#### Decisions made while building (for the reviewer to check)

1. **A blob is never reused between scrapes.** Every bill file has a new `scraped_at` and `_id`
   each night, so the plan's "a blob already read is never parsed again" saves nothing. Instead:
   - files are compared by a hash of their content with `scraped_at`, `_id` and a vote's `bill`
     pointer left out;
   - every file is parsed in every scrape. That's affordable at the speeds above.
2. **Times are stored in UTC.** The self-hosted runner commits in `-05:00`, which would break
   date order in SQL.
3. **Two tables beyond section 5's five:**
   - `scrape_fields`: Table 1's per-field part, one row per scrape and field;
   - `bad_files`: which unreadable file, and which bill when it can be found.
4. **What each change is compared against:**
   - Bills new, gone and returned: the scrape just before.
   - Field and action changes: the bill's last-seen version (the same rule as `field_loss.py`).
   - So an empty scrape counts every bill gone, and the next full one counts them all returned.
5. **An unreadable bill file is not "gone".** The bill is found by a text search in the file,
   and compared again at the next scrape.
6. **Duplicates:** when a bill has several files in one scrape, the richest version (most
   actions, then most fields) counts.
7. **Vote count mismatch compares yes, no and the total only.** KY's counts say "other" where
   its voter list says "not voting".
8. **The report's flagging rules are fixed and simple, for a person to review.** They are not the
   auditor's checks. Examples: 5+ bills and 2% gone; 5+ bills and 20% lost a field; 3+ identical
   scrapes in a row; 3+ days with no scrape; numbering gaps.

#### Checks against what we already know: all reproduced

`python3 check_known.py --field-loss-dir …/checks wy ky ar`: 12 of 12 pass.

| Known | Scanner | Verdict |
|---|---|---|
| AR: 0 bill files in 119 scrapes, 03-13 to 07-12 | 119 scrapes, 03-13 to **07-13** (08:52 UTC). The last scrape with bills is **03-05**, then no scrape at all for 8 days. | **Confirmed, dates corrected.** The notes say "1,928 bills until 03-12" and "to 07-12". |
| AR: 1,928 bills (`2025`) in raw and archive, not in the data repo | 1,928 raw / 0 data repo / 1,928 July archive | Confirmed |
| KY: sponsors lost on 1,707 bills on 08-20, never back | 1,707 of 1,707 on 08-20; 0 came back; 0% in the latest scrape | Confirmed |
| KY: whitespace in SB4's actions (9) and abstract | 08-20: SB4's abstract, and **10** actions changed in whitespace only (checked by hand: 10 of its 57 differ) | **Corrected (10, not 9)** |
| WY: HB0001, SF0001, SF0002 missing from the 2026 session | Absent until **07-15** (UTC; 07-14 local). They arrived with 312 other bills, 23 → 335. | **Confirmed, and fixed since 07-14** (the self-hosted fix). The "re-check due" in the notes is now answered. |
| WY: 556 bills from `2025` in raw, not in the data repo | 556 raw / 0 data repo / 556 July archive | Confirmed |
| `field_loss.py` rows | KY: 6 of 6 identical; WY and AR: none, on both sides | Confirmed |

**Re-running gives the same contents.** Two re-scans of all three states gave an identical
contents hash. The first version didn't: the example lists depended on Python's set order. That's
fixed, and a test (re-scans in fresh processes with different hash seeds) now catches it.

#### New findings, written down and not acted on

1. **KY and WY froze in their 2026 sessions, while green.** In both, the scrapes didn't change
   for months; only `other_identifiers` was added on 03-18, in both states.
   - **KY:** 74 prefiled bills, unchanged 01-08 to 07-01, through the whole regular session.
     Then 1,737 bills on 07-15.
   - **WY:** 23 bills, unchanged 12-03 to 07-01, through the whole budget session. Then 335
     bills on 07-15.
   - Possibly the same event as the Dec 2025 freeze, but the start dates differ.
2. **KY 2025RS never had sponsors.** None of its 1,441 bills has a sponsor in any raw scrape.
   Sponsors first appear on 2026-01-07, with 2026RS.
3. **AR has no votes anywhere in its raw history** (0 vote files), and no `abstracts` or
   `subject`.
4. **Vote counts that don't match the voter list:**
   - **WY:** up to 616 votes per scrape. Joint-committee and veto-override votes list more voters
     than they count, e.g. SF0001 "H Adopted 59-1" lists 65 yes voters.
   - **KY:** up to 116 per scrape. Mostly one extra "not voting" voter (SB8: 13 counted,
     14 listed).
5. **The duplicate pile-up hit all three states over the same days,** 11-27/28 to 12-02 (AR 7×,
   KY 7×, WY 11×), then cleared. So it was a fleet-wide pipeline problem, not an AR one.
6. **The `-pre-rebuild-2026-07-21` snapshots hold only the current session** (0 bills for AR
   `2025`, KY `2025RS` and WY `2025`). The older sessions are only in the July `<st>-legislation`
   copies.

#### Not done yet

- The IL, TN and ND known numbers: their checks go into `check_known.py` when those states are
  scanned.
- Profiles and check replays (Q15, Q16): after the first wave is reviewed.
- Numbering gaps are a heuristic in the report only. They are noisy for resolutions (KY HCR, HR).

#### Next, waiting for OK

The rest of the first wave, four states at a time, biggest last:

1. DE, NH, FL, TX;
2. NC, ND, GA, MA;
3. TN, IL, CA.

Known-number checks for IL, TN, ND, NH and the others get added before their scans are trusted.

### 2026-11-25: review of the WY, KY, AR step (reviewing chat): approved, go on to the first wave

- **Re-checked independently:**
  - `test_scan.py` passes (18) and `check_known.py` passes 12 of 12, run here.
  - The KY freeze, straight from the raw git history: 74 bill files in every scrape on 01-10,
    02-15, 03-19, 04-15, 06-01 and 07-01, then 1,737 on 07-15.
- **The KY and WY freezes are the most important finding so far.** Kentucky's 2026 regular session
  (January to mid-April, about 1,700 bills) was invisible to us while it happened, and every scrape
  was committed as a normal run. WY's budget session the same. That's Q11 ("quiet during session")
  and the auditor's main target. Keep both as the first known cases for its in-session check.
- **The decisions are fine.** Notes for later:
  - **Decision 1** (every file parsed every scrape): CA (2.8 GB) and IL may take 15–25 min each.
    That's fine. Note their times in the next entry.
  - **Decision 4** (an empty scrape counts every bill gone, the next counts them returned): the
    report and the later checks must treat that as **one outage**, not a mass loss and recovery.
    AR's 119 empty scrapes are the test.
  - **Decision 7 and finding 4** (vote counts vs voter lists): WY's joint-committee and
    veto-override votes listing both chambers look normal for WY, not broken. That's per-state
    normal (Q15), so record it in WY's profile rather than as a finding.
- **Finding 6 corrects the plan:** the `-pre-rebuild-2026-07-21` snapshots hold only the current
  session. The older sessions are in the July `<st>-legislation` copies. Section 0's note about the
  archive should say so (fix it in the next commit).
- **Finding 3 (AR has no votes anywhere):** worth one check in the next wave of notes. Does AR's
  scraper collect votes at all? It may be a scraper limit rather than a failure. For the field
  inventory (Q5) either way.
- **Go ahead with the first wave** in the order given (DE, NH, FL, TX; NC, ND, GA, MA; TN, IL, CA),
  each batch's known-number checks added before its scan is trusted. Then stop for review again.

### 2026-11-25: first wave scanned, all 15 states (stopped for review)

All 15 first-wave states are in `history.sqlite` (192 MB) with a `<st>/report.md` each.
**Nothing is committed.** Section 0's archive note is fixed (the older sessions are only in the
July `<st>-legislation` copies).

**Time per state** (each batch ran side by side, so these are slower than a lone run):

| Batch | Times |
|---|---|
| DE, NH, FL, TX | 2.2 min, 1.4, 1.4, 0.2 |
| NC, ND, GA, MA | 5.4 min, 5.9, 7.4, 10.4 (with `field_loss.py` on GA alongside) |
| TN, IL, CA | 12.5 min, **26**, **28** |

Peak memory was about 1.1 GB per state (measured in batch 2). The laptop has 8 GB, so the biggest
states ran three at a time.

#### Scanner changes in this step (for the reviewer to check)

1. **Conflict markers of any length.** TX's 06-26 auto-merge wrote 8-character markers
   (`<<<<<<<<`), which the 7-character test missed: its 580 files were counted as invalid JSON.
   Now 7 or more count. Tested.
2. **Every file is checked for damage,** not only bills and votes. TX's other 2 conflicted files
   were organization files. Only bills and votes are parsed.
3. **`bills` has three new columns:**
   - `in_data_repo`, `in_archive`, `in_archive_pre_rebuild`: whether that repo has the bill's
     folder (its identifier without spaces, as `build_bill_path` names it);
   - NULL when the repo is missing;
   - Q2 can now be answered bill by bill, not just by session counts.
4. **The scanner refuses an old database.** If the database's columns differ from `scan.py`'s
   schema, it stops with a clear message. The database is derived data: delete it and re-scan.
5. **The report says outright that an empty run is one outage** (review note on decision 4).
   Empty runs were already left out of "Bills that dropped out".

#### Checks against what we already know

`check_known.py --field-loss-dir …/checks` (all 15 states): **76 ok, 0 failed, 10 info.** An info line is a claim with no
exact number to match; it shows the evidence instead. Every state gets the conversion's numbers
(`jsonl-log-conversion-results.md`, "Results by repo"):

- scrape count;
- raw bills with no folder in the data repo, per session;
- conflict-marker files;
- distinct votes on the data repo's bills.

Each also gets its own known events (below).

**Vote counts differ only by key, and the difference is measured.** The logs give a vote with
no roll-call number a new id when its counts change (option C's item 4). The scanner keys a vote
by bill + roll-call id + date + motion + chamber. Keyed that way, the converted logs hold exactly
the scanner's number:

| State | Log ids | Scanner key |
|---|---|---|
| DE | 2,063 | 2,060 |
| NH | 636 | 403 |
| NC | 869 | 868 |
| ND | 2,180 | 2,179 |
| IL | 9,842 | 9,710 (IL's 132 split groups) |
| CA | 21,566 | 21,531 |

FL's 9 extra votes were all on its 19 bills with no data-repo folder, so they're excluded the
same way the logs exclude them.

| State | Known | Scanner | Verdict |
|---|---|---|---|
| DE | Baseline; SB315 flip-flop | No outage. SB315 can't be checked: no per-vote table. | Confirmed / can't tell |
| NH | Sponsors 1,143/1,143 on 12-25 and 12-30; documents 33/33 on 01-28; versions 1,126/1,155 on 08-21; "all came back" | All four losses exactly. Sponsors came back on every bill still scraped (HB1545 was never scraped after 12-30); versions came back. **Documents never came back:** no NH bill has any after 01-28. | **Corrected** (documents) |
| NH | A rate-limited run wiped 436 files (07-14) | Only one scrape that day (334 bills); the wiped run isn't in the raw history as a commit | Can't tell |
| FL | HB 755's committee vote gone on 08-07; 1,480 of 1,902 bills blocked | HB 755: 6 votes ever, 3 missing from its last scrape (08-07). That scrape lost 454 votes. | Confirmed |
| FL | Duplicates 3,123 / 1,878, then 5,330 / 1,878 | 07-25: 3,123 / 1,878; 07-26: 5,330 / 1,878 | Confirmed |
| TX | 41 scrapes; conflict markers in 582 files on 06-26; 89R 11,503 and 891 592 in raw and archive, not in the data repo | Exactly, after fixes 1 and 2. All 582 are in one auto-merge commit, `56fd9b78`. | Confirmed |
| NC | Stuck at 1,794 from 12-14 to 07-14, then 2,334 | 1,794 in every scrape 12-15 to 07-13; 2,334 on 07-14. **No new information from 11-28 at all:** the freeze is as old as the raw history, not from 12-14. | Confirmed, start corrected |
| ND | Error-page voters on 8 nights | Same nights and counts, except 08-11: 1,166 broken votes where the notes have 34. 1,132 of those bad versions are byte-identical to 12-30's (checked in the raw files), so the logs counted only 34 new ones. Both are right. The scanner's number is the one an auditor needs. | Confirmed (explained) |
| GA | Conflict markers on every bill file for 5 days from 07-21 (`0ea65a5e`); 5,480 bills (2025_26) not in the data repo | One scrape, `0ea65a5e`, 914 files (all 352 bill files), 0 readable bills, then **no scrape for 5.3 days**. 2025_26 left the scrape on 06-20, when the special session started. | Confirmed |
| MA | ~210 bills dropped per run 07-01 to 08-07; 4.5× duplicates; 3 bills dropped 07-27 | Bills don't come and go between scrapes (median 0 gone). Instead new bills trickle in after the fix (+68 on 07-15, +118 on 08-07), so the same bills were probably missing every night. Worst duplicates 6.6×. 10 bills last seen 07-26, never back. | Can't tell (evidence shown); duplicates **corrected** |
| TN | 6,787 roll calls emptied over 63 nights, 5,839 on 07-02 | Exactly | Confirmed |
| TN | "Only 37 of ~5,400 bills before July's fix" | 4,589 to 6,096 bills, 11-27 to 02-18; then **no scrape for 128 days**; then partial runs of 14 to 111 bills in late June; 9,112 on 07-02 | **Corrected** |
| IL | Synopsis lost on 8,648/8,648 on 07-13, never back; two 0-bill scrapes | Exactly (07-13 22:55 UTC; 07-03 04:46 and 07-13 21:00) | Confirmed |
| IL | Frozen at ~2,944 bills 12-14 to 07-14 | **8,648** bills in every scrape 12-15 to 07-01; 189 of 190 scrapes unchanged | Confirmed, count corrected |
| IL | "Dan Ugaste" → "Daniel J. Ugaste" on 716 sponsorships | Renamed in partial passes: 536 bills over 5 scrapes on 08-15, 197 over 5 on 08-19 | Confirmed (no exact match) |
| CA | 5,088 or 5,115 reworded actions | 5,115 | Confirmed (5,115) |
| WY, KY, AR | Earlier entry | All still pass, plus the conversion checks (KY 886 and WY 1,258 votes exactly) | Confirmed |

`field_loss.py` rows match exactly for KY, WY, AR, NH (14 rows) and GA (2 rows). For the
self-hosted states the comparison now accepts the night in local (Central) time too.
They also match exactly for TN (12 rows), IL (1) and CA (5): every `field_loss.py` row in all 8
states it covered here is reproduced, and the scanner has no extra rows.

#### New findings, written down and not acted on

1. **Whole sessions went unseen, with no scrape committed at all.** These aren't frozen
   scrapes; the scraper simply committed nothing:
   - **TN:** 02-18 to 06-26, 128 days. Its session ran 01-13 to 04-24.
   - **NH:** 02-04 to 06-26, 142 days. Session 01-07 to 06-04.
   - **DE:** 03-31 to 06-10, 71 days. Session to 06-30.

   A "no scrape for N days" check would have caught all three in days. That's a candidate
   auditor check, and the simplest one there is.
2. **Frozen while committing, in session.** These add to KY and WY:
   - **IL:** 8,648 bills, unchanged 12-15 to 07-01.
   - **NC:** unchanged 11-28 to 07-13. Its session started 04-21.
   - **MA:** exactly 8,975 bills from November to 06-26, while existing bills kept getting new
     actions. So new bills stopped being added during the session. It reached 11,005 on 07-02.
   - **ND:** no 2026 regular session, so its long quiet stretches are normal. A clean quiet
     baseline.
3. **FL's regular session (1,897 bills) left the scrape from 04-25 to 07-24.** Only the 2026D
   special session's 3 to 6 bills were scraped. It came back whole, and it was after the session
   ended (03-13).
4. **FL votes:** 988 of 2,724 votes are missing from each bill's last scrape. Many nights during
   the session lost 100 to 700 votes (worst 722 on 03-03). The House committee-vote loss is much
   bigger and older than the 08-07 example.
5. **TN:** 19,771 actions and 2,434 of 19,062 votes are missing from each bill's last scrape.
   That's large; worth a look in review before it's called a finding.
6. **NH:**
   - `documents` stopped for good on 01-28.
   - HTML version links went away on 06-28 (256 bills) and 07-25 (888 bills), never back.
   - Sponsor names flip between forms ("Jack Flanagan" ↔ "Jack B. Flanagan" on 08-21/22, 95 bills).
7. **The 12-02 duplicate pile-up** also hit NC (7×), ND (8×) and GA (7×). It was fleet-wide.
8. **AR's scraper is meant to collect votes.** `scrapers/ar/bills.py` (openstates-scrapers
   `b66d84cb`) reads vote links from each bill page with one fixed layout path. Zero votes on
   1,928 bills suggests that path no longer matches arkleg's pages. So it's likely a silent
   scraper failure, not a design limit (review note on finding 3). Unconfirmed: it needs the
   live site.
9. **Vote counts vs voter lists:**
   - GA is 1,257 at worst (04-03) and NC 135.
   - As with WY, these are profile material until a state's normal is known.
10. **Bills gone for good while their session went on:**
    - FL: 19 `SPB` bills (Senate proposed bills, which become numbered SBs: likely normal for FL).
    - MA: 98, 71 of them last seen 06-26, the scrape before its 2 empty ones.
    - NH: 7.

#### Next, waiting for OK

- Review this wave with Tamara.
- Then the profiles and check replays (Q15, Q16), starting with the two simplest candidate checks:
  - **no scrape for N days in session** (TN, NH, DE);
  - **scrapes unchanged for N days in session** (KY, WY, IL, NC, MA).

  Both have known start dates to measure days-to-catch against.

### 2026-11-25: review of the first wave (reviewing chat): approved, with two corrections

**Re-checked independently:** `test_scan.py` 19 OK; `check_known.py` on all 15 states gives 68 ok,
10 info, 0 failed. The five scanner changes are sound; refusing an old database is the right call.
The TN, NH and DE no-scrape gaps match `git log` of the raw repos exactly (128.4, 142.4 and 71.1
days).

**Correction 1: the no-scrape gaps were a fleet problem, not three states.** Gaps over 14 days in
all 56 raw repos (`git log --format=%ct`, not the database):

- **About 20 states** had one. Most end at the same few minutes, so the scrapers were restarted
  together, not fixed state by state:
  - **06-26 12:21 to 13:10 UTC:** AZ (147 days), CT (141), DC (147), HI (95), LA (46), MP (29),
    NH (142), NJ (128), NM (147), TN (128), TX (41). VA and VI (152) restarted 07-01.
  - **01-30 11:29 UTC:** AZ, DC, NM, TX, VA, VI, after gaps of 19 to 47 days.
  - **09-29 20:19 UTC, the last commits before the pause:** AR (40 days), CO (35), FL (53), GU (52),
    MA (53), PA (70), VI (70) had committed nothing since August.
- So "no scrape for N days in session" needs **two levels**: per state, and fleet-wide ("K states
  went quiet the same night"). The fleet check would have caught February in a day or two.
- Most of these states are outside the first wave (AZ, CT, DC, HI, LA, NJ, NM, VA, VI, CO, GU, PA).
  That's a reason to scan them next: their gaps are already known, so they're cheap test cases for
  the check replays.

**Correction 2: TN's 19,771 "lost" actions are a chamber swap, not a loss (finding 5).** They are
in the data repo today.

- From the 06-26/07-02 scrapes on, TN's Senate bills have their chambers reversed. SJR 0001 has 44
  actions in every scrape. In February 41 read `upper` (Senate) and 3 `lower`. In September the same
  actions, same dates and words, read 41 `lower` and 3 `upper`. "Filed for introduction" on every
  SB and SJR is now `lower`.
- The scanner matches actions on date + chamber, so these show as gone + new. The logs do the same,
  so the backfill appended each one again. In `govbot_data/full/tn-legislation`, **3,105 bills have
  19,712 actions logged twice** under opposite chambers: 19,560 added on 07-02 and 152 on 06-26.
  2,154 are SB, 626 SJR, 285 SR and 40 HJR. SJR0001's log has 82 action ids for 44 actions, and its
  `metadata.json` has the reversed chambers.
- Kind: **corruption** (wrong data that looks valid), and the first one found that's live in a data
  repo. For the findings doc and `tn.md`; probably an OpenStates bug report. Not acted on.
- A candidate auditor check: **an action's chamber changes while its date and words don't.** Also
  worth a scanner column, since it's cheap.
- **TN's 2,434 lost votes don't fit this.** They're spread over House bills too (HB 844, HJR 425,
  SJR 799, SB 354), so they remain an open question for the next step.

**The other findings:**
- 2, the frozen states: the NC start date and IL count corrections are right, and IL at 8,648 is a
  better baseline than the notes' ~2,944.
- 3, FL's regular session missing from 04-25 to 07-24: like GA on 06-20, the scrape followed the
  newest session, a special session, and dropped the regular one. A profile item for states with
  special sessions.
- 4, FL votes: not re-checked here. Before calling it a finding, check it isn't a key change like
  TN's.
- 8, AR votes: agreed it's likely a silent scraper failure; leave it unconfirmed until someone looks
  at arkleg.

**Next:** go ahead with the profiles and check replays, as proposed. Add the fleet-level version of
the no-scrape check and the chamber-swap check to the list. Scan the second-wave states with the
known gaps when there's time.

### 2026-11-26: profiles and check replays, Q15 and Q16 (stopped for review)

**Nothing is committed.** Everything below is on the SSD under
`/Volumes/govbot-data/scratch/history-analysis/`:

- `profiles/<st>.json`;
- `replay-profile.md` and `replay-uniform.md`;
- a `replay_alarms` table in `history.sqlite`.

The database was rebuilt from scratch with the two new scanner measures (below), for **27
states**:

- the first wave;
- the second-wave states with known gaps: AZ, CT, DC, HI, LA, NJ, NM, VA, VI, CO, GU, PA, MP.

All known-number checks still pass (76 ok, 10 info, 0 failed). IL took 49 min and CA 53 min,
alongside the others.

**A count correction:** the first-wave table in section 1 lists **14** states, not 15. Earlier
entries here repeated "15".

#### New code

| File | What it does |
|---|---|
| `profiles.py` | Each state's normal (Q15), from its healthy days only (outside every known failure and every gap of over 14 days) |
| `replay.py` | Runs each candidate check day by day, as the auditor would have, and scores it (Q16) |
| `known_events.py` | The answer key (known failures with dates, the check expected to catch each, and sources) and `CAVEATS`, how a state's history misleads |
| `daily.py` | The session calendar (`session-calendar-2026.md`), all 56 raw repos' commit times, and the day-by-day view |

`test_scan.py` now has 24 tests.

A profile holds:

- the filing pattern per session;
- new bills, actions and votes per day, in session and out (median, 90th percentile);
- the longest quiet run and the longest gap between scrapes;
- field coverage;
- the usual vote-count mismatch;
- session switches;
- **suspected freezes;**
- **caveats;**
- per-state thresholds, each saying how it was set.

A state with fewer than 60 healthy days, or fewer than 10 in session, is marked **thin**, and
takes the fleet's median thresholds. Thin states: AR, AZ, CT, FL, IL, KY, ND, NH, NM, TX, VA, WY.

#### Scanner changes (both from the first-wave review)

1. **`actions_chamber_swapped`:** an action that left and came back with the same date and
   words under another chamber. It's matched before rewording, so it's no longer counted as lost
   or reworded. It's also a column in `bills`.
2. **`votes_rekeyed`:** a vote that left and came back under another key on the same bill
   that night (same day and voters, or same day and motion). It isn't counted in
   `votes_gone_for_good`. TN: 696 re-keyed. FL: 0.

#### FL's 988 lost votes: not a key change, and almost all House committee votes

Measured with Tamara's FL rules, now in `fl.md` ("Reading FL's raw history") and in
`known_events.CAVEATS["fl"]`:

- **None of the 988** is in its bill's last scrape under another key.
- **987 are House committee votes:**
  - **454 went missing on 08-07,** in a run with a 78–99% block rate;
  - **533 on four nights during the session** (02-12: 76, 02-25: 133, 03-01: 24, 03-03: 300),
    under the old scraper, which recorded no block rate. Only House committee votes went
    missing on those nights, which fits blocks, but it can't be proven.
- **The only other one** is SB 7040's Senate floor vote (02-11), missing from 03-14 on. It's
  reported apart.
- **By best version ever seen** (rule 1), FL has 2,724 votes; 1,736 are in its last scrape.
- **FL's misleading windows** are known events with no check expected to catch them, so they're
  left out of FL's normal:
  - the House committee vote loss;
  - 04-25 to 07-24, when the regular session was out of the scrape;
  - July and August partial runs (auto-saved up to 40 times a day);
  - the 07-23 change to the custom scraper image.

#### The replay (per-state thresholds)

Days to catch count from the failure's start. For the in-session checks they count from the
session's start, if that was later.

| Check | Known failures | Caught | Days to catch, median (worst) | Alarms | Matching no known failure |
|---|---|---|---|---|---|
| `no_scrape` (per state; in and out of session) | 28 | **28** | 6 (14) | 50 | 9 |
| `fleet_no_scrape` (3+ states quiet 2+ days, within 2 days) | 34 | 23 | **1 (2)** | 36 | **0** |
| `unchanged` (in session, nothing new for N days) | 4 | **4** | **6 (12)** | 16 | 5 |
| `no_new_bills` (in session, actions but no new bill) | 1 | 1 | 20 | 9 | 5 |
| `empty_scrape` | 7 | **7** | 0 | 19 | 1 |
| `field_loss` (option C's 50% of ≥20) | 6 | **6** | 0 | 9 | 1 |
| `broken_votes` (20+ emptied or error voters) | 9 | 8 | 0 | 15 | 2 |
| `chamber_swap` (50+ actions) | 1 | **1** | 0 | 2 | 0 |
| `bill_drop` (5%+, not a session switch) | 0 | — | — | 7 | 0 |

**Every known failure of the kinds these checks target was caught.** The misses:

- **ND's 09-19 "Proxy Error":** only 15 votes, under the 20 limit.
- **11 gaps the fleet check missed,** each of which started on its own (DE, HI, DC, VI, …). The
  per-state check caught all of them. Each check has its job:
  - the fleet check caught the shared nights in 1–2 days (12-04, 02-06, 08-08…), with no
    unexplained alarm;
  - the per-state check caught everything, in 2–14 days.
- **The frozen states, measured from their session's start:** KY 6 days, IL 6, WY 6, NC 12.
  KY's whole 2026 session would have been flagged in its first week. MA's stuck bill count:
  20 days.

**Per-state thresholds against one rule for all** (`replay-uniform.md`):

- **Same catches.** Unexplained alarms fall from 56 to 23: `no_scrape` 23 → 9, `unchanged`
  24 → 5.
- **The cost:** states that normally skip days get a slower `no_scrape`. Worst catch is 14 days
  (CO), 12 (MP) and 10 (NJ), against 6 with the uniform 3/7 days.
- **The question for review:** is a 14-day limit acceptable anywhere in session? Capping the
  in-session limit at about 7 days would keep most of the gain.

**Self-calibration nearly hid a freeze, and the fix is in.** At first, PA's profile took its
189-day in-session quiet run as "normal" and set its `unchanged` limit to 191 days. That raised
the fleet median to 27 days, and so KY's limit too.

- **The fix:** an in-session quiet run over 21 days is reported as a **suspected freeze** and
  isn't used to set a limit.
- **Suspected freezes,** none of them in the notes:
  - **PA:** 189 days from 01-06. 3,578 bills, with no new bill, action or vote from December to
    June, in session. A real freeze, the same shape as IL and NC. Left out of the answer key on
    purpose, so its catch isn't scored as known.
  - **HI:** 61 days from 01-22.
  - **LA:** 64 days from 03-09, the day its session started.
  - **NJ:** 39 days from 07-01.
  - **NC:** 25 days from 07-15.
  - **MP:** 29 days from 06-27.
  - **GU:** 78 and 228 days. GU's normal: no actions on any bill (now a caveat).
  - **VI:** 307 days. No data at all (below).

#### New findings, written down and not acted on

1. **PA froze through most of its session** (above). It's a new member of the freeze group,
   caught by `unchanged` from 01-12.
2. **VI has had no data since 2025-12-07.**
   - Its "Scrape data for vi" commits kept running until 10-29, but every one since 12-07
     changes only `.windycivi/warning_history.json`.
   - That corrects the first-wave review's VI entry (a 152-day gap, then a restart on 07-01).
     That entry counted all commits.
   - Every other raw repo has about 30 non-data commits (workflow updates), so **a no-scrape
     check must count only commits that touch `_data/<st>/`.** Both the scanner and the replay
     do.
3. **AZ, a lead:** 97 to 217 roll calls "emptied" every night from 07-24 to 09-29, so votes seem
   to flip between empty and full each night. To check against AZ's converted logs before it's
   called a finding. HI's 113 on 09-17 may be the known HI parsing fix (`tn.md`).
4. **DE:** `versions` gone from 562 of 801 bills on 07-15, all back the next scrape. Its first
   run after the July fix.
5. **CT's and PA's 07-21 "empty scrapes"** are manual cleanup commits ("chore: clear
   duplicate-accumulated scrape data"), not scrapes. They're now known events.
6. **A 7- to 13-day fleet-wide gap in early July** (AZ, CT, ND, NM, VA and others, to 07-14/15).
   These are the per-state check's remaining "unexplained" alarms. They're real outages, just
   under the 14-day line.

#### Not ready as checks

- **`no_new_bills`:** 5 unexplained alarms (CA's summer recess, DC, NJ, NC and MP near session
  ends). Bill-filing deadlines make it noisy. It needs each state's deadlines before it can be
  used.
- **`bill_drop`:** its only alarm is FL's partial run (07-25), which the FL caveats explain.
  No known failure to test it on.

#### Next, waiting for OK

1. Review this step: the thresholds, the `no_scrape` in-session cap, and the suspected freezes.
2. Then the auditor design doc, from section 6: the checks that are ready (`no_scrape` +
   `fleet_no_scrape`, `unchanged`, `empty_scrape`, `field_loss`, `broken_votes`,
   `chamber_swap`), their per-state settings, and the caveats.
3. In parallel, the third-wave scans, so every state has a profile.

### 2026-11-26: review of the profiles and replays (reviewing chat): approved, with notes

**Re-checked independently:**
- **VI:** `git log --since=2025-12-08 -- _data/vi` is empty. All 39 commits since then touch only
  `.windycivi/warning_history.json` (28) or the workflow (11). My first-wave gap table counted
  every commit, so it's replaced by the scanner's data-only count. The rule "a no-scrape check
  counts only commits that touch `_data/<st>/`" is right, and belongs in the design doc.
- **PA:** confirmed, and **longer than reported.** PA's only scrape with anything new before
  07-14 is the first one, **11-27** (3,578 bills). Every scrape after it adds 0 bills, 0 actions
  and 0 votes, until 07-14 brings 1,279 new bills, 5,606 actions and 2,140 votes. So PA was
  frozen for the whole raw history, about 229 days, like NC.
  - The 189 days start on 01-06 because that's where the session calendar starts PA's session.
    But PA's legislature meets all year, with its two-year session running the whole time.
  - **Check the calendar for full-time legislatures** (at least CA, IL, MA, MI, NJ, NY, OH, PA,
    WI, US): they should count as in session all year, or the in-session checks start late for
    exactly the states most likely to have news any day.

**On the review question (the in-session `no_scrape` limit): cap it at 7 days.** That's my
recommendation; it's Tamara's call.
- A 14-day blind spot in session is the kind of miss this auditor exists to prevent.
- The cost is a few more alarms in states that skip days, and a skipped-day alarm is cheap to
  dismiss.
- Out of session, keep the per-state limits.

**The replay scores are in-sample, so read them as best cases.** The profiles, the thresholds
and the scoring all come from the same history, and some thresholds were adjusted after seeing
what they missed (the freeze exclusion, rightly).
- **Proposal:** treat the third wave as a **held-out test**:
  1. Fix the check settings and fleet medians first, and record them in the design doc.
  2. Then scan the third-wave states and score the checks on their known events without
     re-tuning.
- That's the nearest thing to next year we can get now.

**Smaller notes:**
- **`broken_votes`:** split it. A voter name that is error-page text ("Service Unavailable",
  "Proxy Error") is never legitimate, so alarm on 1 or more. Keep the 20 limit for emptied roll
  calls only, which can be noisy. That would catch ND's 15-vote 09-19 night.
- **FL:** the 987 House committee votes match the FL rules. They're FL's block cost, measured.
  SB 7040's lost Senate floor vote is worth one look, since FL's Senate site isn't the blocked
  one.
- **AZ's nightly emptied votes:** check whether it's the A, B, A flip-flop the vote rule already
  handles (`log_jsonl.py`), before calling it a finding.
- **`no_new_bills` and `bill_drop`:** agreed, they aren't ready. Keep them in the design doc as
  "needs per-state deadlines" and "no test case".

**Next:** go ahead with the auditor design doc and, in parallel, the third-wave scans, run as the
held-out test above. Stop for review after.

**Tamara's decisions, collected:**
1. The in-session `no_scrape` cap (7 days recommended).
2. Whether the third wave is scored as a held-out test.
3. (Carried) TN's doubled actions in the data repo: whether and how to fix, after the analysis.

### 2026-11-26: overnight instructions (reviewing chat, for Tamara, who is asleep)

Tamara's decisions:
1. The in-session `no_scrape` limit is capped at **7 days**.
2. The third wave **is scored as a held-out test**.
3. Everything else in the review entry above is approved as written.

Work through the steps below without stopping for review. Nobody will answer before morning.
Instead of stopping, write a dated progress entry at the end of this section after each step,
then go on.

**Limits, all night:**
- **No commits, no pushes, no PRs.** Don't write to any GitHub repo.
- Don't unpause anything.
- Never write into `raw-scrapers/`, `govbot_data/full/`, `govbot-archive/` or `windy-civi/`. They're
  read-only.
- Scratch and output go only under `/Volumes/govbot-data/scratch/history-analysis/`.
- Keep the laptop's own disk (20 GB free at 01:00) above 10 GB. If it drops below, stop scanning
  and write why.
- The laptop has 8 GB of memory: at most 3 scans at once, and at most 2 when IL, CA, NY or another
  big state is among them.
- If a usage limit pauses you, just carry on where you left off when it lifts.
- Don't change the answer key (`known_events.py`) to make a score look better. You may **add** a
  known event that you find in `tamara-notes/` with its source, and say so in the entry.

**Steps, in order:**

1. **Apply the review notes to the code:**
   - the 7-day in-session cap;
   - full-time legislatures in session all year (check the list against
     `session-calendar-2026.md`, and say which you used);
   - `broken_votes` split: error-page voters alarm at 1 or more, emptied roll calls stay at 20;
   - PA's freeze counted from 11-27.

   Re-run the tests, `check_known.py` and the replay on the 27 scanned states. Record the new
   scores.
2. **Freeze the settings for the held-out test:**
   - Write every check's rule, its limits, the per-state settings method, the fleet medians and
     the thin-state fallback to `/Volumes/govbot-data/scratch/history-analysis/frozen-settings.json`.
   - Record its `sha256` and the time in your progress entry **before any third-wave scan
     starts.** That's the proof the settings came first.
   - After this, no change to check logic or limits until the held-out scores are written. A bug
     that crashes the scanner may be fixed; say so, and show that it doesn't change any score on
     the 27 states.
3. **Draft the auditor design doc,** from section 6, while the scans run. Save it as a new file in
   `shared-docs/`, with the frozen settings as its starting values.
4. **Scan the third wave,** 29 states: AK, AL, IA, ID, IN, KS, MD, ME, MI, MN, MO, MS, MT, NE, NV,
   NY, OH, OK, OR, PR, RI, SC, SD, USA, UT, VT, WA, WI, WV.
   - Small states first.
   - Add known-number checks where the conversion results or `tamara-notes/state-specific/` have
     numbers; a state with none gets only the conversion checks.
   - Run with no re-tuning.
5. **Score the held-out test:**
   - Run the frozen checks on the 29 new states and write `replay-heldout.md`.
   - Show catches, days to catch, and unexplained alarms, next to the in-sample scores.
   - Then list what you would change, **without changing it.**
6. **Write the morning summary** at the end of this section. Keep it short, in plain words, for
   Tamara:
   - what's done;
   - the held-out result, in one or two sentences;
   - new findings;
   - anything that failed or was skipped;
   - decisions waiting for her.

**Stop early only if:**
- a known-number check fails and you can't explain why;
- the database or a scan gives different results on a re-run (idempotency);
- disk or memory goes past the limits above.

Write what happened and stop. Don't work around it.

#### Overnight progress

(Dated entries go here.)

##### 2026-11-26, step 1: review notes applied, re-scored (27 states)

**Changes:**

- **In-session `no_scrape` limit capped at 7 days** (`profiles.IN_SESSION_NO_SCRAPE_CAP`). The
  fleet fallback is capped too.
- **Full-time legislatures are in session all year** (`daily.FULL_TIME`): CA, IL, MA, MI, NJ, NY,
  OH, PA, WI, plus USA and DC.
  - That's the review's list plus DC, whose council meets all year (the calendar already says
    01-02 to 12-31).
  - The calendar gives all of the others shorter windows (e.g. PA 01-06 to 11-30, NY to 06-05,
    WI to 03-19, CA to 08-31).
  - The territories are already all year in the calendar.
  - For these states, days to catch count from the failure's start, not a calendar session
    start.
- **`broken_votes` split:** one check with two limits. An error-page voter alarms at 1 or more
  (`ERROR_VOTERS_MIN`); emptied roll calls alarm at 20 (`EMPTIED_VOTES_MIN`). I kept one check
  name so no answer-key entry had to be relabelled.
- **PA's freeze added to the answer key:** `unchanged`, 2025-11-28 to 2026-07-13, source this
  doc's review entry, as the overnight rules allow. It was left out before, while it was only
  the replay's own finding.
- **One further change, before freezing the settings:** a gap between scrapes that overlaps a
  fleet-wide outage (a `fleet_no_scrape` alarm day) is no longer taken as a state's normal gap.
  - Without it, early July's 7–13-day outage (finding 6) set ND's, HI's, LA's, DE's and CO's
    out-of-session limits to 13–15 days.
  - Making FL, AZ, TX and the other full-time-affected states fall back to that median gave
    12-day catches.
  - With it, every state's measured limits are 3–5 days in session and 7 out of session.

**Results:**

- `test_scan.py`: 24 OK.
- `check_known.py`: 76 ok, 10 info, 0 failed.
- **Replay** (`replay-profile.md`): 80 caught, 11 missed, 37 alarms matching no known failure.
  The uniform run: 80 / 11 / 58.

| Check | Known | Caught | Days, median (worst) | Alarms | Unmatched |
|---|---|---|---|---|---|
| `no_scrape` | 28 | 28 | 6 (6) | 69 | 22 |
| `fleet_no_scrape` | 34 | 23 | 1 (2) | 36 | 0 |
| `unchanged` | 5 | 5 | 6 (12) | 19 | 4 |
| `no_new_bills` | 1 | 1 | 20 | 11 | 7 |
| `empty_scrape` | 7 | 7 | 0 | 19 | 1 |
| `field_loss` | 6 | 6 | 0 | 9 | 1 |
| `broken_votes` | 9 | **9** (ND 09-19 now caught) | 0 | 16 | 2 |
| `chamber_swap` | 1 | 1 | 0 | 2 | 0 |

**What this changes:**

- **`no_scrape` is now the same per state and uniform.** It catches every gap within 6 days.
  Its 22 unmatched alarms are all real 7–13-day stretches with no scrape (most in July's fleet
  outage). They're short outages, not false alarms.
- **The earlier "per-state halves the false alarms" result came from inflated limits,** set by
  that outage. The real per-state gain is in `unchanged`: 4 unmatched against 25 uniform, with
  the same catches.
- **PA's freeze, now in session from day 1:** caught 5 days after its first scrape.
- **IL, full-time:** caught at once; it was already quiet before its event start.

##### 2026-11-26, step 2: settings frozen for the held-out test (before any third-wave scan)

- **File:** `/Volumes/govbot-data/scratch/history-analysis/frozen-settings.json`
- **sha256:** `e5c67717a285d99c584b4d0d961704ada63cfa52a57c863bcf6b43dd82a0b18e`
- **Frozen at:** 2026-11-26T07:48:07+00:00 UTC. No
  third-wave scan had started; the database held only the 27 in-sample states.
- **Written by:** `freeze.py` (new).

What it holds:

- **Every check's rule and limits.**
- **The per-state method,** including:
  - healthy days;
  - the in-session cap of 7;
  - fleet-outage gaps left out;
  - the suspected-freeze limit of 21 days;
  - the thin rule;
  - the full-time list.
- **The fleet fallback values, from the measured, non-thin states:**
  - `no_scrape` 3 days in session (14 states measured it) and 7 out of session (7 states);
  - `unchanged` 7 days (14 states);
  - `no_new_bills` 21 days (the default; none measured).
- **The 27 in-sample states' own settings.**
- **The sha256 of** `scan.py`, `daily.py`, `profiles.py` and `replay.py`, and separately of
  the answer key (`known_events.py`).

How it's enforced:

- `replay.py --frozen` refuses to score if the code's check rules or profile method differ from
  the file.
- `profiles.py --frozen` gives new states the frozen fleet fallback, not one recalculated with
  them included.
- **The answer key will change,** by additions only: known events for third-wave states, from
  `tamara-notes/` with sources. Its sha256 is recorded separately for that reason.

##### 2026-11-26, step 3: auditor design doc drafted

`shared-docs/state-auditor-design.md` (new). Its sections:

- what the auditor does and doesn't do;
- the nine checks, 7 ready and 2 not, with rules, in-sample scores and status;
- the two levels of no-scrape (per state and fleet), counting data commits only;
- what "in session" means;
- the profile method, with the frozen starting values for the 27 in-sample states;
- the caveats (FL, GU, VI; WY as a profile note);
- the output list;
- the evidence;
- six open decisions.

It points to this doc's step 5 for the held-out scores, which may change its numbers.

##### 2026-11-26, step 4: third wave scanned (29 states)

All 29 scanned with the frozen code: 3 at a time, then MT, USA and NY 2 at a time. Took about
5 hours, finishing 09:33 UTC. No crash, no unreadable state. The laptop disk stayed at 18–20 GB
free. Logs: `scratch/history-analysis/checks/wave3.log`. Known-number checks:
`checks/wave3-check_known.txt`.

**Known-number checks:**

- **88 pass, 0 fail, 1 not compared.**
- The checks are the conversion table's numbers for every state (scrapes, distinct votes, raw
  bills with no folder, conflict files for OH and WV), from `jsonl-log-conversion-results.md`.
  They were added before any check was run.
- **Four failed on the first run.** Each is explained below, and its explanation is written
  next to its number in `check_known.py`:
  - **MT (+31 votes in the scanner):** MT publishes the same roll call many times under
    different roll-call numbers. SB 155 has 10 copies of one 02-06 committee vote
    (`2025-SB 155-828` … `-1220`): same time, motion, counts and voters. The log keeps them as
    one id; the scanner counts each.
  - **VT (+1):** H 740's 05-19 Senate roll calls #157 and #161 both passed 17–13 and got one log
    id. These are two different roll calls, so **#161 is missing from VT's
    `vote_event_logs.jsonl`: a real loss in the logs** (new finding 1 below).
  - **USA (−174):** 174 votes name their bill another way: "SJRes 5" or "HJ RES 1" instead of
    the bill's "SJRES 5". The formatter files them under the bill; the scanner matches names
    exactly, so it doesn't. This is a scanner gap. It is left as is under the freeze and listed
    in step 5.
  - **PR (not compared):** PR's data repo isn't on the SSD. It was converted on a case-sensitive
    disk image, because two file names differ only in case. So there are no folders to compare.
- **Idempotency:** I re-scanned AL and compared its six tables. The sha256 was the same before
  and after.
- **Tests:** 24 OK.

**Answer key: additions only, after the freeze, each with its source.**

- **10 events from `notes-by-state.md`:**
  - the December 2025 freeze in AK, IN, MI, NE, NY, OH, SC, USA and VT
    (`unchanged`, 2025-12-14 → 2026-07-13, "stuck at N bills while green");
  - WA's freeze on 07-24 → 07-25. WA was out of session, so `unchanged` can't catch it. It's in
    the key for completeness and doesn't count as a miss.
- Its sha256 now differs from the frozen one, as planned.
- **Nothing was changed or removed.**

**What the scans show (before scoring):**

| | |
|---|---|
| Scrapes | 253 (MD) to 688 (USA) |
| Largest | NY, 25,503 bills |
| Smallest | NV, 27 bills |
| Scrapes with 0 readable bills | 13: NY 6; ME, MO, MT, OH, PR, SD and USA 1 each |
| Conflict-marker files | OH 464 on 07-21, WV 14 on 07-14 (both known) |
| Top-level field loss (≥50% of ≥20) | KS only: `extras` and `other_titles` on 781 of 781 bills, 2026-05-09 |
| Scraped after the 09-30 pause | MI, OH and USA, until 10-29; PR until 10-01; UT's last is 09-27 |

- The full-time states MI, OH and USA kept getting commits after the pause. The replay stops at
  the pause either way.
- **The AZ "emptied votes" alarms** (in-sample) are a scanner artifact, confirmed in step 1's
  follow-up:
  - 217 vote keys appear in one scrape both with voters and without;
  - the logs show zero real flips.

  This is not fixed, because of the freeze. It's listed in step 5.

**New findings, written down and not acted on:**

1. **The JSONL log can merge two different roll calls** that share a day, chamber, result and
   counts. VT H 740 #161 is lost.

   The bill-folder rule in `CLAUDE.md` says votes are deduped by roll-call `identifier` + date +
   motion. VT's two roll calls have different identifiers, yet they share one id. So the id
   suffix (`~<hash>`) doesn't take the identifier into account.

   How many other states this hits is not measured yet. MT's 31 are true duplicates, so merging
   them is right there. This one belongs to the logs workstream.
2. **KS lost `extras` and `other_titles` on every bill (781 of 781) on 2026-05-09, and neither
   came back** before the pause. KS was out of session (adjourned 04-10). It isn't in the
   answer key, so the replay will score it as unexplained.

##### 2026-11-26, step 5: held-out scores (29 states, frozen settings)

**How it was run:**

- `profiles.py --frozen` gave the 29 states their profiles with the frozen fleet fallback.
- `replay.py --frozen` checked the code against `frozen-settings.json` before scoring. It
  matched.
- Output: `scratch/history-analysis/replay-heldout.md` and the `replay_alarms` rows with
  mode `heldout`.
- A second run gave a byte-identical report.
- **No check logic or limit was changed.**
- **One answer-key addition, made during scoring:** WV's December 2025 freeze. It's in the
  2026-07-14 recovery summary's table of frozen states (~2,709 → 5,950 files) and in
  `error-tracking.md`. I missed it when I added the third-wave events in step 4.
  - Before the addition: 38 caught, 12 missed, 59 unmatched.
  - After: 39 caught, 12 missed, 56 unmatched.

**Scores, held-out next to in-sample:**

| Check | Held-out: caught / known | Days to catch, median (worst) | Unmatched | In-sample: caught / known | Days | Unmatched |
|---|---|---|---|---|---|---|
| `no_scrape` | 6 / 6 | 6 (6) | 28 | 28 / 28 | 6 (6) | 22 |
| `unchanged` | 10 / 11 | 6 (9) | 13 | 5 / 5 | 6 (12) | 4 |
| `empty_scrape` | — (none known) | — | 7 | 7 / 7 | 0 | 1 |
| `field_loss` | — | — | 1 | 6 / 6 | 0 | 1 |
| `broken_votes` | — | — | 0 | 9 / 9 | 0 | 2 |
| `chamber_swap` | — | — | 1 | 1 / 1 | 0 | 0 |
| `no_new_bills` | — | — | 2 | 1 / 1 | 20 | 7 |
| `bill_drop` | — | — | 4 | — | — | 0 |
| `fleet_no_scrape` | 23 / 34 | 1 (2) | 0 | the same | | |

- **`fleet_no_scrape` is not a held-out score.** It reads all 56 raw repos both times, so its
  row is the same table twice.
- **The one `unchanged` miss is WA, 07-24 → 07-25.** It was out of session, where `unchanged`
  doesn't run by design.
- **Held-out has no known failures for the per-scrape checks,** so for them only the unmatched
  alarms can be judged.

**The unmatched alarms (56), one by one:**

- **`unchanged`, 13. All are real freezes nobody wrote down,** not false alarms. In every
  window the state was scraped again and again in session, with **zero** new bills, actions
  or votes:

  | State | Since | Days in session with nothing new | Stuck at |
  |---|---|---|---|
  | WI | 12-18 | 147 | 1,624 bills, through 05-12 |
  | MD | 01-20 | 84 | 531 |
  | KS | 01-18 | 83 | 781, until 702 new bills arrived on 05-09 |
  | ID | 01-20 | 73 | **1 bill**, the whole session |
  | SD | 01-19 | 71 | 41 |
  | MS | 02-11 | 64 | 2,991 |
  | WA | 01-18 | 54 | 2,075 |
  | WI | 06-05 | 40 | |
  | MN | 04-14 | 35 | 9,808 |
  | OR | 02-08 | 27 | 264 |
  | MS | 01-14 | 21 | |
  | WI | 08-06 | 14 | |
  | MN | 03-05 | 7 (after the 17-day limit) | |

  - Most started inside the December 2025 freeze window. The recovery summary's "16 states
    plus USA" lists AK, IN, MI, NE, NY, OH, SC, USA, VT and WV from this wave, but not these.
  - `error-tracking.md` lists them only as "(stale)" counts on 07-02. ID's "completed 2026
    session only shows 1 bill" comes closest.
  - **They aren't in the answer key, because the notes don't call them failures.** If Tamara
    confirms them, held-out `unchanged` becomes 22 caught of 23 with 0 unmatched.
- **`no_scrape`, 28:**
  - **14 are the 07-05 → 07-14 fleet outage,** 6–10 days. The fleet check already caught it on
    day 1. These are the same kind of alarm as most of the 22 in-sample ones.
  - **5 are 07-18 → 07-20, 3–4 days:** MI, NY, OH, USA and WI, all full-time, so in session.
  - **9 are 1–6-day in-session gaps:** AL, MO ×3, MS ×2, RI, UT ×2. They are real gaps, just
    over a 3-day limit.
- **`empty_scrape`, 7:**
  - **6 are not scrapes:**
    - MO, MT, OH, PR and USA on 07-21 are the same manual commit, "chore: clear
      duplicate-accumulated scrape data", that CT and PA have in the key;
    - SD on 12-02 is a manual "Delete _data/sd directory".

    Their only source is the raw git log, not `tamara-notes/`, so under the overnight rule they
    stay unmatched.
  - **ME on 07-08 is a real scrape** with 4 files and 0 bills.
- **`bill_drop`, 4:** ME on 04-04 (1,521 of 2,442) and MO on 04-11, 06-17 and 07-21 (about 1,055
  of 3,155). Every dropped bill came back. These are partial scrapes, real but brief.
- **`field_loss`, 1:** KS on 05-09, `extras` and `other_titles` on 781 of 781. Neither came back.
  It's the same scrape that ended KS's freeze. **Real, and unrecorded.**
- **`chamber_swap`, 1:** IA on 08-09, 54 actions moved from "legislature" to "upper". Not looked
  into.
- **`no_new_bills`, 2:** UT 02-09 → 03-07 and WI 08-20 → 09-29. It's still not ready
  (design doc).

**In one line:** on states the settings never saw, every known failure that a check can see was
caught within 6 days (`unchanged` worst 9). Of the 56 unmatched alarms:

- **about 15 are real failures the notes never recorded:** 13 `unchanged`, the KS field loss,
  and ME's empty scrape;
- **about 20 duplicate the fleet check or are maintenance commits;**
- **the rest are short real gaps or brief partial scrapes.**

**What I would change. None of it is changed, because of the freeze:**

1. **Per-state `no_scrape`: stay quiet on days a fleet alarm already covers.** That removes 14
   held-out and most of the 22 in-sample unmatched alarms, and costs no catch: every one is
   inside a caught fleet outage.
2. **Skip maintenance commits** (`chore:` messages, "Delete _data/…") as scrapes. That removes 6
   `empty_scrape` alarms and the MO 07-21 `bill_drop`. It would also handle CT and PA without
   answer-key entries.
3. **Scanner:**
   - **Match a vote to its bill by a normalized identifier:** case, spaces and "Res"/"RES"
     ("SJRes 5" = "SJRES 5"). USA has 174 votes the scanner doesn't attach (step 4).
   - **Count a vote as emptied only when every copy in the scrape is empty** (`all`, not
     `any`). That fixes the AZ artifact: 217 keys with both copies.
4. **`bill_drop`: alarm only when the bills stay gone for a second scrape,** or rate a one-scrape
   drop lower. All 4 came back.
5. **Answer key:**
   - Tamara to confirm the 13 unrecorded freezes, KS's field loss and the 07-21 chore commits.
     Then they go in with her as the source.
   - The key has no held-out events for the per-scrape checks, so those stay untested on new
     states.
6. **`unchanged` limits:**
   - WI learned 22 days and MN 17 from quiet runs that were probably freezes themselves.
   - WI's own profile already marks three suspected freezes: 168, 61 and 35 days. Only 1.5% of
     its in-session scrape days had anything new, so the "healthy" 20-day quiet run that set
     its limit sits between freezes.
   - The 21-day suspect line catches long freezes but not one-to-three-week ones.
   - Profiles should exclude the windows the replay flags, once a person confirms them (review
     loop).

##### 2026-11-26, morning summary (for Tamara)

**Done:** all six overnight steps.

1. Review notes applied, and the 27 states re-scored.
2. Settings frozen before any third-wave scan: `frozen-settings.json`, sha256 `e5c67717…`.
3. Auditor design doc drafted: `shared-docs/state-auditor-design.md`.
4. All 29 third-wave states scanned. Every known-number check passes or is explained.
5. Held-out scores written: `scratch/history-analysis/replay-heldout.md`.
6. This summary.

Nothing was committed, pushed or unpaused. Nothing was written outside the scratch folder, this
worktree and `tamara-notes`. Disk stayed at 18–20 GB free.

**Held-out result:** on the 29 states the settings never saw, every known failure a check can
see was caught: 16 of 17, within 6 days (`unchanged` worst 9). The one miss was out of session,
by design. Of the alarms that matched nothing known, the biggest group (13 `unchanged`) are real
session-long freezes that were never written down.

**New findings (not acted on):**

- **Unrecorded freezes** in session, with zero new bills, actions or votes:
  - WI: 147, 40 and 14 days;
  - MD 84, KS 83, ID 73 (1 bill all session), SD 71;
  - MS: 64 and 21;
  - WA 54;
  - MN: 35 and 7;
  - OR 27.
- **KS lost `extras` and `other_titles` on all 781 bills on 2026-05-09,** and they never came
  back.
- **The JSONL vote log can merge two different roll calls:** VT H 740 #161 is missing from
  `vote_event_logs.jsonl`. It's a logs-workstream bug. How many states it hits is not measured.
- **MT publishes the same roll call up to 10 times** under different roll-call numbers. The log
  merging those is correct.
- **ME scraped 0 bills on 07-08.** ME and MO had brief partial scrapes (about a third of their
  bills gone for one scrape).
- **The 07-21 "chore: clear duplicate-accumulated" commit** also hit MO, MT, OH, PR and USA, not
  only CT and PA.
- **MI, OH and USA kept getting data commits until 10-29,** after the 09-30 pause. PR got them
  until 10-01.

**Failures and skips:**

- **No crashes.**
- **Four known-number checks failed on the first run.** All are explained in step 4:
  - MT duplicates;
  - the VT log bug;
  - USA bill-name spelling, a scanner gap left in place;
  - PR has no data repo on the SSD.
- **Two scanner gaps are deliberately not fixed under the freeze:** USA vote-to-bill matching
  and AZ's "emptied" double-count.
- **Answer-key additions after the freeze:**
  - 10 third-wave events from `notes-by-state.md` (step 4);
  - WV's freeze from the recovery summary (step 5).

**Decisions waiting for you:**

1. **Confirm the unrecorded freezes, KS's field loss and the 07-21 chore commits** as known
   events, with you as the source.
2. **The step 5 change list:**
   - fleet-aware `no_scrape`;
   - skip maintenance commits;
   - the two scanner fixes;
   - a two-scrape `bill_drop`;
   - profiles that exclude confirmed freezes.

   OK to make these after review? It means re-scoring both samples, and the held-out score is
   then no longer blind.
3. **The design doc's six open decisions** (section 7): where it runs and posts, long
   `unchanged` limits, special sessions, `no_new_bills`, caveated losses, and recomputing the
   2027 profiles.
4. **Still open from before:** the TN doubled-actions fix.
5. **When to commit the branch** (`history-scanner`, all uncommitted).

### 2026-11-26: review of the overnight work (reviewing chat): approved, with two corrections

The overnight rules were kept: nothing was committed or pushed, the settings were frozen before
any third-wave scan, the answer key only grew (with sources), and both scores are shown where an
addition changed one. Running AL twice for idempotency was a good extra.

**Re-checked independently:**
- **ID:** 1 bill (`2026`) in every scrape from 01-24 to 04-10 and beyond, then 817 at the end.
  Confirmed: ID's whole 2026 session was invisible.
- **VT H 740:** the vote log holds #157 to #160 for 05-19 and no #161, and the raw scrape has
  both #157 and #161.

**Correction 1: VT #161 is "can't tell", not "a real loss".**
- In the raw scrape, #157 and #161 are the same in **everything but the roll-call number**: date,
  motion, result, counts 17–13, and all 30 voters with the same votes.
- That's the same shape as MT's copies, which this entry calls true duplicates. The data alone
  can't tell one from the other.
- VT's site can: open `loadBillRollCallDetails/2026/161`, and if it's a separate question (a
  different amendment called by the same senator), it's a loss.
- **The mechanism, for the logs workstream:** `_find_vote` and `_same_vote` in
  `actions/format/utils/log_jsonl.py` treat two votes as one when the identifier keys match
  **or** the fallback keys (date, motion, chamber, counts) match. So two votes with different
  identifiers merge whenever the fallback matches.
  - Using the fallback only when a vote has no identifier would keep VT's #161, but it would also
    split MT's 10 copies.
  - So this is a per-state rule, and it needs MT's and VT's sites checked first.
  - Low priority: VT is 1 vote. MT is the case to understand.

**Correction 2: MI, OH and USA committing until 10-29 isn't a finding.** They were among the 9
states left running at the 09-30 pause (dc gu mi mp nj oh pa usa vi). Their data stops on 10-29
because the Python 3.9 failure started on 10-30. PR's commits until 10-01 aren't explained by
that, and are worth one look.

**The held-out result is the most useful thing in this analysis.**
- The checks caught every known failure they can see on 29 states they were never tuned on,
  within 6 days (`unchanged` worst 9).
- Most of the "unexplained" alarms turned out to be **real failures nobody had written down**:
  13 session freezes, KS's field loss and ME's empty scrape.
- Record the blind numbers in the design doc as the baseline before any change.

**On the decisions waiting for Tamara** (recommendations; she has said she'll go with them):

1. **Confirm the unrecorded freezes, KS's field loss and the 07-21 chore commits:** yes.
   - Each is a measured fact (zero new bills, actions or votes for weeks, in session), and ID's is
     re-checked above.
   - Source: "history scanner, confirmed by Tamara 2026-11-26".
2. **The step 5 change list: yes, all of it**, after the blind baseline is in the design doc.
   - Re-score both samples, and label the new scores "after tuning".
   - The held-out score can't be blind twice. The first number is the honest one, and it's
     recorded.
3. **The design doc's open decisions:**
   1. **Where it runs: GitHub-hosted Actions, not the home laptop.** The auditor has to work when
      the laptop is off, and it only reads git history.
      - **Output:** one rolling GitHub issue in `chihacknight/govbot`, rewritten each run (alarms
        by state, with evidence links), so nothing piles up.
      - A page can come later.
   2. **Long `unchanged` limits:** cap them in session, starting at 10 days, and let the replay
      show the alarm cost. WI's 22 and MN's 17 were learned from quiet runs that were themselves
      probably freezes.
   3. **Special sessions:** yes, add them. FL (04-25 to 07-24) and GA (06-20) both lost their
      regular session when a special one started.
   4. **`no_new_bills`:** drop it for 2027. Gathering deadlines for 56 states is a project of its
      own, and `unchanged` plus `bill_drop` cover most of what it would catch.
   5. **Caveated losses (FL's House committee votes):** no alarm. Add one line per run to the
      report with the block rate and its trend, per FL's rule "direction, not presence".
   6. **The 2027 profiles:** run on the frozen 2026 settings plus the fleet fallback from day
      one, and recompute after the first 2–3 weeks of each session.
4. **TN's doubled actions:** still open, after the analysis.
5. **Committing:** recommended now. A night's work is uncommitted on one disk.
   - One PR from `history-scanner`: the scanner code, the plan doc, the design doc, `fl.md` and
     the README.
   - Leave out `home-runner-setup.md`, which is in #314.
   - The SSD outputs (database, profiles, reports) stay on the SSD as derived data.

**Next, after Tamara's OK:** add the blind baseline to the design doc, make the step 5 changes,
re-score, confirm the new known events, then commit and open the PR. Stop for review after.

### 2026-11-26: after tuning (Tamara's decisions applied)

**First, the blind baseline.** The held-out numbers were written into the design doc
(section 6, "Blind held-out baseline") before any change below. Everything after this point is
labelled "after tuning" and isn't blind.

**The review's corrections, taken:**

- **VT H 740 #161 is "can't tell", not a loss.** It matches #157 in everything but the
  roll-call number, the same shape as MT's copies. VT's site decides it.
- **MI, OH and USA committing until 10-29** isn't a finding.
- **PR's commits until 10-01, one look:**
  - the pause's template commit landed 09-29 20:22 CDT (09-30 01:22 UTC);
  - PR's scheduled runs on 09-30 and 10-01 still ran;
  - a second template commit on 10-02 00:04 UTC stopped it.

  So the pause took two template pushes to stop PR.

**The step 5 changes. All are made; each has an offline test (28 tests, all OK):**

1. **Hand commits are not scrapes.** `daily.is_scrape` is an allowlist of the subjects a scrape
   writes: "Scrape data", "Auto-save in-progress scrape", "Auto-merge: kept scraped data", and
   "Merge branch". It was measured over every data commit in the 56 raw repos.
   - It leaves out 9 commits:
     - the 7 "chore: clear duplicate-accumulated" commits on 07-21;
     - "Delete _data/sd directory";
     - NH's "fix: restore … wiped".
   - Every check, the profiles and the fleet commit list skip them. The scanner still records
     them.
2. **`no_scrape` waits during a fleet outage.** Measured, not real-time, the first idea (stay
   quiet on fleet-alarm days) wouldn't have worked: a fleet alarm fires only on the 1–4 days
   when states cross the 2-day line, and the July per-state alarms come after that. So the rule
   is:
   - if a state's silence began inside a fleet alarm that names it, its own alarm waits until
     the silence passes 14 days.
3. **`bill_drop` needs the bills to be still gone in the next scrape** (at most a quarter back).
   It fires on the second scrape's day.
4. **Scanner, vote fixes:**
   - **A vote is matched to its bill by a normalized identifier,** without case, spaces or
     punctuation, when the exact name isn't in the scrape and the normalized one points to one
     bill only. USA now attaches all 852 votes, exactly the logs' count, so the step 4
     explanation is gone from `check_known.py`.
   - **VA's 49 unattached votes are real:** they're on bills that aren't in the scrape
     (HR2069 …), not another spelling.
   - **A vote is "empty" or "emptied" only when every copy in the scrape is.** AZ's emptied
     scrapes went from 120 to 0.
5. **`unchanged` is capped at 10 days in session** (decision 3.2).
6. **The profiles leave out the confirmed freezes.** They are known events now, so the days
   are unhealthy.

**Re-scanned:**

- **For the vote fixes:** USA, FL, MI, TN, VA, AZ, DE and HI.
- **So their tables match the code** (their `emptied` counts were already 0): AK, CO, MN, MO,
  NE, SC and WI. They are the other states with empty votes.
- The `before-tuning/` folder holds the old profiles and replays.
- Known-number checks on all 56: **156 ok, 0 fail.**
- The after-tuning held-out replay, run twice, gave a byte-identical report.

**Known events confirmed by Tamara.** Source: "history scanner, confirmed by Tamara
2026-11-26". 19 were added:

- **13 `unchanged` freezes.** Each window runs from the day after the last scrape with anything
  new to the day before the next one:

  | State | Freeze |
  |---|---|
  | WI | 11-27 → 05-13, 05-15 → 07-14, 07-16 → 08-19 |
  | MD | 01-14 → 07-14 |
  | KS | 11-27 → 05-08 |
  | ID | 01-14 → 07-14 |
  | SD | 12-31 → 07-01 |
  | MS | 01-08 → 02-03, 02-05 → 07-14 |
  | WA | 11-27 → 04-21 |
  | MN | 11-27 → 03-11, 03-29 → 07-14 |
  | OR | 01-31 → 07-14 |

  Most end at the 07-14 recovery (self-hosted runners), so they were part of the December 2025
  freeze. The recovery summary missed them.
- **KS's `field_loss`** on 05-09.
- **The 07-21 chore commits** in MO, MT, OH, PR and USA, as for CT and PA. With change 1 these
  no longer matter, but they're kept for the record.
- **Not added:**
  - ME's empty scrape on 07-08: the decision didn't name it, and it stays unmatched;
  - the in-sample suspected freezes (MP, NC, NJ, HI, LA).

**Scores:**

- **Reports:**
  - `replay-after-tuning-insample.md`: 82 caught, 11 missed, 26 unmatched;
  - `replay-after-tuning-heldout.md`: 54 caught, 12 missed, 16 unmatched.
- **The before/after table is in the design doc,** section 6.
- **`no_scrape` alone** is slower (median 13). It waits while the fleet check has the outage.
- **Both no-scrape checks together** catch every known gap: median 1, worst 6 (it was 2 and 6).
- **The 10-day `unchanged` cap's cost:**
  - **in-sample, 4 → 15 unmatched:**
    - MP 8, NJ 2, NC 2, CA, DE and GU;
    - worst catch 12 → 9.
  - **held-out, 7 short alarms:** MI, NY and USA all 07-31 → 08-08 (an August recess?), plus
    MN, OK and WI ×2.
- **The held-out catch count rose (39 → 54) only because confirmed failures joined the key.**
  That isn't evidence the checks improved.
- **Still unmatched and worth a look:**
  - HI's 389 roll calls emptied on 09-17 (in-sample);
  - DE's versions on 07-15;
  - IA's 54 actions moved from "legislature" to "upper" on 08-09;
  - MO's 06-17 drop, which now persists for two scrapes.

**The design doc is updated:**

- section 7 records Tamara's decisions:
  - GitHub-hosted Actions with one rolling issue;
  - the `unchanged` cap of 10;
  - special sessions added when the auditor is built;
  - `no_new_bills` dropped for 2027;
  - FL's block rate as a report line, not an alarm;
  - the 2027 profiles start from these;
- the checks table and the starting-values table show the tuned rules and the 56 states'
  values.

**Next:** the PR (below). Then stop for review. TN's doubled-actions fix is still open.
