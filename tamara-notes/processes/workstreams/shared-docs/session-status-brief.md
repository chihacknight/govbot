# Session status: a new process that runs before the state auditor

Brief for the chat that builds it. Written 2026-11-26 by the reviewing chat, from a discussion
with Tamara.

> **The goal now: re-audit the 2026 history with session status added.** Go back through the
> history as the scanner did, but read every quiet stretch against two things: was the scraper
> on (GitHub run history), and was the legislature in session (`sessions.csv`). Find each
> state's patterns from that. Those patterns are what the live system gets built from later.
>
> **Later, the live system:** know, for every state on every day, whether its legislature is in
> session, and use that to tell a normal quiet stretch from a broken scraper. The state auditor
> (`state-auditor-design.md`) will read this process's output; it doesn't work out session
> status itself. Don't build the live pieces yet (see "Later").

## Ground rules

- **The scrapers stay paused.** This process never turns a scraper on or off. It recommends;
  Tamara decides.
- **Start fresh.** Don't build on `check-sessions.yml`, `close-session.yml`, the
  `openstates-scrape-paused` template or the session fields in `chn-openstates-scrape.yml`.
  They were never really used. Retiring them is a later PR, Tamara's call.
- **Only documented public sources:** the MultiState PDF, the congress.gov API, and PDFs Tamara
  downloads. LegiScan's site returns 403 to us; don't work around it. No search-engine scraping.
  Check MultiState's terms of use before any automatic fetch.
- **Per-state settings, not one rule for all.**
- Commit or push only when Tamara says so. The repo squash-merges: after a PR merges, start a
  fresh branch off `main`.
- Big files and scratch go on the SSD, `/Volumes/govbot-data/scratch/`. Read-only:
  `raw-scrapers/`, `govbot_data/full/`, `govbot-archive/`.

## Why

In 2026 Tamara turned scrapers off and on by hand: when a state was out of session (mostly in
the last few months) or when a scraper wasn't working. She did this as a volunteer next to a
full-time job and couldn't watch closely, so almost none of it was written down. The history
scanner then found long quiet stretches it couldn't explain. Some were real failures (ID had 1
bill all session). Others were normal: WI's 147 quiet days were mostly after it adjourned on
03-19, though it also held two special sessions (04-14 to 05-14 and 05-11 to 05-13) inside that
stretch.

## Decisions (Tamara, 2026-11-26)

1. **Data first.** Scraping stays on by default. Out of session isn't a reason to turn a scraper
   off; data can still arrive.
2. **When a state has had no new data for N days, check session status:**
   - either source says in session → **alarm**;
   - every source says out → **note it, no alarm**;
   - the sources disagree → **flag it** (say which says what).
3. **Session status never hides a failure.** A failed run or broken data alarms in session or
   out. Status only decides what "no new data" means.
4. **Generous windows.** Veto sessions and lame-duck returns count as in session. We don't know
   exactly how fast actions reach our data, so give more days than needed.
5. **Keep scraping after adjournment as long as data keeps coming.**
6. **Prefiling counts:** scrape and check before a session convenes when the calendar says
   prefiling is open.
7. **Before recommending a scraper be turned off, run final checks:** see "Later" below.

## What already exists

All in the `history-scanner` worktree (`govbot-bill-skip`), uncommitted:

- **`tamara-notes/session-dates/sessions.csv`:** 260 rows, one per session or dated event.
  Columns: `code, state, year, session, type, convenes, adjourns, convenes_estimated,
  adjourns_estimated, source, source_updated, notes`. Types: `regular`, `special`, `veto`,
  `reconvene`, `organizational`, `informal`, `recess`, `none` (no regular session that year).
- **`tamara-notes/session-dates/build_sessions_csv.py`:** builds it. Needs poppler. It reads:
  - LegiScan PDFs: `7-8-2026_`, `8-20-2026_`, `10-13-2026_Session_Calendar.pdf`,
    `11-23-2026_2027_Session_Calendar.pdf`. Red dates are estimates; the script reads the
    colour. LegiScan drops a special once it's over, so every version is kept.
  - MultiState PDFs, `multi-state/multistate-2025-…` and `…-2026-legislative-session-dates.pdf`.
    Page 2 has specials, veto sessions, lame ducks and recesses with dates.
  - `MANUAL` rows in the script: the territories, Alaska's specials, Congress past 10-30.
    Hand rows win over the PDFs.
- **The two sources disagree on 11 states' 2026 dates.** Most differ by a day or two. The big
  ones: NC (LegiScan Aug 31, MultiState Dec 18 with the lame duck), NJ (2028 term vs Dec 17), IA
  (Apr 21 vs May 3), ME (Apr 15 vs Apr 29). Each source has specials the other lacks (LegiScan:
  ND 09-02, SC 05-15).
- **Not covered by either:** DC, Congress, PR, GU, MP, VI. FL's spring and summer specials are
  in neither (OpenStates lists FL 2026 D/E/F).
- **Lag measurement:** `/Volumes/govbot-data/scratch/claude-review/lag/` (`lag.py`, `lag.txt`).
  Days from an action's date to `first_seen`, for actions dated 07-22 to 09-29 only (earlier
  `first_seen` values in unbackfilled repos are the 07-21 rebuild, not a real scrape). Median 1–2
  days in most of the 25 states with data. IL 6, MA 5, MD 6, DE 5, NC 10, MP 16, PA 30. Long
  tails are partly our own outages.
- **Run history:** each raw repo's Actions runs say whether the scraper ran each day:
  `gh api repos/govbot-openstates-scrapers/<st>-legislation/actions/runs`. It goes back to
  2026-01-07 (checked on TN and WI). No run means off; a failed run means it broke.

## What to reuse from the overnight scan, and what to redo

- **Keep the scan database,** `/Volumes/govbot-data/scratch/history-analysis/history.sqlite`.
  It records what each scrape held (bill counts, fields, votes, sessions in the scrape, bad
  files). That's a record of the git history, and it doesn't change. Re-scanning took hours and
  would give the same numbers. **First, spot-check it:** pick 3 states and compare a few scrapes'
  bill counts with the raw repos, and check that every state's scan reached its last commit.
- **Keep the scanner code** (`actions/openstates-scrape-audits/history/`) where it helps.
- **Known failures (`known_events.py`, corrected 2026-11-26):** 51 events come from Tamara's notes,
  past fixes and the raw git log; score against those. 14 were added from the overnight scan
  (13 freezes and KS's field loss), labelled "confirmed by Tamara". That label is wrong: Tamara
  took that back the same day. Relabel them "history scanner, unconfirmed (re-audit)", report
  them separately, and let step 5 sort them. (This brief first said "17"; that was the held-out
  sample's count, not the file's.)
- **Redo everything built on top:** the per-state profiles and limits, the replays and alarm
  counts, and the list of ~15 "unrecorded failures". They assumed things we now know were wrong:
  - the full-time states (CA, IL, MA, NY, WI and more) were treated as in session all year;
  - the calendar had no specials, veto sessions or lame ducks, and nothing before 2026;
  - with no run history, Tamara's pauses looked like quiet stretches, and some were learned as
    "healthy" limits.
- **The blind test can't be repeated cleanly.** Every state's results have been seen now. Report
  the new numbers as "how the rules fit 2026", not as a blind score. The real test is 2027:
  freeze the settings in January and check them against what happens.

## Sources and how each is refreshed

| Source | Covers | How |
|---|---|---|
| MultiState PDF | 50 states: regular sessions, specials, veto, lame duck, recess | **Automatic, weekly.** The page `multistate.us/resources/<year>-legislative-session-dates` links the PDF (S3). Find the link on the page each time; don't hard-code it. Keep every version. |
| congress.gov API | Congress | **Automatic.** `/v3/congress/<n>` gives each session's start and end (an open session has no end). Needs a free api.data.gov key as a repo secret. |
| LegiScan PDF | 50 states + DC | **Tamara downloads it** now and then. |
| Legislature sites | DC, PR, GU, MP, VI | **Tamara checks the site** once or twice a year; the process reminds her. |

**Check first:** PR. Our notes say its session "ends June 30 by law", but PR may also have a
second regular session from August to November. Check senado.pr.gov / camara.pr.gov and fix the
`MANUAL` row.

## The steps: the re-audit

1. **Check the scan database** (see "What to reuse"): 3 states spot-checked, every scan complete.
2. **Check `sessions.csv`.** Spot-check 10 rows against the PDFs. Fix PR. Add Congress from the
   API. Add the 2025 LegiScan calendar if Tamara can download it.
3. **Daily status.** One function: (state, date) → status, using every source, plus which
   sources agree. Statuses: `in_session`, `special`, `veto_or_lame_duck`, `prefiling`,
   `out_of_session`, `no_regular_session`, `unknown` (no source covers that day), and a
   `disagree` flag. Organizational days, informal sessions and recesses don't count as in
   session. Offline tests with small fixture CSVs.
4. **Pull run history** for all 56 raw repos (`gh api …/actions/runs`, read-only, to the SSD):
   for each state and day, whether the scraper ran, failed or was off.
5. **Sort every quiet stretch.** For each stretch with no new data, combine run history and
   session status:
   - scraper off;
   - ran and failed;
   - ran, nothing new, out of session (normal);
   - ran, nothing new, in session (the real question).

   This replaces asking Tamara about each gap. Before 2026-01-07 there's no run history; list
   those stretches for her.
6. **Measure each state's patterns:**
   - **the tail after adjournment:** how many days new actions keep arriving after the session
     ends (governors' signings and vetoes). Use the raw history or the scan database, not
     `first_seen` from before 07-21;
   - **lag:** days from an action's date to the scrape that first had it, over the full raw
     history (redo `lag.py` that way);
   - **how each state breaks:** which kinds of failure it has had, and how often.
7. **Rebuild the profiles and replays** with session status and run history: per-state limits
   learned only from stretches where the scraper ran and the state was in session. Then re-score
   against the known failures, labelled "fit to 2026".
8. **Write it up** in this doc: the patterns per state, what the re-audit found, and the real
   in-session failures for Tamara to confirm.
9. **Stop for review.**

## Later, after the re-audit (don't build yet)

- **The MultiState fetcher** (after the terms check): find the PDF on the page, download it,
  keep it if new, rebuild the CSV, report the changed rows. Fail-soft: a failed fetch keeps the
  last good copy and says so.
- **Final checks before recommending a scraper be turned off:**
  - the session has ended in every source;
  - the last actions in the data line up with the end of session;
  - no new data for longer than that state's measured tail, plus a margin;
  - the scraper's last runs succeeded (a scraper failing at the end can't prove it's done).

  Output a recommendation with the evidence. Never act on it.
- **Reminders:** a LegiScan PDF older than 30 days during January–June; a site check due for
  DC or a territory; a MultiState fetch failing for over a week.
- **Running daily** before the auditor, on GitHub-hosted Actions.

## Output

**Of the re-audit:**
- `sessions.csv`: the calendar, hand-correctable.
- The sorted quiet stretches and the per-state patterns as tables in the scan database, plus a
  CSV of each (Tamara reads them in DBeaver).
- The write-up in this doc (step 8).

**Of the live system, later:** a status file per run (state, date, status, the sources'
answers, `disagree`) for the auditor to read. Turn-off recommendations and reminders go in the
auditor's one rolling GitHub issue (design section 7), not their own.

## Where the code goes

Suggested: `actions/openstates-scrape-audits/sessions/`, next to `history/`. The CSV and PDFs
stay in `tamara-notes/session-dates/` until Tamara says otherwise.

## Open questions (Tamara's)

- How long N is ("no new data for N days") per state. Start from the lag numbers and the
  scanner's profiles; re-measure in spring 2027.
- Whether a state that gets blocked for scraping too often (like PA) drops to weekly out of
  session instead of daily.
- When to retire the old session workflows.

## Progress

(The building chat adds dated entries here.)

### 2026-11-26: steps 1 and 2

**Step 1, scan database: checked, keep it.**
- Every state's scan reached its raw repo's last commit under `_data/<st>/` (56/56: the
  scan's last row is that commit, the scrape count equals `git rev-list --count`, rows are
  contiguous). `runs.raw_head` differs from it for most states only because later commits
  don't touch `_data/` (pause-era workflow commits). The SSD clones match GitHub's HEAD (56/56).
- Spot-check, WI, TN and KY, 4 scrapes each (first, ⅓, ⅔, last), recounted straight from git:
  bill files, distinct bills and bills per session all match (12/12). Script:
  `/Volumes/govbot-data/scratch/session-status/spotcheck.py`.

**Step 2, `sessions.csv`: 260 → 264 rows.**
- Builder re-run first: it reproduces the CSV byte for byte.
- 10 rows checked against the PDFs (WI/ID/TX/ND/RI 2027, 2026 and 2025 regular rows, NH veto
  day, AK 3rd special, CO 2025 and VA 2026 specials): all match, red "estimated" flags included.
- **PR fixed, partly.** PR does have a second ordinary session, Aug–Nov: senado.pr.gov (read
  today) says the Senate closed the 4th ordinary session of the 20th Assembly on **2026-11-17**.
  PR's own data agrees (243 new bills in Aug, 204 in Sep, after 48 in Jul). The start date
  isn't on a page I could read (camara.pr.gov and the Ley 9-1954 PDF didn't load), so
  2026-08-17 (third Monday of August, from the rule) is marked estimated. Added the 2025
  equivalent (08-18 to 11-18) too, both ends estimated. **To check:** the law or camara.pr.gov.
- **Congress added from the API** (`congress/congress-119.json`, read with `DEMO_KEY`, no
  secret needed for a one-off): session 1 2025-01-03 to 2026-01-03, session 2 from 2026-01-03,
  still open (empty `adjourns`, notes "open"). The builder reads every `congress/*.json`.
- **Not done: the 2025 LegiScan calendar.** LegiScan answers 403 to us, so it needs you to
  download it. Until then 2025 has only MultiState (70 rows).
- Seen for step 3: MultiState gives WI 2025 as 01-06 to 12-31 and 2026 from 01-13, so a
  two-year legislature reads "out" for a few days around New Year. Step 3 treats a biennium's
  gap between its two years as in session.

### 2026-11-26: steps 3 and 4 done, step 5 first pass, then stopped (a mismatch)

**Step 3, daily status: `actions/openstates-scrape-audits/sessions/status.py`.**
`status(cal, state, day)` → status, each source's answer (legiscan / multistate / congress /
manual), `disagree`, `estimated`. 12 offline tests on a fixture CSV (`python3 test_status.py`).
Rules, each written in the module's docstring:
- any source saying in → that status (special > veto/lame duck > in session > prefiling);
- a source only says "out" for a state-year when it has a regular or "none" row for that year,
  so AK's hand rows (specials only) don't contradict its regular session;
- organizational and informal days don't count; a recess takes days out of a regular session;
- a row with no end date gets 30 days, estimated (LegiScan's MD 08-03, ND 09-02 and SC 05-15
  specials, MultiState's AR 2026 row); congress.gov's open session runs on;
- prefiling: LegiScan's "Prefiling" note → from the PDF's date until the session convenes;
- a biennium split across two rows (WI in MultiState) stays in session across New Year.
- Also added **PR 2025 Jan–Jun** (rule-based, estimated): without it the new 2025 Aug–Nov
  row made Jan–Jun 2025 read "out".
- DC is in LegiScan for 2026 and 2027 (the brief says no source covers it); only 2025 is
  unknown, for lack of the 2025 LegiScan PDF.

**Step 4, run history: done.** All 56 repos, 14,878 runs (`gh api …/actions/runs`, read-only)
in `/Volumes/govbot-data/scratch/session-status/runs/<st>.jsonl`. Every repo starts
2026-01-07. One workflow (`openstates-scrape.yml`, scheduled plus 341 manual). Outcomes: 12,263
success, 2,281 failure, 331 cancelled, 1 startup failure. Every day since 01-07 that has a scrape
commit also has a run on record. On 26 of those days no run succeeded, but the failed or cancelled
runs still committed partial data (FL and MA auto-saves, July and August). So "failed" and "brought
new data" are kept separate. NJ, USA, DC, MI, OH, PA, VI, GU and MP kept running past 09-29. Their
data stops at 10-29, which fits the Python 3.9 outage.

**Step 5, first pass: `sessions/reaudit.py`.** It adds `run_days`, `status_days`, `days`,
`quiet_segments` and `quiet_stretches` to `history.sqlite`, rebuilt on each run, and writes CSVs
to `/Volumes/govbot-data/scratch/session-status/csv/`. Before the first run the database was
copied to `session-status/history.before-reaudit.sqlite`. Days through 2026-11-25:
- **new data:** 2,078 days;
- **ran, nothing new, out of session:** 5,663;
- **ran, nothing new, in session:** 4,495;
- **off:** 3,516;
- **failed:** 2,534;
- **before run history:** 2,078 (444 in session, 1,621 out, 13 unknown; the same total
  as the new-data days is a coincidence).

WI shows the method works: identical content from 11-27 to 05-13 through green runs, across its
whole floor period.

Of the 114 in-session quiet segments of 7 days or more:
- 49 fall inside an event taken from your notes;
- 15 fall only inside an event the overnight scan found;
- 50 fall inside no event.

The 50 unexplained segments:
- **Territories:** GU, MP and VI are "year-round" in the hand rows, so every quiet stretch reads
  "in session". Their calendar is too broad to judge by.
- **A shared 07-22 to 08-08 window** in MI, OH, USA, NC and PA. It looks fleet-wide, perhaps
  after the 07-21 rebuild, and needs a look.
- **Single states worth a look:** HI 01-22 to 03-23 (61 days), LA 03-17 to 05-11 (56 days), PA
  07-22 to 09-20 (61 days), NJ 07-06 to 08-08 (34 days), DE in February.
- **One source only:** the MD 08-03 and AK 4th specials, where the other source says out.

**Stopped here: `known_events.py` doesn't match the brief.** The brief says to keep "the 17
known failures… Nothing from the overnight run was added to them." The committed file (42dec748)
has 65 events: 51 from notes and earlier reviews, and 14 marked "history scanner, confirmed by
Tamara 2026-11-26" (WI ×3, MD, KS freeze + field loss, ID, SD, MS ×2, WA, MN ×2, OR). Steps 5–7
score against this list. Scoring against events the scanner itself found is partly circular.
**Question for Tamara:** score step 7 against all 65, or against the notes-only 51, with the 14
reported separately?

### 2026-11-26: the 2025 LegiScan calendars, and the relabel

**Relabel (not committed, waiting for your OK).** The 14 overnight events in
`history/known_events.py` now read "history scanner, unconfirmed (re-audit)", not "confirmed by
Tamara 2026-11-26", and the comment above them says they're unconfirmed. The 07-21 maintenance
entries ("raw git log; confirmed by Tamara") are unchanged. Step 7 scores only the other 51; the 14
are reported apart.

**2025 LegiScan calendars added** (01-24-2025, 08-15-2025, 09-03-2025, copied from the main
checkout's `session-dates/2025 legiscan/`). The newest (09-03) gives each state's regular row;
specials are kept from all three. `sessions.csv`: 266 → 323 rows.
- **Added 51 regular 2025 rows,** one per state plus DC and Congress.
- **Added 6 dated specials:** CO 08-21, DE 08-12, FL 01-27, MO 09-03, OR 08-29, SD 09-25.
- **Removed: the hand-kept DC 2025 row.** LegiScan now gives the 26th Council from 2025-01-02.
- **No 2026 or 2027 row changed** (checked by diff).
- **Builder changes:**
  - A note is split on ";", so FL's "Prefiling; Special Session January 27th" keeps "Prefiling"
    on the regular row and makes one special row.
  - "Special Session TBD" parts (CT, LA, MN, NM, VA, WV) are skipped, not turned into undated rows.
- **Two status rules, because of these rows** (`status.py`, with tests):
  - **Within one source, a regular row ends where the same state's next regular row begins.**
    LegiScan's 2025 rows run biennia into 2026 or 2027 (WI and MI to 2026-12-31, MA and NY into
    2027, CA to 2026-09-12). Without the cut, LegiScan would call WI in session all of 2026,
    though its 2026 PDF says 01-13 to 03-19.
  - **"Interim Recess <date>"** in a regular row's notes (IL May 31, NY June 17, both 2025) is a
    recess from that date to the row's end. So IL's 2025 veto session now reads in session from
    MultiState and out from LegiScan: flagged as a disagreement.
- **The replay's results are unchanged:** every 2025 day falls before run history. No pre-January
  day has unknown status any more (DC had 13).


### 2026-11-26: steps 5–8 done, write-up (step 8). Stopping for review (step 9).

#### Where everything is

- **Code** (new, not committed): `actions/openstates-scrape-audits/sessions/`:
  - `status.py`: the daily status function;
  - `reaudit.py`: the day tables and the quiet stretches (steps 4–5);
  - `action_dates.py`: when each action first reached the raw history;
  - `patterns.py`: step 6;
  - `rescore.py`: step 7;
  - `candidates.py`: the unconfirmed events this re-audit found;
  - tests: `test_status.py` and `test_reaudit.py`, both pass.
- **Tables** added to `history.sqlite`, each rebuilt on every run: `run_days`, `status_days`,
  `days`, `quiet_segments`, `quiet_stretches`, `action_seen`, `state_patterns`, `session_tails`,
  `rescore_settings`, `rescore_alarms`. Nothing in the scan's own tables was changed. A copy from
  before the first run: `session-status/history.before-reaudit.sqlite`.
- **CSVs for DBeaver,** in `/Volumes/govbot-data/scratch/session-status/csv/`: `days`,
  `quiet_segments`, `quiet_stretches`, `state_patterns`, `session_tails`.
- **The replay report:** `session-status/rescore.md`, one profile per state in `session-status/profiles/`.

#### Step 5: how every day sorts

Days from each state's first scrape to 2026-11-25:

| Kind | Days |
|---|---|
| ran, nothing new, out of session | 5,663 |
| ran, nothing new, in session | 3,870 |
| scraper off | 3,516 |
| ran and failed | 2,534 |
| brought new data | 2,078 |
| territory (GU, MP, VI), ran, nothing new | 625 |
| before run history (to 01-06) | 2,078 (388 in session, 1,572 out, 118 territory) |

There are 88 quiet stretches of 7+ days with green runs while in session, 2,993 days in all.
- 49 fall inside an event from your notes, past fixes or the git log;
- 15 fall inside one of the 14 overnight events;
- 6 fall inside a candidate event (below);
- **18 fall inside nothing.** They are listed under "For you to confirm".

**Before 01-07 there's no run history.** 36 of 56 states brought nothing new from their first
scrape (11-26/27) to 01-06, about 40 days. Most were out of session. Every stretch is in
`quiet_segments` (kinds `no_record_*`).

**The 14 overnight events, sorted by their days:**
- **11 look like real in-session freezes:** green runs, in session, nothing new. WI 11-27 to
  05-13 (100 days in session), MD 01-14 (89), KS 11-27 (89), ID 01-14 (78), SD 12-31 (77), MS
  02-05 (70), WA 11-27 (60), MN 03-29 (39), OR 01-31 (33), MS 01-08 (24), MN 11-27 (15).
- **2 look normal:** WI 05-15 to 07-14 and WI 07-16 to 08-19 have no in-session day at all,
  only out-of-session days, off days and failed runs. By decision 2 they're a note, not a failure.
- **1 isn't a quiet stretch:** the KS field loss from 05-09. Step 5 can't sort it; the
  field-loss check catches it.

#### Fleet events this re-audit found (in `candidates.py`, not in `known_events.py`)

1. **The download cache, 07-22 to 08-08: 16 states.** About 55 runs a day were green, but only
   2 to 8 states a day brought anything new. On 08-09, the morning after govbot 37df675d (#112:
   the scrape action restored scrapelib's HTTP cache from any earlier run, and scrapelib never
   revalidates), 19 states brought new data at once. IA and ME brought over 10,000 actions
   each. The 07-21 rebuild had just filled the cache. The 16: AK, AZ, IA, IL, KS, LA, MD, ME, NC,
   NJ, NY, OH, USA, VA, VT and WY.
2. **NJ, the same cache, 01-30 to 08-08.** #112's own text says NJ "froze on a late-January
   2026 snapshot for ~7 months". The raw history agrees: new data on 01-29, then only votes on
   06-30, then 08-09.
3. **Zero-result scrapes committed as green, 06-26 to about 07-02.** On 06-26, d1bf2c24 ("treat
   zero-result scrape as soft failure when fallback data exists") landed. CT, HI, LA and NM went
   from a month of failed runs to green runs that committed empty scrapes. DC, MP and TX lost
   large shares of their bills that day. Your notes already list NH's and MA's empty scrapes from
   the same week. This one isn't in `candidates.py`: these alarms are true failures either way.
4. **Waves of failed runs:**
   - 01-07 to 05-25: AZ, DC and NM all 139 days; also TX, NH, CT, NJ, TN, VA, VI, HI and DE;
   - 05-27 to 06-25: the same group plus LA and MP;
   - 08-08 to 09-29: FL and MA, 53 days;
   - 10-30 onward: DC, GU, MI, MP, NJ, OH, PA, USA and VI, the Python 3.9 outage.

   These are why decision 3 ("a failed run alarms") gives 323 alarm episodes over the year.

#### Step 6: each state's patterns

- **Lag** (action date to the first scrape that had it): a wait counts only when every day of
  it had a green run and fell outside every event that holds back data.
  - Median 1 to 2 days in most of the 33 states where it can be measured. Slower: PA (5 / p90
    24), MP (9 / 20), NE (4 / 21), TN (10), DC (2 / 6), MI (p90 7).
  - 23 states have no clean wait at all: frozen, failing or off most of the year. Their lag
    has to be measured in 2027.
  - With catch-ups left in, the p90 is 100 to 480 days in many states. That is our outages, not
    the sources.
- **Tail after adjournment:** how long after a session's last in-session day (any source) the
  actions are dated, at the 90th percentile.
  - 8 to 70 days in most states: AL 8, TN 10, RI 13, WI 14, CA 26, IA 30, NH 36, MD 43, PR 44,
    MO 59, HI 67, IL 68, DE 70.
  - Longer: SC 73, MN 75, NY 103, FL 104, WV 107, NE 139. These probably include interim
    committee actions and effective dates, not only signings: a guess, not checked.
  - The day such actions last *arrived* is inflated by our own catch-ups (WI 175), so the
    dated tail is the one to use for "keep scraping after adjournment".
  - Full-time legislatures (PA, MI, OH, NJ, USA, DC) have no session end in 2026, so no tail.
    Per state and session: `session_tails`.
- **How each state breaks:** the table below, and `state_patterns.alarms_by_check`.

| State | Lag median / p90 (days) | Tail p90 (days) | Quiet limit | Failed-run days | Off days | Alarms (episodes) by check |
|---|---|---|---|---|---|---|
| ak | 1 / 4 | 36 | 7 | 6 | 59 | no new bills 1, quiet 4, failed run 2 |
| al | 1 / 1 | 8 | 7 | 35 | 76 | failed run 4 |
| ar | — | — | 7 | 14 | 59 | empty scrape 5, quiet 2, failed run 4 |
| az | — | 9 | 7 | 170 | 75 | failed run 3 |
| ca | 1 / 2 | 26 | 8 | 1 | 59 | no new bills 1, failed run 1 |
| co | 1 / 2 | 21 | 7 | 1 | 76 | failed run 1 |
| ct | — | 27 | 7 | 141 | 75 | empty scrape 1, failed run 3 |
| dc | 2 / 6 | — | 7 | 196 | 2 | bill drop 1, empty scrape 1, no new bills 1, failed run 3 |
| de | 1 / 1 | 70 | 10 | 72 | 76 | field loss 1, quiet 1, failed run 5 |
| fl | — | 104 | 7 | 144 | 73 | broken votes 2, failed run 25 |
| ga | 1 / 1 | 40 | 7 | 24 | 59 | empty scrape 1, failed run 19 |
| gu | — | — | 45 | 28 | 3 | quiet 4, failed run 4 |
| hi | 1 / 6 | 67 | 7 | 94 | 75 | broken votes 1, empty scrape 1, quiet 1, failed run 3 |
| ia | 1 / 1 | 30 | 7 | 0 | 59 | chamber swap 1 |
| id | 1 / 1 | — | 7 | 2 | 76 | quiet 2, failed run 2 |
| il | 1 / 2 | 68 | 7 | 11 | 68 | empty scrape 2, field loss 1, quiet 5, failed run 7 |
| in | — | 13 | 7 | 7 | 70 | quiet 1, failed run 3 |
| ks | — | — | 7 | 13 | 59 | field loss 1, quiet 2, failed run 2 |
| ky | — | 12 | 7 | 3 | 76 | field loss 1, quiet 2, failed run 3 |
| la | — | 22 | 7 | 48 | 75 | empty scrape 1, quiet 1, failed run 4 |
| ma | 0 / 1 | 6 | 7 | 134 | 59 | empty scrape 1, no new bills 35, failed run 41 |
| md | — | 43 | 7 | 8 | 76 | quiet 3, failed run 3 |
| me | 1 / 1 | — | 10 | 2 | 59 | empty scrape 1, quiet 1, failed run 2 |
| mi | 1 / 7 | — | 10 | 31 | 2 | quiet 5, failed run 2 |
| mn | — | 75 | 9 | 38 | 76 | quiet 10, failed run 25 |
| mo | 1 / 1 | 59 | 7 | 17 | 76 | bill drop 2, failed run 7 |
| mp | 9 / 20 | — | 21 | 56 | 3 | bill drop 1, no new bills 1, quiet 1, failed run 5 |
| ms | — | 13 | 7 | 6 | 76 | quiet 2, failed run 4 |
| mt | 1 / 2 | — | 7 | 5 | 76 | failed run 5 |
| nc | 1 / 1 | 96 | 10 | 7 | 70 | no new bills 2, quiet 6, failed run 3 |
| nd | 1 / 6 | — | 7 | 4 | 76 | broken votes 8, no new bills 1, quiet 2, failed run 4 |
| ne | 4 / 21 | 139 | 7 | 6 | 70 | quiet 1, failed run 2 |
| nh | 1 / 3 | 36 | 7 | 142 | 74 | empty scrape 2, field loss 4, failed run 4 |
| nj | 1 / 2 | — | 10 | 168 | 2 | empty scrape 1, no new bills 1, quiet 4, failed run 4 |
| nm | — | 33 | 7 | 173 | 69 | empty scrape 1, failed run 3 |
| nv | — | — | 7 | 7 | 70 | failed run 4 |
| ny | 1 / 1 | 103 | 7 | 8 | 59 | quiet 5, failed run 4 |
| oh | 1 / 1 | — | 7 | 43 | 2 | quiet 7, failed run 7 |
| ok | 1 / 1 | 15 | 10 | 6 | 76 | quiet 1, failed run 5 |
| or | — | 34 | 7 | 3 | 76 | quiet 1, failed run 3 |
| pa | 5 / 24 | — | 7 | 44 | 11 | quiet 15, failed run 13 |
| pr | 1 / 2 | 44 | 7 | 1 | 57 | failed run 1 |
| ri | 1 / 2 | 13 | 7 | 14 | 76 | failed run 9 |
| sc | 1 / 2 | 73 | 7 | 6 | 59 | quiet 2, failed run 2 |
| sd | — | — | 7 | 1 | 75 | quiet 1, failed run 1 |
| tn | 10 / 10 | 10 | 7 | 129 | 75 | bill drop 1, broken votes 4, chamber swap 2, field loss 1, failed run 4 |
| tx | — | — | 7 | 171 | 76 | bill drop 1, field loss 1, failed run 7 |
| usa | 2 / 3 | — | 7 | 38 | 2 | quiet 6, failed run 7 |
| ut | 0 / 1 | 16 | 9 | 11 | 76 | no new bills 1, failed run 5 |
| va | — | 2 | 7 | 90 | 158 | failed run 2 |
| vi | — | — | 45 | 118 | 98 | quiet 3, failed run 4 |
| vt | — | — | 7 | 9 | 59 | quiet 4, failed run 5 |
| wa | — | 18 | 7 | 16 | 76 | quiet 1, failed run 13 |
| wi | — | 14 | 7 | 12 | 76 | quiet 3, failed run 10 |
| wv | 1 / 1 | 107 | 7 | 8 | 69 | bill drop 1, quiet 2, failed run 5 |
| wy | — | — | 7 | 0 | 76 | quiet 1 |

The lag and tail columns are blank where they can't be measured. GU's bills carry no actions at
all, so it has no lag or tail.

#### Step 7: limits and the replay, "fit to 2026"

**Not a blind score.** Every state's 2026 has been seen; the real test is 2027, with the settings
frozen in January.

**Limits:** green in-session days with nothing new before the quiet alarm.
- **Learned from:** unexplained quiet runs only, where the scraper ran and the state was in
  session. A run of 21 days or less counts as normal; longer runs are reported as suspects.
  The limit is the longest normal run + 2, at least 7, at most 10 (your earlier cap).
- **The result:** 7 in most states, 8 to 10 in CA, DE, ME, MI, MN, NC, NJ, OK and UT.
- **HI and PA take the fleet median (7).** All of their unexplained runs are suspects: HI 61;
  PA 24 and 61.
- **Territories:** the 90th percentile of their own quiet runs + 7, at least 14, at most 45.
  GU and VI get 45, MP 21. This is the looser rule for "year-round".

**Scored** against the 40 events from your notes, past fixes and the git log that a check is
meant to catch (the other 11 are maintenance commits and FL caveats). **39 caught, 1 missed.**

| Check | Events | Caught | Median days to catch | Alarm episodes | Explained by a scored / overnight / candidate event | Unexplained |
|---|---|---|---|---|---|---|
| quiet | 16 | 15 | 6 | 112 | 58 / 23 / 7 | 24 |
| no new bills | 1 | 1 | 60 | 44 | 35 / 0 / 0 | 9 |
| empty scrape | 7 | 7 | 0 | 18 | 11 / 0 / 1 | 6 |
| field loss | 6 | 6 | 0 | 10 | 7 / 1 / 0 | 2 |
| broken votes | 9 | 9 | 0 | 15 | 12 / 0 / 0 | 3 |
| chamber swap | 1 | 1 | 0 | 3 | 2 / 0 / 1 | 0 |
| bill drop | 0 | — | — | 7 | 2 / 0 / 0 | 5 |
| failed run | — | — | — | 323 | 92 / 47 / 2 | 182 |

- **Days to catch** count from the first green in-session day after an event starts. For the Dec
  2025 freeze that is 01-07 (run history) or the session's start.
- **The miss is by design.** WA's 07-24 two-day freeze was out of session, and decision 2 makes
  that a note.
- **Most unexplained alarms are the fleet events above.** The empty scrapes and bill drops are
  the 06-26 week; the failed runs are the waves.
- **Notes, no alarm:** 431 quiet stretches out of session, and 192 scraper-off stretches (your
  pauses).

#### For you to confirm: likely real in-session failures

1. **HI, 01-21 to at least 03-23:** 3,520 bills byte-identical on 67 green runs, in session.
2. **LA, 03-17 to 05-11:** only 7 bills in the 2026 session, identical throughout.
3. **PA, 07-22 to 10-23:** frozen, then a catch-up on 10-24 (374 new bills, about 2,400
   actions, 5,800 votes). PA isn't in the 08-09 burst, so it's separate from the cache event.
4. **NJ:** the cache freeze, 01-30 to 08-08 (candidate 2), plus 7 to 12-day quiet runs in
   Aug–Sep after it.
5. **The 11 overnight freezes** listed above.
6. **The 3 fleet events** (cache, zero-result, failed-run waves).
7. **Shorter unexplained in-session runs:** DE 02-01 (9 days) and 02-13 (7); OK 02-06 (11); UT
   03-01 (7); MN 03-15 (7); MI 07-27 (13, just inside the cache window but not in its 08-09
   burst).
8. **Runs where the sources disagree:**
   - NC Aug–Sep: LegiScan says the session ended 08-31, MultiState runs to 12-18;
   - ME 04-16 to 04-29: LegiScan 04-15 vs MultiState 04-29;
   - MD from 08-10 and ND from 09-12: one-source specials with the 30-day default end.
9. **Territories:** GU 57, 38, 31 and 84-day quiet runs past its limit of 45; VI 24 to 30 days.
   Their bills come rarely, and GU's have no actions, so a broken GU scraper and a quiet GU
   legislature look the same. A site check would settle it.

#### Open questions

- Does decision 3 mean every failed day? That gives 323 episodes. Most belong to a few months-long
  waves where everything failed together. One fleet alarm per wave, or "failed on 2+ days in a
  row", would be far fewer. Your call.
- What should N be, the days with nothing new? The limits above are a starting point. The lag
  numbers say 7 days covers the normal wait in almost every state that can be measured; PA, MP
  and NE need more.
- The 30-day default for a special with no end date (MD, ND, SC; CO, DE, FL, MO, OR and SD in
  2025): keep it, or add the real end dates as hand rows?
- PR's start dates, from the rule: check them when camara.pr.gov loads.
- Commit: the relabel in `known_events.py`, the new `sessions/` folder, and the `session-dates/`
  changes (`build_sessions_csv.py`, `sessions.csv`, `congress/`, the 2025 PDFs). All waiting for
  your OK.

### 2026-11-26: `session-dates/` reorganized

- **PDFs moved to `sources/<legiscan|multistate>/<year covered>/<updated date>.pdf`:**
  - LegiScan 2025: `2025-01-24`, `2025-08-15`, `2025-09-03`;
  - LegiScan 2026: `2026-07-08`, `2026-08-20`, `2026-10-13`;
  - LegiScan 2027: `2026-11-23`;
  - MultiState: `2025/2025-12-31` and `2026/2026-11-26`, the "last updated" dates printed on
    each.
- **The two old notes moved to `old-notes/`:** `session-calendar-2026.md` and
  `session-dates-comparison.md`, each with a "Superseded by `../sessions.csv`" line on top.
  The empty `multi-state/` folder is gone. Tracked files were moved with `git mv` (the 7-8 and
  8-20 PDFs, both notes); the rest were untracked.
- **New `README.md`:** the layout, how to add a calendar, and who reads which file.
- **`build_sessions_csv.py` finds the PDFs by walking `sources/`.** The year comes from the
  folder, the updated date from the file name. A misnamed file stops the build with a message.
  The hard-coded `CALENDARS` / `MULTISTATE` lists are gone. MultiState now follows the same
  rule as LegiScan if a year ever has several versions: the newest gives the regular rows, and
  dated events are kept from every version. Today each year has one.
- **`sessions.csv` rebuilt: the same 323 rows, apart from the source paths** (checked as a set,
  with each old source mapped to its new path). Some rows changed position, because the sort
  breaks ties on the source. The `MANUAL` rows' sources now say `old-notes/session-calendar-2026.md`.
- **Second-order fixes, so nothing breaks when this merges:**
  - **Six scripts read `session-calendar-2026.md` by path:** `weekly-scraper-audit.py` (run by
    `weekly-scraper-audit.yml` and `daily-scraper-error-digest.yml`; it returns `{}` without
    complaint when the file is missing), `history/daily.py`, `internal/session_coverage_check.py`,
    `internal/audit_states.py`, `internal/audit_new_bill_flatline.py` and
    `internal/archive/weekly_scraper_audit.py`. All now point at `old-notes/`.
    `weekly-scraper-audit.py` and `daily.py` still parse all 56 states.
  - `docs/src/state-status-reference.md`'s GitHub link updated.
  - `sessions/status.py` tells sources apart by the new paths; its fixture was updated.
- **Checked:** tests pass. Re-running steps 5–7 gives identical daily status per source and an
  identical `rescore.md`.
- **Left alone:**
  - mentions of the old file names in other notes and in this doc's earlier entries (history);
  - `freeze.py`'s label "session-calendar-2026.md": changing it would change the frozen
    settings that the replay checks against.

### 2026 data completeness, later

Parked on 2026-11-26 (Tamara's review of steps 5–8: approved). Neither item below has been
tested. Pick them up with the "full text later" work.

#### The cache hypothesis

The scrape action's unbounded download cache existed since at least 2025-10-13 (`6e4346ce`,
"Reorganize actions into subdirectories", already has `cache-scrapes-` restore keys). It was
bounded to one UTC day only on 2026-08-08 (`37df675d`, #112). scrapelib never revalidates a cached
response, so the cache may explain the in-session freezes all year, not only 07-22 to 08-08 and NJ.

A hint: MD, ID, MS, MN and OR all end their freezes on 07-14, right after the 07-02 to 07-14
window when the scrapers were off. GitHub evicts a cache that goes unused for 7 days, so the first
run after that window would have started cold.

The run history agrees on the window: all five were off from 07-02 to 07-14, and their first run
after it, on 07-15, brought new data. **Another explanation to rule out:** several states were moved
to the self-hosted runner on 07-14 and 07-15 (MD and ID among them, per the state follow-up notes).
A different runner, or a changed workflow, could also have started without the old cache.

To test later: for each freeze, find when the state's cache key was first restored and when it was
evicted or replaced, and whether a freeze ends where a cold run starts.

#### For you to confirm (as written in step 8)


1. **HI, 01-21 to at least 03-23:** 3,520 bills byte-identical on 67 green runs, in session.
2. **LA, 03-17 to 05-11:** only 7 bills in the 2026 session, identical throughout.
3. **PA, 07-22 to 10-23:** frozen, then a catch-up on 10-24 (374 new bills, about 2,400
   actions, 5,800 votes). PA isn't in the 08-09 burst, so it's separate from the cache event.
4. **NJ:** the cache freeze, 01-30 to 08-08 (candidate 2), plus 7 to 12-day quiet runs in
   Aug–Sep after it.
5. **The 11 overnight freezes** listed above.
6. **The 3 fleet events** (cache, zero-result, failed-run waves).
7. **Shorter unexplained in-session runs:** DE 02-01 (9 days) and 02-13 (7); OK 02-06 (11); UT
   03-01 (7); MN 03-15 (7); MI 07-27 (13, just inside the cache window but not in its 08-09
   burst).
8. **Runs where the sources disagree:**
   - NC Aug–Sep: LegiScan says the session ended 08-31, MultiState runs to 12-18;
   - ME 04-16 to 04-29: LegiScan 04-15 vs MultiState 04-29;
   - MD from 08-10 and ND from 09-12: one-source specials with the 30-day default end.
9. **Territories:** GU 57, 38, 31 and 84-day quiet runs past its limit of 45; VI 24 to 30 days.
   Their bills come rarely, and GU's have no actions, so a broken GU scraper and a quiet GU
   legislature look the same. A site check would settle it.
10. **UT, 2026-01-19 to 07-15:** the scrape held the same 8 bills through UT's whole session
    (01-20 to 03-06); its 824 2026 bills (first actions from 01-21) arrived only on 07-15. Found
    by "no bills from a running session" (2026-11-26); the quiet rule missed it because those 8
    bills kept getting small new actions. Not in `known_events.py`.


### 2026-11-26: the three-list replay of 2026. Stopping for review.

Tamara's decisions (2026-11-26):
- **Failed runs:** 3 days in a row.
- **No new data:** two levels, 7 and 14 days.
- **A special with no end date:** Tamara checks the state's site.
- **Commit:** later, one commit to PR #315 after her OK. The relabel stays uncommitted until then.

**Code (new, not committed):**
- `sessions/lists.py`: the replay, with its rules in the docstring. Writes `list_items` and
  `list_weeks` to `history.sqlite`, a report to `session-status/lists.md`, and CSVs to
  `session-status/csv/list_items.csv` and `list_weeks.csv`.
- `sessions/deadlines.py`: the intro deadlines, written to `csv/intro_deadlines.csv`.
- Tests for both in `test_reaudit.py`. All tests pass.

**First: what the formatter does with a damaged scrape today** (`actions/format`):
- **Empty scrape: not passed on.** With no JSON files the format action exits with an error
  (`action.yml:77`). With only jurisdiction or organization files it runs, but has no bills to
  write, and nothing deletes a bill's folder.
- **Bill drop: not passed on.** A bill missing tonight keeps its folder and `metadata.json`.
- **Field loss: depends on the field.** The 9 guarded fields keep last night's value
  (`bill_guards.GUARDED_FIELDS`). Any other field goes into `metadata.json` the first night:
  `extras`, `other_identifiers`, `related_bills`, `classification`. In 2026 those were NH's and
  KS's extras and TX's other identifiers.
- **So:** an empty scrape, a bill drop and a guarded-field loss are "needs you" after 3 days. An
  unguarded-field loss is "needs you" on day 1.

**How I read the rules, where they leave a choice:**
- **A "day with no new data"** counts only days with a green run (before 01-07: a day with a
  scrape commit). Off days (your pauses) and failed days neither count nor reset the clock.
  Failures have their own rule.
- **One item, one line:** an item stays one line from the day it opens until it clears. If the
  same item comes back within 2 days of clearing, it is still the same item.
- **Ready to turn off:** the latest action in the data must be dated between 7 days before the
  session's end and the end plus the state's tail. My first version had no lower bound and
  recommended frozen states (IN, NY, NE, VT, SC, AR), whose latest actions were months older
  than the session's end.
- **Fleet items:** "3+ states fail on the same days" means 3+ states reach their 3rd failed day
  within a day of each other.
- **A special with no end date** stays on "needs you" from day 14 to the 30-day default end.
- **Weeks** start on Monday. "Open" is the items on the list at any point that week; "raised"
  is the items new that week.

#### The count on each list per week

| List | Weeks | Open: median | Open: worst (week of) | Raised: median | Raised: worst (week of) |
|---|---|---|---|---|---|
| Heads-up | Jan 5–Sep 28 (scrapers on) | 51 | 75 (05-25) | 9 | 29 (07-27) |
| Needs you | Jan 5–Sep 28 | 21 | 30 (02-16) | 2 | 13 (06-22) |
| Ready to turn off | Jan 5–Sep 28 | 3 | 18 (08-03) | 1 | 8 (08-03) |
| Heads-up | Oct 5–Nov 23 (paused; 9 states ran) | 9 | 12 | 0 | 9 |
| Needs you | Oct 5–Nov 23 | 3 | 3 | 0 | 1 |
| Ready to turn off | Oct 5–Nov 23 | 0 | 0 | 0 | 0 |

"Needs you" items opened from Jan 5 to Sep 28: 109, about 2.8 a week. By rule:

| Rule | Items | Median days open |
|---|---|---|
| failed runs, 3 days in a row | 42 | 6 |
| 14 days with nothing new in session | 40 | 44 |
| empty scrape | 10 | 3 |
| bill drop | 7 | 1 |
| field loss | 7 | 1 |
| special with no end date | 3 | 16 |

67 of those 109 overlap a failure from your notes, one of the 14
overnight events, or a candidate. The worst week, 06-22, is one cause: the 06-26 zero-result
change, which raised 5 empty scrapes and 5 bill drops. The January peaks are the real Dec 2025
freeze.

#### Is it low noise? What causes the noise

- **"Needs you" raised: on target.** A median of 2 new items a week, so a handful.
- **"Needs you" open: about 21 a week, above the target.** That comes from 2026, not from the
  rules. Real failures stayed open for weeks: a quiet item lasts a median of 44 days, until a fix
  or a rebuild. In a typical week only 6 open items match no known or candidate failure (worst
  week 14). Once failures get fixed within a week or two, the open count should fall to the
  raised count.
- **Failed runs flap.** FL raised 12 separate failed-runs items and MA 7: each fails 3 days,
  passes once, then fails again. Treating a reopen within 7 days as the same item fixes it.
- **Ready to turn off repeats.** UT was recommended 7 times and WI 4: each late action resets the
  14 days. Counting it once per out-of-session period fixes it.
- **Broken data from one cause shows as many items** (the 06-26 week). Grouping it as one fleet
  item when 3+ states break the same day, as failed runs already are, fixes it.
- **The three tweaks together, computed but not applied:**

  | | As specified | With the tweaks |
  |---|---|---|
  | "Needs you" raised (weeks of Jan 5 to Sep 28, to 10-04) | 111 | 94 |
  | "Needs you" worst week | 13 | 8 |
  | "Ready to turn off" raised | 54 | 26 |

- **Heads-up: the noisiest list.** About 51 items are open in a typical week. 35 of them are
  "7 days with nothing new", which counts in any session status, so every out-of-session state
  sits on it all summer. If that's too much: count it only in session (either source), or
  show it as one digest line ("23 states quiet 7+ days").

#### Known failures: does "needs you" still catch them?

Of the 51 events from your notes, past fixes and the git log, 40 are meant to be caught by a
check; the other 11 are maintenance commits and FL caveats.

- **Caught: 23**, all 15 in-session freezes, 5 of 7 empty scrapes and 3 of 7 field losses.
  Days late:
  - **Freezes:** 13 to 15 days after the first green in-session day (AK, KY, NE, PA, SC, VT,
    WY, IL, NY, WV). That is the 14-day rule doing what it says. NC took 12, IN 2. MI, OH and
    USA opened 4 days *before* the freeze's recorded start (12-14): the quiet had begun on 12-10.
    Counted from each event's own start, the Dec 2025 freezes come out 36 to 81 days late,
    because they began out of session.
  - **Empty scrapes and field losses:** 2 days late (the 3-day rule), or 0 for an unguarded
    field.
- **Log only: 9.** ND's 8 error-page voters and TN's emptied roll calls, as `SCRAPER_FAILURES`
  skips them.
- **Missed by design: 7.**
  - IL's 07-13 empty scrape recovered 2 hours later, and NH's 06-26 one by 06-28: both under 3
    days.
  - NH's sponsorships on 12-25 and 12-30, and its versions on 08-21: back within 3 days, and
    all three are guarded fields.
  - TN's 07-02 chamber swap: one scrape, not 2 in a row.
  - WA's 07-24 freeze: out of session.

  Heads-up raised each of these on day 1.
- **No rule: 1.** MA's "no new bills while actions came" has no "needs you" rule in the new
  lists.

#### Bill-introduction deadlines (MultiState 2026, page 1)

House and Senate deadlines set against the session's start. "Early" means both chambers'
deadlines fall within 31 days of convening, so nearly all bills are filed at the start.

- **Early (21), days from convening to the later deadline:** OK −18 (before convening), FL 0,
  NH 1, WY 4, HI 7, NC 9, VA 9, UT 10, MS 13, AR 14, NE 14, NM 15, TN 17, LA 22, SD 22, IL 23,
  KS 23, AZ 28, ID 28, CO 30, MD 30.
- **Later (7):** AK 34, IN 39, WV 40, CA 46, MO 50, KY 57, AL 65.
- **No deadline in the PDF (18):** CT, DE, GA, IA, MA, ME, MI, MN, NJ, NY, OH, OR, PA, RI, SC,
  VT, WA, WI. In GA and WA the PDF gives only a crossover date. These can file bills any time.
- **No 2026 regular session:** MT, ND, NV, TX.
- 2025 is in the same CSV. In an early state, a session with few new bills after its deadline
  is normal; only actions should keep coming.

#### The data behind the three-list replay

Generated from `history.sqlite` (`list_weeks`, `list_items`) and `csv/intro_deadlines.csv` on 2026-11-26.
The same data is in `/Volumes/govbot-data/scratch/session-status/csv/` for DBeaver.

**Per week** (week starting Monday; "open" = on the list at any point that week, "new" = raised that week):

| Week of | Heads-up open | new | Needs you open | new | Ready to turn off open | new |
|---|---|---|---|---|---|---|
| 2026-01-05 | 53 | 14 | 10 | 3 | 1 | 1 |
| 2026-01-12 | 52 | 9 | 12 | 3 | 1 | 0 |
| 2026-01-19 | 44 | 11 | 18 | 8 | 0 | 0 |
| 2026-01-26 | 48 | 9 | 25 | 7 | 0 | 0 |
| 2026-02-02 | 51 | 14 | 25 | 4 | 0 | 0 |
| 2026-02-09 | 50 | 8 | 28 | 4 | 1 | 1 |
| 2026-02-16 | 52 | 11 | 30 | 4 | 1 | 0 |
| 2026-02-23 | 51 | 8 | 29 | 0 | 1 | 0 |
| 2026-03-02 | 49 | 7 | 30 | 3 | 1 | 0 |
| 2026-03-09 | 51 | 8 | 30 | 2 | 1 | 0 |
| 2026-03-16 | 53 | 9 | 28 | 4 | 2 | 1 |
| 2026-03-23 | 53 | 6 | 27 | 2 | 3 | 1 |
| 2026-03-30 | 48 | 5 | 27 | 3 | 2 | 0 |
| 2026-04-06 | 51 | 9 | 26 | 1 | 2 | 0 |
| 2026-04-13 | 54 | 11 | 26 | 3 | 2 | 1 |
| 2026-04-20 | 52 | 4 | 25 | 5 | 2 | 0 |
| 2026-04-27 | 51 | 8 | 26 | 2 | 1 | 0 |
| 2026-05-04 | 48 | 2 | 26 | 1 | 2 | 1 |
| 2026-05-11 | 53 | 10 | 25 | 1 | 3 | 1 |
| 2026-05-18 | 58 | 13 | 23 | 2 | 5 | 3 |
| 2026-05-25 | 75 | 26 | 22 | 2 | 10 | 5 |
| 2026-06-01 | 61 | 10 | 21 | 1 | 9 | 2 |
| 2026-06-08 | 59 | 7 | 20 | 0 | 8 | 2 |
| 2026-06-15 | 57 | 7 | 18 | 2 | 8 | 1 |
| 2026-06-22 | 74 | 26 | 28 | 13 | 7 | 0 |
| 2026-06-29 | 61 | 13 | 19 | 6 | 8 | 2 |
| 2026-07-06 | 20 | 3 | 8 | 1 | 2 | 0 |
| 2026-07-13 | 46 | 27 | 13 | 6 | 4 | 2 |
| 2026-07-20 | 45 | 23 | 6 | 2 | 4 | 2 |
| 2026-07-27 | 54 | 29 | 5 | 3 | 10 | 6 |
| 2026-08-03 | 56 | 5 | 9 | 4 | 18 | 8 |
| 2026-08-10 | 39 | 9 | 5 | 2 | 10 | 1 |
| 2026-08-17 | 44 | 9 | 8 | 3 | 13 | 6 |
| 2026-08-24 | 40 | 7 | 7 | 0 | 12 | 0 |
| 2026-08-31 | 39 | 6 | 7 | 0 | 11 | 0 |
| 2026-09-07 | 54 | 19 | 5 | 0 | 11 | 1 |
| 2026-09-14 | 48 | 8 | 7 | 2 | 12 | 5 |
| 2026-09-21 | 42 | 6 | 6 | 0 | 12 | 1 |
| 2026-09-28 | 38 | 4 | 7 | 2 | 12 | 0 |
| 2026-10-05 | 4 | 0 | 3 | 0 | 0 | 0 |
| 2026-10-12 | 3 | 0 | 3 | 0 | 0 | 0 |
| 2026-10-19 | 4 | 1 | 3 | 0 | 0 | 0 |
| 2026-10-26 | 12 | 9 | 3 | 1 | 0 | 0 |
| 2026-11-02 | 9 | 0 | 1 | 0 | 0 | 0 |
| 2026-11-09 | 9 | 0 | 1 | 0 | 0 | 0 |
| 2026-11-16 | 9 | 0 | 1 | 0 | 0 | 0 |
| 2026-11-23 | 9 | 0 | 1 | 0 | 0 | 0 |

**Every "needs you" item** opened from 2026-01-05 to 2026-11-25 (a fleet item names its states):

| Rule | Who | Opened | Closed | Days | Detail |
|---|---|---|---|---|---|
| failed_3 | fleet: az dc md nm oh tx va vi | 2026-01-09 | 2026-06-25 | 167 | 8 states failing together |
| quiet_14 | gu | 2026-01-10 | 2026-02-12 | 34 | 45 green in-session days, nothing new |
| failed_3 | al | 2026-01-11 | 2026-01-13 | 3 | failed 3+ days in a row |
| failed_3 | tx | 2026-01-14 | 2026-05-15 | 122 | failed 3+ days in a row |
| quiet_14 | oh | 2026-01-15 | 2026-07-13 | 175 | 43 green in-session days, nothing new |
| failed_3 | nj | 2026-01-16 | 2026-01-28 | 13 | failed 3+ days in a row |
| quiet_14 | vt | 2026-01-19 | 2026-05-29 | 127 | 14 green in-session days, nothing new |
| quiet_14 | ne | 2026-01-20 | 2026-04-17 | 88 | 14 green in-session days, nothing new |
| quiet_14 | ky | 2026-01-21 | 2026-04-15 | 84 | 14 green in-session days, nothing new |
| quiet_14 | ms | 2026-01-21 | 2026-01-31 | 11 | 14 green in-session days, nothing new |
| quiet_14 | ny | 2026-01-22 | 2026-06-05 | 133 | 14 green in-session days, nothing new |
| failed_3 | fl | 2026-01-25 | 2026-01-30 | 6 | failed 3+ days in a row |
| quiet_14 | ks | 2026-01-25 | 2026-04-11 | 76 | 14 green in-session days, nothing new |
| quiet_14 | wa | 2026-01-25 | 2026-03-12 | 47 | 14 green in-session days, nothing new |
| quiet_14 | sc | 2026-01-26 | 2026-06-13 | 138 | 14 green in-session days, nothing new |
| quiet_14 | sd | 2026-01-26 | 2026-03-30 | 64 | 14 green in-session days, nothing new |
| quiet_14 | id | 2026-01-27 | 2026-04-02 | 65 | 14 green in-session days, nothing new |
| quiet_14 | md | 2026-01-27 | 2026-04-13 | 76 | 14 green in-session days, nothing new |
| quiet_14 | il | 2026-01-28 | 2026-05-31 | 119 | 14 green in-session days, nothing new |
| quiet_14 | wv | 2026-01-29 | 2026-03-14 | 44 | 14 green in-session days, nothing new |
| field_loss | nh | 2026-01-30 | 2026-01-30 | 1 | documents still lost |
| quiet_14 | ak | 2026-02-02 | 2026-07-13 | 159 | 14 green in-session days, nothing new |
| failed_3 | ms | 2026-02-03 | 2026-02-03 | 1 | failed 3+ days in a row |
| quiet_14 | hi | 2026-02-04 | 2026-03-23 | 48 | 14 green in-session days, nothing new |
| failed_3 | fleet: ct nh ut | 2026-02-07 | 2026-06-25 | 138 | 3 states failing together |
| failed_3 | fl | 2026-02-11 | 2026-02-11 | 1 | failed 3+ days in a row |
| quiet_14 | nj | 2026-02-12 | 2026-02-18 | 7 | 14 green in-session days, nothing new |
| failed_3 | fl | 2026-02-15 | 2026-02-23 | 9 | failed 3+ days in a row |
| quiet_14 | or | 2026-02-15 | 2026-03-06 | 20 | 14 green in-session days, nothing new |
| quiet_14 | ms | 2026-02-18 | 2026-04-15 | 57 | 14 green in-session days, nothing new |
| failed_3 | nj | 2026-02-21 | 2026-06-25 | 124 | failed 3+ days in a row |
| failed_3 | tn | 2026-02-21 | 2026-06-25 | 124 | failed 3+ days in a row |
| quiet_14 | wy | 2026-02-22 | 2026-03-11 | 18 | 14 green in-session days, nothing new |
| quiet_14 | mn | 2026-03-07 | 2026-03-08 | 2 | 14 green in-session days, nothing new |
| failed_3 | ar | 2026-03-08 | 2026-03-12 | 5 | failed 3+ days in a row |
| failed_3 | fl | 2026-03-08 | 2026-03-10 | 3 | failed 3+ days in a row |
| failed_3 | mn | 2026-03-11 | 2026-03-11 | 1 | failed 3+ days in a row |
| empty_scrape | ar | 2026-03-15 | 2026-07-13 | 117 | a scrape with 0 readable bills |
| failed_3 | la | 2026-03-16 | 2026-03-16 | 1 | failed 3+ days in a row |
| failed_3 | fl | 2026-03-17 | 2026-03-18 | 2 | failed 3+ days in a row |
| failed_3 | mo | 2026-03-19 | 2026-03-23 | 5 | failed 3+ days in a row |
| failed_3 | fl | 2026-03-22 | 2026-03-29 | 8 | failed 3+ days in a row |
| quiet_14 | la | 2026-03-25 | 2026-05-11 | 48 | 14 green in-session days, nothing new |
| failed_3 | hi | 2026-03-26 | 2026-06-25 | 91 | failed 3+ days in a row |
| quiet_14 | gu | 2026-03-30 | 2026-10-29 | 210 | 45 green in-session days, nothing new |
| failed_3 | fl | 2026-04-02 | 2026-04-09 | 8 | failed 3+ days in a row |
| failed_3 | de | 2026-04-03 | 2026-06-09 | 67 | failed 3+ days in a row |
| failed_3 | mn | 2026-04-12 | 2026-04-12 | 1 | failed 3+ days in a row |
| failed_3 | ut | 2026-04-13 | 2026-04-13 | 1 | failed 3+ days in a row |
| quiet_14 | wi | 2026-04-14 | 2026-05-12 | 29 | 113 green in-session days, nothing new (sources disagree) |
| failed_3 | mn | 2026-04-16 | 2026-04-17 | 2 | failed 3+ days in a row |
| quiet_14 | ar | 2026-04-21 | 2026-05-07 | 16 | 14 green in-session days, nothing new |
| failed_3 | fl | 2026-04-21 | 2026-04-22 | 2 | failed 3+ days in a row |
| quiet_14 | mn | 2026-04-21 | 2026-05-18 | 26 | 14 green in-session days, nothing new |
| quiet_14 | nc | 2026-04-21 | 2026-07-01 | 71 | 36 green in-session days, nothing new |
| failed_3 | fleet: al ma mo | 2026-04-25 | 2026-05-20 | 26 | 3 states failing together |
| failed_3 | ks | 2026-04-29 | 2026-05-08 | 10 | failed 3+ days in a row |
| quiet_14 | me | 2026-04-29 | 2026-04-29 | 1 | 14 green in-session days, nothing new (sources disagree) |
| field_loss | ks | 2026-05-09 | 2026-05-11 | 2 | extras (not guarded, in the data repo on day 1) |
| failed_3 | la | 2026-05-14 | 2026-06-25 | 42 | failed 3+ days in a row |
| failed_3 | tx | 2026-05-19 | 2026-06-25 | 37 | failed 3+ days in a row |
| failed_3 | ma | 2026-05-24 | 2026-05-24 | 1 | failed 3+ days in a row |
| special_no_end | sc | 2026-05-29 | 2026-06-13 | 16 | Special Session May 15th (sources/legiscan/2026/2026-07-08.pdf): no end date, check the state's site |
| failed_3 | mp | 2026-05-31 | 2026-06-25 | 26 | failed 3+ days in a row |
| failed_3 | ri | 2026-06-06 | 2026-06-09 | 4 | failed 3+ days in a row |
| failed_3 | ga | 2026-06-19 | 2026-06-19 | 1 | failed 3+ days in a row |
| bill_drop | mo | 2026-06-20 | 2026-06-20 | 1 | 1,057 of 3,156 bills gone and still gone in the next scrape (1,057 of all gone came back later) |
| failed_3 | ma | 2026-06-25 | 2026-06-25 | 1 | failed 3+ days in a row |
| quiet_14 | nj | 2026-06-26 | 2026-06-29 | 4 | 21 green in-session days, nothing new |
| field_loss | tx | 2026-06-27 | 2026-06-27 | 1 | other_identifiers (not guarded, in the data repo on day 1) |
| empty_scrape | ct | 2026-06-28 | 2026-07-01 | 4 | a scrape with 0 readable bills |
| bill_drop | dc | 2026-06-28 | 2026-06-28 | 1 | 977 of 1,183 bills gone and still gone in the next scrape (977 of all gone came back later) |
| empty_scrape | hi | 2026-06-28 | 2026-07-01 | 4 | a scrape with 0 readable bills |
| empty_scrape | la | 2026-06-28 | 2026-06-30 | 3 | a scrape with 0 readable bills |
| bill_drop | mp | 2026-06-28 | 2026-06-28 | 1 | 175 of 301 bills gone and still gone in the next scrape (175 of all gone came back later) |
| empty_scrape | nj | 2026-06-28 | 2026-06-29 | 2 | a scrape with 0 readable bills |
| empty_scrape | nm | 2026-06-28 | 2026-07-04 | 7 | a scrape with 0 readable bills |
| bill_drop | tn | 2026-06-28 | 2026-06-28 | 1 | 6,095 of 6,096 bills gone and still gone in the next scrape (6,095 of all gone came back later) |
| bill_drop | tx | 2026-06-28 | 2026-06-28 | 1 | 362 of 692 bills gone and still gone in the next scrape (362 of all gone came back later) |
| bill_drop | wv | 2026-06-28 | 2026-06-28 | 1 | 567 of 606 bills gone and still gone in the next scrape (567 of all gone came back later) |
| field_loss | tn | 2026-06-29 | 2026-06-29 | 1 | documents still lost |
| quiet_14 | mi | 2026-06-30 | 2026-07-13 | 13 | 14 green in-session days, nothing new |
| empty_scrape | ma | 2026-07-01 | 2026-07-01 | 1 | a scrape with 0 readable bills |
| failed_3 | ma | 2026-07-04 | 2026-07-04 | 1 | failed 3+ days in a row |
| empty_scrape | il | 2026-07-05 | 2026-07-05 | 1 | a scrape with 0 readable bills |
| empty_scrape | nh | 2026-07-05 | 2026-07-05 | 1 | a scrape with 0 readable bills |
| failed_3 | ma | 2026-07-09 | 2026-07-12 | 4 | failed 3+ days in a row |
| failed_3 | fl | 2026-07-15 | 2026-07-15 | 1 | failed 3+ days in a row |
| field_loss | il | 2026-07-15 | 2026-07-15 | 1 | abstracts still lost |
| quiet_14 | nj | 2026-07-15 | 2026-08-08 | 25 | 14 green in-session days, nothing new |
| field_loss | de | 2026-07-17 | 2026-07-17 | 1 | versions still lost |
| failed_3 | fleet: ak ar il in ma mi nc ne nm nv ny oh pa sc usa va vi vt wv | 2026-07-18 | 2026-07-23 | 6 | 19 states failing together |
| quiet_14 | mp | 2026-07-18 | 2026-07-25 | 8 | 21 green in-session days, nothing new |
| empty_scrape | ga | 2026-07-23 | 2026-07-23 | 1 | a scrape with 0 readable bills |
| bill_drop | mo | 2026-07-23 | 2026-07-23 | 1 | 1,060 of 3,159 bills gone and still gone in the next scrape (1,060 of all gone came back later) |
| failed_3 | fl | 2026-07-27 | 2026-08-06 | 11 | failed 3+ days in a row |
| failed_3 | ma | 2026-07-31 | 2026-08-06 | 7 | failed 3+ days in a row |
| quiet_14 | nc | 2026-08-02 | 2026-08-08 | 7 | 14 green in-session days, nothing new |
| quiet_14 | oh | 2026-08-04 | 2026-08-08 | 5 | 14 green in-session days, nothing new |
| quiet_14 | pa | 2026-08-04 | 2026-09-20 | 48 | 14 green in-session days, nothing new |
| quiet_14 | usa | 2026-08-04 | 2026-08-08 | 5 | 14 green in-session days, nothing new |
| quiet_14 | vi | 2026-08-09 | 2026-09-22 | 44 | 45 green in-session days, nothing new |
| failed_3 | fl | 2026-08-10 | 2026-09-29 | 51 | failed 3+ days in a row |
| failed_3 | ma | 2026-08-10 | 2026-09-29 | 51 | failed 3+ days in a row |
| special_no_end | md | 2026-08-17 | 2026-09-01 | 16 | Special Session August 3rd (sources/legiscan/2026/2026-07-08.pdf): no end date, check the state's site |
| field_loss | ky | 2026-08-22 | 2026-08-22 | 1 | sponsorships still lost |
| quiet_14 | md | 2026-08-23 | 2026-09-01 | 10 | 14 green in-session days, nothing new (sources disagree) |
| quiet_14 | nc | 2026-09-16 | 2026-09-29 | 14 | 14 green in-session days, nothing new (sources disagree) |
| special_no_end | nd | 2026-09-16 | 2026-10-01 | 16 | Special Session September 2 (sources/legiscan/2026/2026-08-20.pdf): no end date, check the state's site |
| quiet_14 | pa | 2026-09-30 | 2026-10-23 | 24 | 62 green in-session days, nothing new |
| quiet_14 | vi | 2026-09-30 | 2026-10-29 | 30 | 89 green in-session days, nothing new |
| failed_3 | fleet: dc gu mi mp nj oh pa usa vi | 2026-11-01 | 2026-11-25 | 25 | 9 states failing together |

**Ready to turn off**, every recommendation:

| State | Opened | Closed | Days | Detail |
|---|---|---|---|---|
| ut | 2026-01-09 | 2026-01-14 | 6 | out of session since 2025-12-10; latest action 2025-12-11; tail 16 |
| nd | 2026-02-12 | 2026-03-25 | 42 | out of session since 2026-01-22; latest action 2026-01-28; tail 33 |
| ut | 2026-03-22 | 2026-04-10 | 20 | out of session since 2026-03-08; latest action 2026-03-07; tail 16 |
| nd | 2026-03-29 | 2026-04-23 | 26 | out of session since 2026-01-22; latest action 2026-01-28; tail 33 |
| ut | 2026-04-16 | 2026-05-11 | 26 | out of session since 2026-03-08; latest action 2026-03-07; tail 16 |
| nd | 2026-05-08 | 2026-05-25 | 18 | out of session since 2026-01-22; latest action 2026-01-28; tail 33 |
| ut | 2026-05-16 | 2026-05-25 | 10 | out of session since 2026-03-08; latest action 2026-03-07; tail 16 |
| ia | 2026-05-18 | 2026-08-08 | 81 | out of session since 2026-05-04; latest action 2026-05-03; tail 30 |
| fl | 2026-05-19 | 2026-05-27 | 8 | out of session since 2026-03-14; latest action 2026-05-04; tail 104 |
| ks | 2026-05-23 | 2026-08-08 | 76 | out of session since 2026-04-12; latest action 2026-04-10; tail 33 |
| co | 2026-05-30 | 2026-07-01 | 33 | out of session since 2026-05-14; latest action 2026-05-13; tail 21 |
| nd | 2026-05-30 | 2026-07-01 | 33 | out of session since 2026-01-22; latest action 2026-01-28; tail 33 |
| ut | 2026-05-30 | 2026-06-04 | 6 | out of session since 2026-03-08; latest action 2026-03-07; tail 16 |
| wi | 2026-05-30 | 2026-06-05 | 7 | out of session since 2026-05-15; latest action 2026-05-13; tail 14 |
| fl | 2026-05-31 | 2026-06-01 | 2 | out of session since 2026-03-14; latest action 2026-05-04; tail 104 |
| ok | 2026-06-02 | 2026-07-01 | 30 | out of session since 2026-05-15; latest action 2026-05-14; tail 15 |
| al | 2026-06-05 | 2026-07-01 | 27 | out of session since 2026-05-09; latest action 2026-05-08; tail 8 |
| ut | 2026-06-08 | 2026-06-16 | 9 | out of session since 2026-03-08; latest action 2026-03-07; tail 16 |
| wi | 2026-06-11 | 2026-06-13 | 3 | out of session since 2026-05-15; latest action 2026-05-13; tail 14 |
| wi | 2026-06-20 | 2026-06-25 | 6 | out of session since 2026-05-15; latest action 2026-05-13; tail 14 |
| wi | 2026-06-30 | 2026-07-01 | 2 | out of session since 2026-05-15; latest action 2026-05-13; tail 14 |
| ut | 2026-07-01 | 2026-07-01 | 1 | out of session since 2026-03-08; latest action 2026-03-07; tail 16 |
| al | 2026-07-15 | 2026-07-15 | 1 | out of session since 2026-05-09; latest action 2026-05-08; tail 8 |
| nd | 2026-07-15 | 2026-07-15 | 1 | out of session since 2026-01-22; latest action 2026-01-28; tail 33 |
| al | 2026-07-21 | 2026-09-12 | 54 | out of session since 2026-05-09; latest action 2026-05-08; tail 8 |
| nd | 2026-07-21 | 2026-08-21 | 32 | out of session since 2026-01-22; latest action 2026-01-28; tail 33 |
| wv | 2026-08-01 | 2026-08-08 | 8 | out of session since 2026-03-15; latest action 2026-06-29; tail 107 |
| ar | 2026-08-02 | 2026-09-29 | 59 | out of session since 2026-05-08; latest action 2026-05-06; tail 33 |
| in | 2026-08-02 | 2026-09-12 | 42 | out of session since 2026-02-28; latest action 2026-03-12; tail 13 |
| sd | 2026-08-02 | 2026-09-29 | 59 | out of session since 2026-03-31; latest action 2026-03-30; tail 33 |
| va | 2026-08-02 | 2026-08-08 | 7 | out of session since 2026-06-30; latest action 2026-07-01; tail 2 |
| vt | 2026-08-02 | 2026-08-08 | 7 | out of session since 2026-05-30; latest action 2026-05-29; tail 33 |
| id | 2026-08-03 | 2026-09-29 | 58 | out of session since 2026-04-03; latest action 2026-04-02; tail 33 |
| ky | 2026-08-03 | 2026-09-12 | 41 | out of session since 2026-04-16; latest action 2026-04-27; tail 12 |
| wy | 2026-08-03 | 2026-08-08 | 6 | out of session since 2026-03-12; latest action 2026-03-10; tail 33 |
| il | 2026-08-04 | 2026-08-08 | 5 | out of session since 2026-06-01; latest action 2026-07-20; tail 68 |
| ny | 2026-08-04 | 2026-08-08 | 5 | out of session since 2026-06-06; latest action 2026-07-17; tail 103 |
| az | 2026-08-07 | 2026-08-08 | 2 | out of session since 2026-06-14; latest action 2026-06-22; tail 9 |
| mo | 2026-08-07 | 2026-08-14 | 8 | out of session since 2026-05-16; latest action 2026-07-13; tail 59 |
| ne | 2026-08-09 | 2026-08-10 | 2 | out of session since 2026-04-18; latest action 2026-07-21; tail 139 |
| wv | 2026-08-12 | 2026-08-13 | 2 | out of session since 2026-03-15; latest action 2026-06-29; tail 107 |
| ms | 2026-08-19 | 2026-09-14 | 27 | out of session since 2026-07-17; latest action 2026-07-17; tail 13 |
| az | 2026-08-23 | 2026-09-01 | 10 | out of session since 2026-06-14; latest action 2026-06-22; tail 9 |
| ks | 2026-08-23 | 2026-09-29 | 38 | out of session since 2026-04-12; latest action 2026-04-10; tail 33 |
| me | 2026-08-23 | 2026-09-11 | 20 | out of session since 2026-04-30; latest action 2026-04-29; tail 33 |
| va | 2026-08-23 | 2026-09-29 | 38 | out of session since 2026-06-30; latest action 2026-07-01; tail 2 |
| wy | 2026-08-23 | 2026-08-24 | 2 | out of session since 2026-03-12; latest action 2026-03-10; tail 33 |
| wy | 2026-09-09 | 2026-09-29 | 21 | out of session since 2026-03-12; latest action 2026-03-10; tail 33 |
| al | 2026-09-16 | 2026-09-29 | 14 | out of session since 2026-05-09; latest action 2026-05-08; tail 8 |
| az | 2026-09-16 | 2026-09-29 | 14 | out of session since 2026-06-14; latest action 2026-06-22; tail 9 |
| ky | 2026-09-16 | 2026-09-29 | 14 | out of session since 2026-04-16; latest action 2026-04-27; tail 12 |
| in | 2026-09-18 | 2026-09-29 | 12 | out of session since 2026-02-28; latest action 2026-03-12; tail 13 |
| ms | 2026-09-18 | 2026-09-29 | 12 | out of session since 2026-07-17; latest action 2026-07-17; tail 13 |
| me | 2026-09-26 | 2026-09-29 | 4 | out of session since 2026-04-30; latest action 2026-04-29; tail 33 |

**Known failures** (the 40 of the 51 a check is meant to catch), as scored:

| State | Event | Started | Result | Item | Days after start | Days after first green in-session day |
| nd | broken_votes: error page as a voter, 1,137 votes | 2025-12-30 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: error page as a voter, 1,149 votes | 2026-04-22 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: error page as a voter, 1,166 votes | 2026-04-30 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: error page as a voter, 1,166 votes | 2026-06-20 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: error page as a voter, 1,166 votes | 2026-06-24 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: error page as a voter, 1,166 votes | 2026-08-11 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: 'Proxy Error' as a voter, 1,166 votes | 2026-08-29 | log only (SCRAPER_FAILURES) | — | — | — |
| nd | broken_votes: 'Proxy Error' as a voter, 15 votes | 2026-09-19 | log only (SCRAPER_FAILURES) | — | — | — |
| tn | broken_votes: 6,787 roll calls emptied over 63 nights, 5,839 on 07-02 | 2026-06-26 | log only (SCRAPER_FAILURES) | — | — | — |
| tn | chamber_swap: Senate bills' actions saved under the House | 2026-06-26 | missed | — | — | — |
| ar | empty_scrape: 0 bill files in 119 scrapes | 2026-03-13 | caught | empty_scrape 2026-03-15→2026-07-13 | 2 | — |
| ga | empty_scrape: every bill file had conflict markers | 2026-07-21 | caught | empty_scrape 2026-07-23→2026-07-23 | 2 | — |
| il | empty_scrape: a 0-bill scrape committed as green | 2026-07-03 | caught | empty_scrape 2026-07-05→2026-07-05 | 2 | — |
| il | empty_scrape: a 0-bill scrape committed as green | 2026-07-13 | missed | — | — | — |
| ma | empty_scrape: 2 scrapes with 0 bill files | 2026-06-29 | caught | empty_scrape 2026-07-01→2026-07-01 | 2 | — |
| nh | empty_scrape: 4 scrapes with 0 bill files | 2026-06-26 | missed | — | — | — |
| nh | empty_scrape: a scrape with 0 bill files | 2026-07-03 | caught | empty_scrape 2026-07-05→2026-07-05 | 2 | — |
| il | field_loss: abstracts on 8,648 of 8,648 bills, never back | 2026-07-13 | caught | field_loss 2026-07-15→2026-07-15 | 2 | — |
| ky | field_loss: sponsorships on 1,707 of 1,707 bills, never back | 2026-08-20 | caught | field_loss 2026-08-22→2026-08-22 | 2 | — |
| nh | field_loss: sponsorships 1,143 of 1,143 | 2025-12-25 | missed | — | — | — |
| nh | field_loss: sponsorships 1,143 of 1,143 | 2025-12-30 | missed | — | — | — |
| nh | field_loss: documents 33 of 33, never back | 2026-01-28 | caught | field_loss 2026-01-30→2026-01-30 | 2 | — |
| nh | field_loss: versions 1,126 of 1,155 | 2026-08-21 | missed | — | — | — |
| ma | no_new_bills: exactly 8,975 bills; no new bills, actions still came | 2025-11-28 | no needs-you rule for this kind | — | — | — |
| ak | unchanged: stuck at 514 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2026-02-02→2026-07-13 | 50 | 13 |
| il | unchanged: 8,648 bills unchanged (the Dec 2025 freeze) | 2025-12-15 | caught | quiet_14 2026-01-28→2026-05-31 | 44 | 14 |
| in | unchanged: stuck at 40 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2025-12-16→2026-02-27 | 2 | 2 |
| ky | unchanged: 74 prefiled bills unchanged through the 2026 session | 2026-01-08 | caught | quiet_14 2026-01-21→2026-04-15 | 13 | 13 |
| mi | unchanged: stuck at ~2,360 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2025-12-10→2026-06-15 | -4 | -4 |
| nc | unchanged: 1,794 bills unchanged (the Dec 2025 freeze) | 2025-11-28 | caught | quiet_14 2025-12-10→2025-12-31 | 12 | 12 |
| ne | unchanged: stuck at ~1,037 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2026-01-20→2026-04-17 | 37 | 13 |
| ny | unchanged: stuck at ~9,584 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2026-01-22→2026-06-05 | 39 | 15 |
| oh | unchanged: stuck at ~1,538 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2025-12-10→2026-01-07 | -4 | -4 |
| pa | unchanged: 3,578 bills unchanged from the first scrape until 07-14 (found by the  | 2025-11-28 | caught | quiet_14 2025-12-11→2026-07-13 | 13 | 13 |
| sc | unchanged: stuck at ~3,051 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2026-01-26→2026-06-13 | 43 | 13 |
| usa | unchanged: stuck at ~8,250 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2025-12-10→2026-07-13 | -4 | -5 |
| vt | unchanged: stuck at 898 bills while green (the Dec 2025 freeze) | 2025-12-14 | caught | quiet_14 2026-01-19→2026-05-29 | 36 | 13 |
| wa | unchanged: frozen since 07-24 04:06, silently 'success' (out of session) | 2026-07-24 | missed | — | — | — |
| wv | unchanged: stuck at ~2,709 files while green (the Dec 2025 freeze; Azure IP block | 2025-12-14 | caught | quiet_14 2026-01-29→2026-03-14 | 46 | 15 |
| wy | unchanged: 23 bills unchanged through the 2026 budget session | 2025-12-03 | caught | quiet_14 2026-02-22→2026-03-11 | 81 | 13 |

**Bill-introduction deadlines** (MultiState page 1; days = convening to the later chamber deadline; early = within 31 days):

| State | Year | Convenes | House | Senate | Crossover | Days | Early |
|---|---|---|---|---|---|---|---|
| AK | 2025 | 2025-01-21 | — | — | — | — | — |
| AL | 2025 | 2025-02-04 | — | — | — | — | — |
| AR | 2025 | 2025-01-13 | 2025-03-03 | 2025-03-03 | — | 49 | no |
| AZ | 2025 | 2025-01-13 | 2025-02-11 | 2025-02-03 | — | 29 | yes |
| CA | 2025 | 2024-12-02 | 2025-02-21 | 2025-02-21 | 2025-06-06 | 81 | no |
| CO | 2025 | 2025-01-08 | 2025-02-07 | 2025-01-31 | 2025-03-14 | 30 | yes |
| CT | 2025 | 2025-01-08 | — | — | — | — | — |
| DE | 2025 | 2025-01-14 | — | — | — | — | — |
| FL | 2025 | 2025-03-04 | 2025-02-28 | 2025-03-04 | — | 0 | yes |
| GA | 2025 | 2025-01-13 | — | — | 2025-03-06 | — | — |
| HI | 2025 | 2025-01-15 | 2025-01-23 | 2025-01-23 | 2025-03-06 | 8 | yes |
| IA | 2025 | 2025-01-13 | — | — | — | — | — |
| ID | 2025 | 2025-01-06 | 2025-02-10 | 2025-01-17 | 2025-03-03 | 35 | no |
| IL | 2025 | 2025-01-08 | 2025-02-07 | 2025-02-07 | 2025-04-11 | 30 | yes |
| IN | 2025 | 2025-01-08 | 2025-01-14 | 2025-01-16 | 2025-02-20 | 8 | yes |
| KS | 2025 | 2025-01-13 | — | — | 2025-02-20 | — | — |
| KY | 2025 | 2025-01-07 | 2025-02-19 | 2025-02-18 | — | 43 | no |
| LA | 2025 | 2025-04-14 | 2025-04-23 | 2025-04-23 | 2025-06-09 | 9 | yes |
| MA | 2025 | 2025-01-01 | — | — | — | — | — |
| MD | 2025 | 2025-01-08 | 2025-02-07 | 2025-02-03 | 2025-03-17 | 30 | yes |
| ME | 2025 | 2024-12-04 | — | — | — | — | — |
| MI | 2025 | 2025-01-08 | — | — | — | — | — |
| MN | 2025 | 2025-01-14 | — | — | — | — | — |
| MO | 2025 | 2025-01-08 | 2025-03-08 | 2025-03-01 | — | 59 | no |
| MS | 2025 | 2025-01-07 | 2025-01-20 | 2025-01-20 | 2025-02-14 | 13 | yes |
| MT | 2025 | 2025-01-06 | 2025-02-26 | 2025-02-26 | 2025-03-07 | 51 | no |
| NC | 2025 | 2025-01-08 | 2025-04-03 | 2025-03-25 | 2025-05-08 | 85 | no |
| ND | 2025 | 2025-01-07 | 2025-01-20 | 2025-01-27 | 2025-02-25 | 20 | yes |
| NE | 2025 | 2025-01-08 | — | 2025-01-22 | — | 14 | yes |
| NH | 2025 | 2025-01-08 | 2025-01-24 | — | 2025-04-10 | 16 | yes |
| NJ | 2025 | 2025-01-14 | — | — | — | — | — |
| NM | 2025 | 2025-01-21 | 2025-02-20 | 2025-02-20 | — | 30 | yes |
| NV | 2025 | 2025-02-03 | 2025-03-17 | 2025-03-17 | 2025-04-22 | 42 | no |
| NY | 2025 | 2025-01-08 | — | — | — | — | — |
| OH | 2025 | 2025-01-06 | — | — | — | — | — |
| OK | 2025 | 2025-02-03 | 2025-01-16 | 2025-01-16 | 2025-03-27 | -18 | yes |
| OR | 2025 | 2025-01-21 | 2025-02-25 | 2025-02-25 | — | 35 | no |
| PA | 2025 | 2025-01-07 | — | — | — | — | — |
| RI | 2025 | 2025-01-07 | 2025-02-27 | 2025-02-25 | — | 51 | no |
| SC | 2025 | 2025-01-14 | — | — | — | — | — |
| SD | 2025 | 2025-01-14 | 2025-02-06 | 2025-02-06 | 2025-02-25 | 23 | yes |
| TN | 2025 | 2025-01-14 | — | — | — | — | — |
| TX | 2025 | 2025-01-14 | 2025-03-14 | 2025-03-14 | — | 59 | no |
| UT | 2025 | 2025-01-21 | 2025-01-31 | 2025-01-31 | 2025-03-04 | 10 | yes |
| VA | 2025 | 2025-01-08 | 2025-01-17 | 2025-01-17 | 2025-02-04 | 9 | yes |
| VT | 2025 | 2025-01-08 | — | — | 2025-03-14 | — | — |
| WA | 2025 | 2025-01-13 | — | — | 2025-03-12 | — | — |
| WI | 2025 | 2025-01-06 | — | — | — | — | — |
| WV | 2025 | 2025-02-12 | 2025-03-18 | 2025-03-24 | 2025-04-02 | 40 | no |
| WY | 2025 | 2025-01-14 | 2025-02-03 | 2025-01-29 | 2025-02-12 | 20 | yes |
| AK | 2026 | 2026-01-20 | 2026-02-23 | 2026-02-23 | — | 34 | no |
| AL | 2026 | 2026-01-13 | — | 2026-03-19 | 2026-04-02 | 65 | no |
| AR | 2026 | 2026-04-08 | 2026-04-22 | 2026-04-22 | — | 14 | yes |
| AZ | 2026 | 2026-01-12 | 2026-02-09 | 2026-02-02 | 2026-02-25 | 28 | yes |
| CA | 2026 | 2026-01-05 | 2026-02-20 | 2026-02-20 | 2026-05-29 | 46 | no |
| CO | 2026 | 2026-01-14 | 2026-02-13 | 2026-02-06 | 2026-03-20 | 30 | yes |
| CT | 2026 | 2026-02-04 | — | — | — | — | — |
| DE | 2026 | 2026-01-13 | — | — | — | — | — |
| FL | 2026 | 2026-01-13 | 2026-01-13 | 2026-01-13 | — | 0 | yes |
| GA | 2026 | 2026-01-12 | — | — | 2026-03-06 | — | — |
| HI | 2026 | 2026-01-21 | 2026-01-28 | 2026-01-28 | 2026-03-12 | 7 | yes |
| IA | 2026 | 2026-01-12 | — | — | — | — | — |
| ID | 2026 | 2026-01-12 | 2026-02-09 | 2026-01-23 | 2026-03-09 | 28 | yes |
| IL | 2026 | 2026-01-14 | 2026-02-06 | 2026-02-06 | 2026-04-17 | 23 | yes |
| IN | 2026 | 2025-12-01 | 2026-01-07 | 2026-01-09 | 2026-01-29 | 39 | no |
| KS | 2026 | 2026-01-12 | 2026-02-04 | 2026-02-04 | 2026-02-19 | 23 | yes |
| KY | 2026 | 2026-01-06 | 2026-03-04 | 2026-03-02 | — | 57 | no |
| LA | 2026 | 2026-03-09 | 2026-03-31 | 2026-03-31 | 2026-05-29 | 22 | yes |
| MA | 2026 | 2026-01-07 | — | — | — | — | — |
| MD | 2026 | 2026-01-14 | 2026-02-13 | 2026-02-09 | 2026-03-23 | 30 | yes |
| ME | 2026 | 2026-01-07 | — | — | — | — | — |
| MI | 2026 | 2026-01-14 | — | — | — | — | — |
| MN | 2026 | 2026-02-17 | — | — | — | — | — |
| MO | 2026 | 2026-01-07 | — | 2026-02-26 | — | 50 | no |
| MS | 2026 | 2026-01-06 | 2026-01-19 | 2026-01-19 | 2026-02-12 | 13 | yes |
| MT | 2026 | — | — | — | — | — | — |
| NC | 2026 | 2026-04-21 | 2026-04-30 | 2026-04-30 | — | 9 | yes |
| ND | 2026 | — | — | — | — | — | — |
| NE | 2026 | 2026-01-07 | — | 2026-01-21 | — | 14 | yes |
| NH | 2026 | 2026-01-07 | 2026-01-08 | — | 2026-03-26 | 1 | yes |
| NJ | 2026 | 2026-01-13 | — | — | — | — | — |
| NM | 2026 | 2026-01-20 | 2026-02-04 | 2026-02-04 | — | 15 | yes |
| NV | 2026 | — | — | — | — | — | — |
| NY | 2026 | 2026-01-07 | — | — | — | — | — |
| OH | 2026 | 2026-01-05 | — | — | — | — | — |
| OK | 2026 | 2026-02-02 | 2026-01-15 | 2026-01-15 | 2026-03-26 | -18 | yes |
| OR | 2026 | 2026-02-02 | — | — | — | — | — |
| PA | 2026 | 2026-01-06 | — | — | — | — | — |
| RI | 2026 | 2026-01-06 | — | — | — | — | — |
| SC | 2026 | 2026-01-13 | — | — | — | — | — |
| SD | 2026 | 2026-01-13 | 2026-02-04 | 2026-02-04 | 2026-02-24 | 22 | yes |
| TN | 2026 | 2026-01-13 | 2026-01-30 | 2026-01-30 | — | 17 | yes |
| TX | 2026 | — | — | — | — | — | — |
| UT | 2026 | 2026-01-20 | 2026-01-30 | 2026-01-30 | 2026-03-03 | 10 | yes |
| VA | 2026 | 2026-01-14 | 2026-01-23 | 2026-01-23 | 2026-02-17 | 9 | yes |
| VT | 2026 | 2026-01-06 | — | — | — | — | — |
| WA | 2026 | 2026-01-12 | — | — | 2026-02-17 | — | — |
| WI | 2026 | 2026-01-13 | — | — | — | — | — |
| WV | 2026 | 2026-01-14 | 2026-02-17 | 2026-02-23 | 2026-03-04 | 40 | no |
| WY | 2026 | 2026-02-09 | 2026-02-13 | 2026-02-13 | 2026-02-24 | 4 | yes |

#### For you to decide next

- **The three dedup tweaks** above: failed runs within 7 days, ready-to-turn-off once per
  period, broken-data fleet items.
- **Heads-up "7 days quiet":** in session only, or one digest line?
- **MA's "no new bills while actions came":** should it have a "needs you" rule (it was 60 days
  late under the old replay)?
- **Early-deadline states:** should they skip "no new bills"-style checks after the deadline?

### 2026-11-26: the three-list replay, revised. Stopping for review.

Tamara's decisions and the reviewer's corrections, all applied, then re-run once. `lists.py`
now runs both modes and writes both: `specified` (the first replay, reproduced exactly) and
`revised`. The tables `list_items` and `list_weeks` have a `mode` column. Report:
`session-status/lists.md`; CSVs in `session-status/csv/`. Tests pass. Nothing committed.

**What changed (revised):**
- **Failed runs:** a reopen within 7 days is the same item.
- **Ready to turn off:**
  - one item per out-of-session period;
  - not when a session or prefiling starts within 60 days (it had recommended UT on 01-09);
  - not when the state's quiet began on the same day as 3+ other states' (the cache bug's
    signature: IL and NY on 08-04). Both cases are gone now.
- **Broken data on 3+ states the same day** is one fleet item, on both lists.
- **Heads-up "7 days quiet"** counts in session only (either source). Out-of-session quiet
  states are one digest line per week ("N states quiet 7+ days, out of session: …").
- **"No new bills while actions came"** is heads-up only, after 21 green in-session days (the
  old check's window). It applies to states without an early intro deadline; early-deadline
  states skip it after their deadline.
- **Chamber swap** is "needs you" on day 1. Broken votes stay at 2 scrapes.
- **Bill drop** follows the 3-day rule, counted from the night of the drop. The first replay
  raised it from the replay check's "still gone in the next scrape" day.
- **Broken-data items stay open until the damage clears,** that is, until the bills or the field
  are back, capped at 120 days. Before, they were marked for one day, so their "days open" meant
  nothing. This is why field loss's median open time is now 73 days: IL's abstracts, KY's
  sponsors and NH's documents never came back.

#### The count on each list per week (weeks of 2026-01-05 to 2026-09-28, scrapers on)

| List | Mode | Open: median | Open: worst (week of) | New: median | New: worst (week of) | New: total |
|---|---|---|---|---|---|---|
| Heads-up | specified | 51 | 75 (05-25) | 9 | 29 (07-27) | 420 |
| Heads-up | revised | 35 | 50 (05-25) | 8 | 25 (05-25) | 381 |
| Needs you | specified | 21 | 30 (02-16) | 2 | 13 (06-22) | 111 |
| Needs you | revised | 22 | 31 (02-16) | 2 | 8 (01-19) | 98 |
| Ready to turn off | specified | 3 | 18 (08-03) | 1 | 8 (08-03) | 54 |
| Ready to turn off | revised | 3 | 9 (06-01) | 0 | 3 (05-18) | 15 |

Weeks of 10-05 to 11-23 (paused; 9 states ran) are the same in both modes: heads-up 9 open, needs
you 3 open, nothing ready to turn off.

**Needs you, items opened Jan 5 to Sep 28, by rule:**

| Rule | Specified | Revised | Median days open (specified / revised) |
|---|---|---|---|
| failed runs, 3 days in a row | 42 | 33 | 6 / 6 |
| 14 days quiet in session | 40 | 40 | 44 / 44 |
| empty scrape | 10 | 6 | 3 / 16 |
| field loss | 7 | 7 | 1 / 73 |
| bill drop | 7 | 4 | 1 / 17 |
| chamber swap | 0 | 3 | — / 1 |
| special with no end date | 3 | 3 | 16 / 16 |

**Heads-up, items opened Jan 5 to Sep 28, by rule:**

| Rule | Specified | Revised |
|---|---|---|
| failed run | 226 | 226 |
| 7 days quiet | 161 (any status) | 81 (in session) |
| out-of-session digest | — | 39 (one a week) |
| broken data | 30 | 23 |
| no new bills | — | 9 |

**Ready to turn off, revised: 15 recommendations,** each once per out-of-session period: ND
02-12, UT 03-22, IA 05-18, FL 05-19, KS 05-23, CO 05-30, WI 05-30, OK 06-02, AL 06-05, SD 08-02,
AZ 08-07, NE 08-09, MS 08-19, WY 09-09, ME 09-26.

#### Is it low noise now?

- **Needs you: yes for new items.** A median of 2 new a week; the worst week drops from 13 to
  8, because the 06-26 week's 5 empty scrapes and 5 bill drops became fleet items.
  - **Open items barely move (about 22 a week).** They are long-running 2026 failures nobody
    fixed: a quiet item lasts a median of 44 days, and broken data now stays listed until
    repaired.
  - **Open items matching no known or candidate failure:** median 6 a week, worst week 8 (was 14).
- **Ready to turn off: yes.** 15 a year, never more than 3 new in a week.
- **Heads-up: still the noisiest list (35 open a week).** The biggest share is now **failed runs:
  16 open in a typical week, 226 raised.** They come from the months-long failure waves (AZ,
  DC, NM, TX and others from January to June), every one already on "needs you" as a failed-runs
  item. In-session quiet is 13 open a week; the digest is 1 line.
  - **The change that would cut this most:** drop a heads-up item while the same state and kind
    is on "needs you". Not applied; it's your call.

#### Known failures: does "needs you" still catch them? (revised)

Of the 40 events a check is meant to catch:
- **Caught: 24** (23 before). **TN's 06-26 chamber swap is now caught on day 0.**
- **Days late, unchanged from the first replay:**
  - **Freezes:** 13 to 15 days after the first green in-session day for AK, IL, KY, NE, NY, PA,
    SC, VT, WV and WY. NC took 12 and IN 2. MI, OH and USA opened 4 to 5 days before the
    freeze's recorded start. Counted from each freeze's own start: 36 to 81 days, because the
    Dec 2025 freezes began out of session.
  - **Empty scrapes** (AR, GA, IL 07-03, MA, NH 07-03) and **field losses** (IL abstracts, KY
    sponsors, NH documents): 2 days.
- **Log only: 9.** ND's 8 error-page voters and TN's emptied roll calls (`SCRAPER_FAILURES`).
- **Missed by design: 6.** All were fixed within 3 days, and heads-up raised each on day 0:
  - IL's 07-13 and NH's 06-26 empty scrapes;
  - NH's sponsorships on 12-25 and 12-30;
  - NH's versions on 08-21.

  WA's 07-24 freeze was out of session, so it is in that week's digest line now, not a line of
  its own.
- **Heads-up only: 1.** MA's "no new bills while actions came", raised on day 21 (MA has no intro
  deadline in the MultiState PDF).

#### For you to decide next

- **Drop a heads-up item while the same thing is on "needs you"?** This is mainly the failed-run
  waves, 16 open a week.
- **Broken-data items stay open until repaired.** Should an item older than some limit drop to a
  weekly reminder instead, like IL's abstracts, which never came back?

### 2026-11-26: four lists (revised rules), re-run once. Stopping for review.

Tamara's answers, applied:
- **Drop a heads-up item while the same state and kind is on "needs you".** Failed run ↔ failed
  runs 3 days; 7 days quiet ↔ 14 days quiet; broken data ↔ any broken-data rule.
- **Known ongoing.** After 30 days open, a "needs you" item (quiet, or any broken-data kind) moves
  to a **"known ongoing"** list: one line a week with its day count.
- **Accepted file.** `tamara-notes/session-dates/accepted.csv` (`state,kind,reason,date`, empty
  for now; described in that folder's README). From its date, an accepted state + kind goes to
  the log only.
- **A fourth list, "turn back on"** (rule below).

The replay reports the revised rules only. Code: `sessions/lists.py`; report:
`session-status/lists.md`; CSVs: `list_items`, `list_weeks`, `turn_on_starts`. Tests pass.
Nothing committed.

**The "turn back on" rule as built:** a day with no run (`off` in run history) while a regular
session, special session or prefiling **starts within 30 days** in any source (`starts_soon`).
- Starts come from `sessions.csv`: every regular and special row's convene date, plus prefiling
  from LegiScan's "Prefiling" notes, counted from the PDF's date.
- **One addition, so you can drop it:** a day with no run while a session is **already running**
  (`running_now`). Without it, a scraper switched off mid-session shows on no list, because off
  days don't count toward quiet. Reported separately.

#### The count on each list per week (weeks of 2026-01-05 to 2026-09-28)

| List | Open: median | Open: worst (week of) | New: median | New: worst (week of) | New: total |
|---|---|---|---|---|---|
| Heads-up | 13 | 27 (07-13) | 9 | 24 (05-25) | 376 |
| Needs you | 11 | 25 (02-16) | 2 | 8 (01-19) | 98 |
| Known ongoing (weekly) | 8 | 20 (03-02) | 0 | 9 (02-23) | 35 |
| Ready to turn off | 3 | 9 (06-01) | 0 | 3 (05-18) | 15 |
| Turn back on | 0 | 25 (05-25) | 0 | 23 (05-25) | 49 |

Weeks of 10-05 to 11-23 (paused; 9 states ran):

| List | Open: median | Open: worst | New: total |
|---|---|---|---|
| Heads-up | 0 | 10 | 10 |
| Needs you | 2 | 2 | 1 |
| Known ongoing | 1 | 1 | 0 |
| Ready to turn off | 0 | 0 | 0 |
| Turn back on | 14 | 15 | 25 |

**Compared with the last run:**
- **Heads-up:** 35 → 13 open a week. Dropping the duplicates removed most of the failed-run
  waves.
- **Needs you:** 22 → 11 open a week. The long-running freezes moved to "known ongoing" (8 a
  week), the list you'd read once a week.
- Raised items are unchanged: a median of 2 new "needs you" a week.

**Items opened Jan 5 to Sep 28, by rule:**
- **Needs you:**
  - failed runs 33 (median 6 days open);
  - 14 days quiet 40 (30, the cap before moving on);
  - field loss 7; empty scrape 6; bill drop 4; chamber swap 3; special with no end date 3.
- **Known ongoing:** 14 days quiet 28 (median 47 more days); field loss 6 (63); empty scrape 1
  (91: AR's 119 empty scrapes).
- **Heads-up:** failed run 226 (each 1 day: the first 2 days of a failure before it reaches
  "needs you", and the short ones); 7 days quiet in session 77; out-of-session digest 39 (one a
  week); broken data 24; no new bills 9.
- **Ready to turn off:** 15.
- **Turn back on:** running now 38; starts soon 6.

**Known failures (revised): unchanged.** 24 caught (TN's chamber swap on day 0, freezes 13 to 15
days after the first green in-session day, empty scrapes and field losses at 2 days), 9 log only,
6 missed by design (heads-up raised each on day 0), and 1 heads-up only (MA, day 21). Dropping
duplicate heads-ups hid none of them.

#### Turn back on: did it flag every session and special start in time?

Starts checked: every regular, special and prefiling start from 2026-01-07 to 2026-12-25 (68 by
state and date). **None was missed.**
- **49:** the scraper ran through the 30 days before, so there was nothing to flag.
- **19:** it was off at some point in those 30 days, and every one was flagged ahead:
  - VA special 04-23: 21 days ahead; still off at the start.
  - GA special 06-17: 22 days ahead, and AK 3rd special 06-20: 25 days ahead. Both flags came
    from the 05-26 skipped day (below); both scrapers were back on 05-27.
  - MS special 07-15: 13 days ahead; back on that day.
  - AK 4th special 07-27: 22 days ahead, from the 07-05 skipped day.
  - MD special 08-03: 30 days ahead; back on 07-21.
  - IA special 10-02: 2 days ahead. MultiState lists it as one date, and the pause had begun on
    09-30.
  - 10 prefiling starts on 11-23 (AR, AZ, FL, IN, MT, NV, OK, TN, TX, VA), plus ME 12-02 and CA
    12-07 (the 2027 sessions): all flagged 30 days ahead, and all still off, since the scrapers
    have been paused since 09-30.
- **"Running now" also caught three sessions running while off:**
  - VI 04-02 to 06-30 (year-round, so always "in session");
  - NC 09-30 to 11-15 (MultiState's session to 12-18);
  - PR 10-02 to 11-17 (its second ordinary session).

**The noise in this list: fleet-wide skipped days.** On 05-26 and 07-05 not one of the 56 repos
ran, so every state in session got a 1-day "running now" item. That's 35 of the 44 items from
January to September, and the 05-25 week's spike. A skipped scheduler day isn't you turning a
scraper off.
- **Suggested fix (not applied, one re-run only):** when no repo runs on a day, raise one fleet
  item ("no scraper ran today"), not one per state; or count "off" only after 2 days in a row.

**The limit of this replay.** `sessions.csv` doesn't record when each source first published a
date, so the replay can't show how much notice a real weekly fetch would have given. It assumes
each date was known all along. Where the LegiScan versions show it, the first version that lists
a special:

| State | Special | Convenes | First LegiScan PDF listing it | Notice |
|---|---|---|---|---|
| ND | Special Session September 2 | 2026-09-02 | 2026-08-20 | 13 days |
| MD | Special Session August 3rd | 2026-08-03 | 2026-07-08 | 26 days |
| SD | Special Session September 25th | 2025-09-25 | 2025-08-15 | 41 days |
| OR | Special Session August 29th | 2025-08-29 | 2025-08-15 | 14 days |
| CO | Special Session August 21st | 2025-08-21 | 2025-08-15 | 6 days |
| FL | Special Session January 27 | 2025-01-27 | 2025-01-24 | 3 days |
| MO | Special Session September 3rd | 2025-09-03 | 2025-09-03 | 0 days |
| DE | Special Session August 12 | 2025-08-12 | 2025-08-15 | listed 3 days after it started |
| AK | Special Session May 21st | 2026-05-21 | 2026-07-08 | first PDF we have is after it |
| SC | Special Session May 15th | 2026-05-15 | 2026-07-08 | first PDF we have is after it |

- AK and SC say more about our download gaps than about LegiScan: there's no 2026 LegiScan PDF
  between January and 07-08.
- Next year's regular sessions were all listed in the 11-23 PDF, 40 to 140 days before they
  convene: DC 40, USA 41, most states 42 to 58, NV and OK 70, AL 71, FL 99, LA 140.
- **Two are short:** ME (convenes 2026-12-02) and CA (2026-12-07) got 9 and 14 days, from the
  same PDF. Our scrapers were already flagged for them from 11-02 and 11-07, but only because
  the replay assumes the date was known. Fetched live, the warning would have come on 11-23.
- MultiState has one version per year (2026's dated 11-26, after nearly every 2026 event), so it
  shows no notice at all. Keeping weekly versions from now on would.

#### For you to decide next

- **Turn back on:** keep "running now", or only "starts soon"?
- **Fleet-wide skipped days:** one fleet item, or "off" only after 2 days in a row?
- **The 226 one-day heads-up failed runs:** these are the first 2 days of failures before they
  reach "needs you". Keep them, or start the heads-up only on day 2?

### 2026-11-26: the timing rule, and "known ongoing" as a weekly line. Re-run once. Stopping for review.

**Already built in the last round** (as in the previous entry), unchanged:
- dropping a heads-up while the same state and kind is on "needs you";
- moving items open past 30 days to "known ongoing";
- the empty `accepted.csv`;
- the "turn back on" list and its check against every session start.

**New this round:**
- **"Known ongoing" is now shown the way the weekly section would read:** state, kind, what's
  wrong, and its day count.
- **The timing rule.**

Code: `reaudit.py` (`run_days_timed`, new `days.run_timed` / `kind_timed` columns) and
`lists.py --timing`. Tests pass (a timing test included). Nothing committed. I haven't started on
`auditor-v1-build-plan.md`.

#### The timing rule, as applied

- **Only finished runs count.** On a day when a run is still queued or in progress at midnight
  UTC, the day is "running": it neither counts toward a limit nor resets one, like an off day.
- **Over 24 hours counts as failed.** Once a run has been queued or in progress for more than 24
  hours (from `created_at`), each further day it's unfinished is a failed day.
- **The day a run finishes** takes its outcome.
- **Where "finished" comes from:** `updated_at` in the runs list isn't a finish time for older
  runs. GitHub moves it when it expires their logs: WI's March runs show `updated_at` in
  November. So for the 4,271 runs whose `updated_at` looked more than 24 hours after
  `created_at`, I fetched the real job times (`gh api .../actions/runs/<id>/jobs`, read-only, to
  `session-status/jobs/`). The cases:
  - **4,213 fetched.** 174 really ran over 24 hours: MA 67, FL 57, and 1 to 4 in each of 19
    other states.
  - **56 not fetchable (404):** one per state, each state's first run on 2026-01-07, its job
    records deleted. These are taken as finished the day they started, with their recorded
    outcome.
  - **2 never finished:** FL's and OH's scheduled runs of 2026-09-13 are still "queued", never
    picked up by a runner. Each is "running" on 09-13 and a failed day from 09-14 on.

**What it changed: little.** It changed 103 of the 18,088 state-days from 01-07:
- 61 "off" → "failed": the two runs queued since 09-13 (FL 66 days changed in all, OH 3);
- 31 "failed" → "running": a run still going at midnight, under 24 hours (mostly FL and MA);
- 6 "ok" → "failed", 3 "failed" → "ok", 1 "off" → "running", 1 "ok" → "running".

**On the lists, also little:**
- **Jan–Sep:** the heads-up worst week goes from 27 to 28 open (25 new instead of 24); failed-run
  items last a median of 7 days open instead of 6. Nothing else moves.
- **Oct–Nov:** "needs you" has 3 open, not 2. OH now fails from 09-14 instead of being off, so it
  is part of the 11-01 fleet failure item (DC, GU, MI, MP, NJ, OH, PA, USA, VI). "Turn back on"
  has 23 new items, not 25: FL and OH show as failing, not off.
- **Known failures:** identical, line for line: 24 caught, 9 log only, 6 missed by design, 1
  heads-up only.

#### The count on each list per week (revised, with the timing rule)

Weeks of 2026-01-05 to 2026-09-28 (scrapers on):

| List | Open: median | Open: worst (week of) | New: median | New: worst (week of) | New: total |
|---|---|---|---|---|---|
| Heads-up | 13 | 28 (07-13) | 9 | 25 (07-13) | 376 |
| Needs you | 11 | 25 (02-16) | 2 | 8 (01-19) | 98 |
| Known ongoing | 8 | 20 (03-02) | 0 | 9 (02-23) | 35 |
| Ready to turn off | 3 | 9 (06-01) | 0 | 3 (05-18) | 15 |
| Turn back on | 0 | 25 (05-25) | 0 | 23 (05-25) | 49 |

Weeks of 2026-10-05 to 2026-11-23 (paused; 9 states ran):

| List | Open: median | Open: worst (week of) | New: total |
|---|---|---|---|
| Heads-up | 0 | 10 (10-26) | 10 |
| Needs you | 3 | 3 (10-05) | 1 |
| Known ongoing | 1 | 1 | 0 |
| Ready to turn off | 0 | 0 | 0 |
| Turn back on | 13 | 14 (11-23) | 23 |

**"Known ongoing" as the weekly section would show it**, week of 2026-09-14. The day count runs
from the day the item went onto "needs you":
- GU quiet_14 (45 green in-session days, nothing new), day 175
- IL field_loss (abstracts still lost), day 68
- PA quiet_14 (14 green in-session days, nothing new), day 48
- TX field_loss (related_bills, not guarded, in the data repo on day 1), day 86
- VI quiet_14 (45 green in-session days, nothing new), day 43

For the week of 09-28 only GU (day 189) and KY sponsors (day 39) are left. The broken-data items
end with each state's last scrape before the 09-30 pause.

**Turn back on: unchanged.** All 68 session, special and prefiling starts are covered; none
missed. The limit and the PDF notice table are as in the previous entry (ND's 09-02 special first
appears in the 08-20 LegiScan PDF, 13 days ahead).

#### For you to decide next (unchanged from the last entry)

- Turn back on: keep "running now", or only "starts soon"?
- Fleet-wide skipped days (05-26, 07-05: no repo ran): one fleet item, or "off" only after 2
  days in a row?
- The one-day heads-up failed runs: keep them, or start the heads-up on day 2?
- **New:** should the "known ongoing" day count run from when the damage began, not from when it
  reached "needs you"? IL's abstracts were lost on 07-13: day 70 by the damage, day 68 by the
  item.

### 2026-11-26: the last rule changes, re-run once. Stopping for review.

Tamara's answers, applied (`sessions/lists.py`, revised mode with the timing rule; tests pass;
nothing committed):
- **"Off" counts only from the 2nd day in a row with no run.** A day when no repo ran at all
  (2026-05-26, 07-05) is neutral for every state, and is one heads-up line: "no scraper ran on
  <date>".
- **"Running now" stays,** under the same 2-day rule.
- **An `accepted.csv` line with kind `off`** (e.g. "paused for migration") sends that state's off
  days to the log only.
- **Heads-up failed runs start on the 2nd failed day in a row.**
- **"Known ongoing" day counts run from when the damage began:** the day after the last new data
  for a quiet item, the first damaged scrape for broken data.

FL's and OH's runs queued since 09-13 are known; Tamara decides whether to cancel them. They're
not acted on here.

#### The count on each list per week

Weeks of 2026-01-05 to 2026-09-28 (scrapers on):

| List | Open: median | Open: worst (week of) | New: median | New: worst (week of) | New: total | Last run |
|---|---|---|---|---|---|---|
| Heads-up | 7 | 21 (01-12) | 5 | 17 (01-12) | 222 | 13 open, 376 new |
| Needs you | 11 | 25 (02-16) | 2 | 8 (01-19) | 98 | same |
| Known ongoing | 8 | 20 (03-02) | 0 | 9 (02-23) | 35 | same |
| Ready to turn off | 3 | 9 (06-01) | 0 | 3 (05-18) | 15 | same |
| Turn back on | 0 | 7 (09-28) | 0 | 5 (09-28) | 13 | 25 worst, 49 new |

Weeks of 2026-10-05 to 2026-11-23 (paused; 9 states ran):

| List | Open: median | Open: worst (week of) | New: total |
|---|---|---|---|
| Heads-up | 0 | 10 (10-26) | 10 |
| Needs you | 3 | 3 (10-05) | 1 |
| Known ongoing | 1 | 1 | 0 |
| Ready to turn off | 0 | 0 | 0 |
| Turn back on | 12 | 13 (11-02) | 21 |

- **Heads-up:** failed-run items fell from 226 to 69 once they start on day 2. The 2 skipped days
  are 2 lines. The rest: quiet in session 77, the weekly out-of-session digest 39, broken data 24,
  no new bills 9.
- **Turn back on, Jan–Sep, 13 items:**
  - VA special 04-23 (from 04-03, then "running now" to 06-29);
  - VI 04-03 to 06-30 and 09-24 to 09-29 (year-round);
  - MS special 07-15 (from 07-03);
  - NC 07-03 to 07-13;
  - MD special 08-03 (from 07-04);
  - PA 09-22 to 09-29.

  The 35 one-day items from the two skipped days are gone.
- **Known failures: unchanged.** 24 caught (TN's chamber swap on day 0; freezes 13 to 15 days
  after the first green in-session day; empty scrapes and field losses at 2 days), 9 log only, 6
  missed by design, 1 heads-up only (MA, day 21).
- **Turn back on: every start still covered.** 68 starts:
  - 50: the scraper was on;
  - 3: the only off day was a day no repo ran (GA 06-17, AK 06-20 and 07-27);
  - 15: flagged ahead: VA 20 days, MS 12, IA 1 (its scraper went off with the 09-30 pause, 2
    days before its 10-02 special), and 12 at 30 days (the 11-23 prefiling starts, ME, CA).

"Known ongoing" as the weekly section would show it, week of 2026-09-14, counted from when the
damage began:
- GU quiet_14, day 219
- IL field_loss (abstracts still lost), day 70
- PA quiet_14, day 61
- TX field_loss (related_bills, not guarded, in the data repo from day 1), day 86
- VI quiet_14, day 43

### 2026-11-26: completeness rules (from the completeness audit), re-run once. Stopping for review.

Added, then re-run once (revised mode, timing rule on). New code: `sessions/bill_dates.py` (each
bill's first and last action date, read once from the last scrape it's in: 116 scrapes, 14 s) and
two rules in `lists.py`; the special end-date rule in `status.py`. Tests pass. Nothing committed.

- **Needs you, "no bills from a running session" (`no_bills_running`):** a regular or special
  session in session for 7+ green days (either source), and no bill in the scrape whose first
  action is on or after its convene date. Matched by dates, not session names.
  - Sessions from different sources starting within 3 days of each other are one session.
  - A state whose bills carry no action dates can't be judged, and is logged as such: GU.
- **Needs you, "session left while running" (`session_left`):** a whole session's bills leave the
  scrape (other sessions' bills still there) while either source has it in session, or within the
  state's tail after its end. A switch after that stays normal.
  - The departing session is placed by dates: the calendar session holding its bills' latest
    *first* action. Last actions don't work for this: they can be effective dates years ahead
    (GA's run to 2028).
- **A special with no end date takes the other source's end** when that source lists a special
  starting within 3 days; otherwise 30 days, as before.
  - MD 08-03 now ends 08-05 (MultiState).
  - ND 09-02 and SC 05-15 have no match and keep 30 days.

#### Does it catch AR, VA and GA?

- **AR (2026 session from 04-08): caught on 04-14,** 6 days in. But AR was already on "needs you"
  from 03-15 as an empty scrape (0 bills from 03-13 to 07-13), so the new rule adds a second item
  for the same problem.
- **VA (2026 regular from 01-14): not by the new rules, and it can't be.** VA had no bills at all
  until 07-14. Its runs failed or were off for the whole regular session (85 failed days, 29 off),
  so there are no green days to count. **Failed runs catch it:** VA is in the 01-09 fleet item.
  After the scraper came back on 07-14, only the special's bills (`2026S1`, 299) were scraped; the
  regular session had ended, so neither rule looks at it. *Gap:* "a session ended and none of its
  bills were ever scraped" would need an after-the-fact check, which these rules don't make.
- **GA (`2025_26` left on 06-16): not caught.** GA's 2026 session ended on 04-02 in both sources,
  and its tail is 40 days, so 06-16 (75 days later) reads as a normal switch. Under the rule as
  written that is right: by the calendars GA's session was over. To catch it would take a longer
  tail for GA, or treating a two-year session as running until its term ends.

#### New "needs you" items per week, and the ones that look wrong

- **28 new items from Jan 5 to Sep 28.** A median of 0 a week; worst week 7 (01-19, the December
  freeze).
- **"Needs you" overall:** a median of 2 new a week (unchanged). Worst week 8 → 15; 98 → 126 items
  in all. Open in a typical week: 11 → 13.
- **22 of the 28 are duplicates:** a "no bills" item for a state already on "needs you" with a
  quiet item, the same freeze counted twice (the December 2025 freeze in January: NE, NY, PA, USA,
  VT, WA, SC, WI, MD, MI, OH, IL, AK; also WY, MN, LA, NC, AR, the WI and SC specials and AK's May
  and June specials). Without
  them: a median of 0 a week, worst week 2.
- **The 6 that aren't duplicates:**
  - **UT, 01-26: right, and new.** UT's scrape held the same 8 bills from 01-19 to past 02-20
    during its session; its 824 2026 bills (first actions from 01-21) arrived only on 07-15. The
    quiet rule missed it because those 8 bills kept getting small new actions. Not in the known
    failures. *For Tamara to confirm.*
  - **FL, 04-25 (`session_left`): right.** FL's 2026 regular session left the scrape on 04-25,
    inside its tail. This is the FL event in your notes ("regular session out of the scrape; only
    2026D scraped"), caught on day 0.
  - **TN, 01-19 (8 days): plausible.** TN convened on 01-13, and its first new-session bills
    arrived on 01-27 (1,528). That fits TN's slow lag, about 10 days, more than a failure.
  - **AK, 08-02: check.** No bill with a first action on or after the 4th special (07-27) ever
    appeared. Either the special had no bills of its own, or OpenStates doesn't list AK's
    special-session bills.
  - **MA, 06-29 (3 days): a duplicate of its empty scrapes** that week.
  - **NJ, 01-29 (`session_left`): looks wrong.** The 221st Legislature ended on 01-12 and the 222nd
    convened on 01-13; the old session leaving on 01-29 is ordinary turnover, flagged only because
    it falls inside NJ's 33-day tail.
- **Two refinements would remove the wrong ones.** Not applied; your call.
  - Fold "no bills" into an open quiet or empty-scrape item for the same state (one cause, one
    line). That drops the 22 duplicates and MA.
  - Don't count a session leaving as a failure once a newer *regular* session has convened and its
    bills are in the scrape. That drops NJ; FL stays, since its newer session was a special.

#### The count on each list per week (weeks of 2026-01-05 to 2026-09-28)

| List | Open: median | Open: worst (week of) | New: median | New: worst (week of) | New: total |
|---|---|---|---|---|---|
| Heads-up | 7 | 21 (01-12) | 5 | 17 (01-12) | 218 |
| Needs you | 13 | 38 (02-09) | 2 | 15 (01-19) | 126 |
| Known ongoing | 14 | 35 (03-02) | 0 | 12 (02-23) | 53 |
| Ready to turn off | 3 | 9 (06-01) | 0 | 3 (05-18) | 15 |
| Turn back on | 0 | 7 (09-28) | 0 | 5 (09-28) | 13 |

The Oct–Nov weeks are unchanged from the last entry. The known failures are unchanged: 24
caught. The new rules aren't scored against them, since none of the 51 is of this kind.

### 2026-11-27: completeness rules refined, two new rules, re-run once. Stopping for review.

Applied, then re-run once (revised mode, timing rule on). Tests pass. Nothing committed.

**Code changes:**
- **`lists.py`:** the refinements and two new rules (below).
- **`status.py`:** the end-date borrowing now covers every session type, not only specials (see
  AR below).
- **New, `sessions/os_sessions.py`:** OpenStates' session list per state, from every version of
  each raw repo's `jurisdiction_*.json`. 1,051 sessions; 2 minutes; read-only.

**Changes:**
- **"No bills from a running session"** now waits **14** green in-session days, as quiet does.
  It **folds into an open quiet or empty-scrape item** for the same state.
- **"Session left while running"** is normal once a **newer regular session** has convened and
  its bills are in the scrape. NJ's 01-29 turnover is gone; FL's 04-25 catch stays (its newer
  session was a special).
- **A calendar special OpenStates doesn't list is log only:** "OpenStates doesn't list this
  session".
  - **Matched by start date:** an OpenStates session starting within 14 days of it. Its
    `classification` isn't reliable: MO's specials say "primary".
  - **Regular sessions always count as listed.** OpenStates lists two-year sessions whose dates go
    stale: AK's `34` ends 2025-05-21 but holds 2026's bills.
  - **Not listed:** AK's three 2026 specials, MD's 12-16 and 08-03 specials, WI's 04-14, SC's
    05-15, AL's 05-04 and IA's 10-02.
- **End-date borrowing for every session type:** a row with no end takes another source's end when
  the other source has a row of the same kind starting within 3 days. MultiState's AR 2026 row
  shows no end, so AR's session had run to the 30-day default (05-07). That made the May special's
  2 bills (first dated 04-30) look like they belonged to it. Now it ends 04-29, as in LegiScan.

**New: "missed session" (needs you).** When a regular or special session ends in every source,
and no bill first acted on inside its dates ever appeared in the scrape, it is needs you the day
after it ends, open until one appears.
- **VA 2026 regular (01-14 to 03-14): caught on 03-15.** It stayed open until 07-14, when the
  bills arrived.
- **AR 2026F (04-08 to 04-29): caught on 04-30,** thanks to the end-date change. Before it, the
  special's bills hid the miss.
- **TN 114S2 (MultiState's 05-05 to 05-07 special; OpenStates lists it): caught on 05-08.** No
  TN bill dated inside it was ever scraped (`114`'s latest first action is 04-23).
- **18 items from Jan 5 to Sep 28**, plus 7 log-only for unlisted specials (MD ×2, AL, SC, AK ×2,
  IA); "no bills" logged 5 more (WI, SC, AK ×3). 17 of the 18 come
  right after a quiet, empty-scrape or failed-runs item for the same state that ran up to the
  session's end. They are the freeze outliving the session: once the session ends, the quiet item
  stops and "missed session" carries the problem on. All the rest are also real: NM, WY, WA, WI,
  MD, NE, CT, SC, AK, VT, IL, LA, NY, AZ and UT's 2025-12-09 special.
- **The 18th:** MS's 07-15 special, whose bills arrived on 08-05, about 3 weeks late.
- **None looks wrong.** One refinement would help: carry the earlier quiet item on as the same
  line, instead of opening a new one when the session ends. Not applied.

**New: "data repo lost something" (needs you on day 1).** A bill folder (its `metadata.json`) or
a session folder disappearing from a govbot-data repo; the data repos only add, by design.
- **Inside the live repos' history:** read with `git log --no-renames --diff-filter=D`, so a moved
  folder counts as a loss too, over all 55 local clones in `govbot_data/full/`. **It never fires.
  No bill folder was ever removed after the rebuild.** (The scanner does see deletions: the 11-25
  log conversion's 9,926 deleted `logs/*.json` files show up when pointed at those paths.)
- **The 07-21 rebuild** recreated each repo from a template, so its history starts that day. I
  compared each pre-rebuild archive (`govbot-archive/<st>-legislation-pre-rebuild-2026-07-21`) with
  the live repo at the end of 07-21 UTC and at HEAD. **It fires on 07-21 for 3 states, all inside
  the known maintenance event:**
  - **USA:** 17,574 bills and **GA:** 176 (`2026_ss`). Their rebuilt repos were still empty at the
    end of 07-21 UTC and filled in afterwards. Everything is back: rebuild timing.
  - **TX: 592 bills of `891` (the 89th Legislature's 1st Called Session, 2025) dropped by the
    rebuild, and still missing today.** They were in the raw history (06-27 to 07-03) and in the
    pre-rebuild repo. *For Tamara: a real loss inside the maintenance event.* TX's `89R` (11,503
    bills, scraped once on 06-27) never reached any data repo either.
  - **Not checked:** PR. Its live repo isn't cloned in `govbot_data/full/`.
- Script: `session-status/rebuild_diff.py`; result: `csv/rebuild_lost.csv`. The deletion scan is
  `session-status/data_repo_deletions.sh`.

**UT added** to "For you to confirm" in "2026 data completeness, later": the same 8 bills held
from 01-19 to 07-15.

#### The count on each list per week (weeks of 2026-01-05 to 2026-09-28)

| List | Open: median | Open: worst (week of) | New: median | New: worst (week of) | New: total |
|---|---|---|---|---|---|
| Heads-up | 7 | 21 (01-12) | 5 | 17 (01-12) | 219 |
| Needs you | 15 | 27 (02-16) | 3 | 8 (01-19) | 123 |
| Known ongoing | 18 | 23 (06-29) | 1 | 9 (02-23) | 55 |
| Ready to turn off | 3 | 9 (06-01) | 0 | 3 (05-18) | 15 |
| Turn back on | 0 | 7 (09-28) | 0 | 5 (09-28) | 13 |

- **The completeness rules together:** 25 "needs you" items in Jan–Sep, a median of 0 a week,
  worst week 4.
  - missed session 18 (worst 3 in a week);
  - no bills 6 (UT, MN, LA, MI, MA, NC; the duplicates are folded away);
  - session left 1 (FL).
- **"Needs you" overall:** a median of 3 new a week (was 2), worst week 8 (was 15 last round,
  before folding).
- **Oct–Nov weeks: unchanged.**
- **Known failures: unchanged.** 24 caught, 9 log only, 6 missed by design, 1 heads-up only.

### 2026-11-27: carry-on for missed sessions, and PR's data-repo check

- **Carry-on applied** (`lists.py`, `carry_cover`). When a quiet, empty-scrape or failed-runs item
  runs up to a session's end, the "missed session" days go on that same line.
  - **Only 3 "missed session" items stand alone:** UT's 2025-12-09 special, VA's 04-23 special
    (ended after its failing stretch), MS's 07-15 special.
  - **A fleet failed-runs item stays open while any of its states' sessions is missed:** the
    01-09 line runs to 07-13, through VA's regular session.
- **Weekly counts, Jan 5 to Sep 28:**

  | List | Open: median | Open: worst | New: median | New: worst | New: total |
  |---|---|---|---|---|---|
  | Heads-up | 7 | 21 | 5 | 17 | 218 |
  | Needs you | 12 | 26 | 2 | 9 (06-29) | 106 |
  | Known ongoing | 15 | 22 | 0 | 9 | 39 |
  | Ready to turn off | 3 | 9 | 0 | 3 | 15 |
  | Turn back on | 0 | 7 | 0 | 5 | 13 |

  "Needs you" went from 123 to 106 new items, back to a median of 2 a week. Known failures are
  unchanged: 24 caught.
- **PR's data-repo check**, read-only, from the completeness chat's clone
  (`scratch/completeness/clones/govbot-data/pr-legislation`, a full clone):
  - no bill folder deleted since 07-21;
  - the rebuild kept all 5,115 bills.

  So across all 56 states the rule fires only on 07-21, and only TX's 592 `891` bills are a real
  loss.

### 2026-11-27: the commit

One commit on `history-scanner`, for PR #315 (open, "State history scanner, check replays and the
state auditor design"). Nothing is staged or committed. Tests pass: `sessions/test_status.py`,
`sessions/test_reaudit.py`, and the existing `history/test_scan.py`.

**What it includes:** the files below (34 once the 7 new PDFs were left out, plus `.gitignore`).

| Group | Files |
|---|---|
| `actions/openstates-scrape-audits/sessions/` (new) | `status.py`, `reaudit.py`, `action_dates.py`, `bill_dates.py`, `os_sessions.py`, `patterns.py`, `rescore.py`, `lists.py`, `deadlines.py`, `candidates.py`, `test_status.py`, `test_reaudit.py`, `__snapshots__/sessions_fixture.csv` |
| The relabel | `history/known_events.py`: the 14 overnight events now read "history scanner, unconfirmed (re-audit)" |
| Path updates (the calendar moved to `old-notes/`) | `history/daily.py`, `weekly-scraper-audit.py`, `internal/session_coverage_check.py`, `internal/audit_states.py`, `internal/audit_new_bill_flatline.py`, `internal/archive/weekly_scraper_audit.py`, `docs/src/state-status-reference.md` |
| `tamara-notes/session-dates/` | `sessions.csv`, `build_sessions_csv.py`, `README.md`, `accepted.csv` (header only), `congress/congress-119.json`, and 4 renames already staged (2 PDFs into `sources/`, 2 notes into `old-notes/`). The 7 new PDFs: left out, see below. Plus `.gitignore` (`sources/`). |
| Shared docs | `session-status-brief.md` (new), `history-analysis-plan.md` (modified), `completeness-audit-brief.md` and `auditor-v1-build-plan.md` (new) |

**Before the OK:**
- `completeness-audit-brief.md` and `auditor-v1-build-plan.md` were written by other chats; Tamara
  reviewed them.
- `history-analysis-plan.md` already had 46 added lines before this work started.

**Size:**
- Tracked changes: 13 files, 75 lines added and 24 removed.
- New files: about 0.4 MB without the PDFs. The largest is this brief (about 135 KB).
- Nothing over 1 MB.

**Checks, all clean:**
- **No secrets:** no API keys, GitHub tokens, AWS keys, private keys or passwords.
  - The one match is a mention of `DEMO_KEY`, api.data.gov's public demo key.
  - The saved congress.gov answer has no key in it: its `request` block holds only `congress`,
    `contentType` and `format`.
- **No email address.**
- **Nothing from the SSD:** no file resolves to a path under `/Volumes`, and there are no
  symlinks. The docs name SSD paths like `/Volumes/govbot-data/scratch/…` as references, as the
  other notes do. The one home-directory path (`/Users/…`, line 8 of `history-analysis-plan.md`)
  was already committed; this change adds none.
- **No cache files** (`__pycache__`).

**Proposed commit message:**

```
Session status re-audit: daily session status, run history, the four-list replay and the v1 rules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

**Committed on Tamara's OK (2026-11-27), with one change:** the 7 new calendar PDFs are left out.
- `tamara-notes/session-dates/sources/` is in `.gitignore`; the PDFs aren't redistributed.
- Their master copy is on the SSD, `/Volumes/govbot-data/session-calendars/sources/` (all 9,
  checked identical), and the session-dates README says so.
- The two PDFs that were already tracked stay tracked; only their moves are in the commit.
- `completeness-audit-brief.md` and `auditor-v1-build-plan.md` were reviewed by Tamara and are
  included.

**Left on the SSD, not committed** (`/Volumes/govbot-data/scratch/session-status/`):
- the run history (`runs/`) and job timings (`jobs/`);
- OpenStates' session lists (`os/`);
- the CSVs for DBeaver (`csv/`) and the reports (`lists.md`, `rescore.md`);
- the one-off scripts: `spotcheck.py`, `pull_runs.sh`, `pull_jobs.sh`, `data_repo_deletions.sh`,
  `rebuild_diff.py`;
- the database copy from before the re-audit (`history.before-reaudit.sqlite`).

The re-audit's tables live in `history-analysis/history.sqlite`.

### The rules for version 1

Settled 2026-11-26 by Tamara, after the replays above. This is the hand-off for whoever builds
`auditor-v1-build-plan.md`. One line per rule: **threshold** — reason. The reference
implementation and its 2026 replay are `actions/openstates-scrape-audits/sessions/` (`status.py`,
`reaudit.py`, `lists.py`). "Fit to 2026" numbers are not a blind test: freeze these settings in
January and check them against 2027.

**Ground rules**
- **The auditor recommends; Tamara acts.** It never turns a scraper on or off. In 2026 every
  pause was hers, by hand.
- **Data first:** scrapers stay on by default. Out of session isn't a reason to turn one off;
  data still arrives (actions dated 8 to 139 days after a session ends, at the 90th percentile).
- **Session status never hides a failure.** It only decides what "no new data" means; failed
  runs and broken data count in session or out.
- **Low noise is the goal.** Tamara maintains this alone, in her free time. Target: a handful of
  new "needs you" items a week. The replay gives a median of 2, worst week 8.

**Judging a day (inputs to every list)**
- **New data:** a new bill, action or vote in that day's scrapes — the scan's measure.
  Auto-saves from failed or cancelled runs count; FL and MA got data that way.
- **Green day:** a run that *finished* green that day — only finished runs count.
- **Running:** a run still queued or in progress at the end of the day; neither counts toward a
  limit nor resets one — not yet known.
- **Run over 24 hours (queued or running):** each further day is a failed day — FL and MA ran for
  days in 2026; FL's and OH's runs have sat queued since 09-13. Take the finish time from the jobs
  API, not the run's `updated_at`, which GitHub moves when it expires logs.
- **Off:** no run that day; counts only from the **2nd day in a row** — one missed scheduled run
  isn't a pause.
- **A day when no repo ran at all:** neutral for every state, plus one heads-up line — GitHub
  skipped the schedule on 2026-05-26 and 07-05; per state it was 35 false items.
- **In session:** either source says regular, special, veto or lame duck, or prefiling —
  decision 2, "either source says in".
- **Doesn't count as in session:** organizational days and informal sessions — MA's Aug–Dec
  informal session isn't one.
- **Recess:** takes days out of a regular session (an "Interim Recess <date>" note too) — NJ
  2025; IL and NY 2025.
- **Disagreement:** when the sources differ, flag it and name each source's answer — 11 states
  differ in 2026 (NC 08-31 vs 12-18).
- **A row with no end date** (any kind) takes another source's end when that source has a row of
  the same kind starting within **3 days**; otherwise assumed **30 days**, marked estimated —
  LegiScan's specials give only a start (MD 08-03: MultiState says 08-05); MultiState's AR 2026
  row shows none (LegiScan: 04-29); generous windows otherwise (decision 4).
- **An older calendar's biennium row** ends where the same source's next regular row begins —
  the newer calendar wins; else WI reads in session all of 2026.
- **A two-year legislature split across two rows** stays in session across the New Year — WI in
  MultiState.
- **Sources:**
  - LegiScan PDFs (Tamara downloads; keep every version, since specials drop off);
  - MultiState PDFs (weekly fetch after its terms check; keep every version);
  - congress.gov API;
  - hand rows for DC and the territories.
- **"Notice" can't be measured from today's history:** `sessions.csv` doesn't record when a
  source first published a date. Keep every version so it can be — e.g. ND's 09-02 special first
  appeared in LegiScan's 08-20 PDF, 13 days ahead.

**Heads-up** (read when convenient; shows what's coming)
- **Quiet:** **7** green **in-session** days (either source) with nothing new — early warning;
  lag is 1–2 days in most states, so 7 is well past normal.
- **Out-of-session quiet:** **one digest line a week** naming the states quiet 7+ days — normal
  out of session; one line, not 35.
- **Failed run:** from the **2nd** failed day in a row — a single failed night usually recovers;
  this cut 226 items to 69.
- **Broken data:** **the day it appears** — empty scrape, bill drop, field loss, broken votes,
  chamber swap. Early sight of damage that may clear on its own (all 6 by-design misses cleared
  within 3 days).
- **No new bills while actions came:** **21** green in-session days — MA's stuck bill count.
  Only for states with **no early intro deadline**; early-deadline states skip it after their
  deadline, since few new bills then is normal.
  - **Early** = both chambers' deadline within **31 days** of convening, from MultiState page 1.
  - 2026's early states: OK, FL, NH, WY, HI, NC, VA, UT, MS, AR, NE, NM, TN, LA, SD, IL, KS, AZ,
    ID, CO, MD.
- **A day when no repo ran:** one line, "no scraper ran on <date>" — fleet event, not a state's.
- **No duplicates:** a heads-up item is dropped while the same state and kind is on "needs you"
  — one place per problem.

**Needs you** (act on these)
- **Quiet in session:** **14** green in-session days (either source) with nothing new; **GU and
  VI 45, MP 21** — catches the freezes 13–15 days after the session's first green day; the
  territories meet occasionally.
- **Failed runs:** **3 days in a row** — catches the failure waves; shorter ones recover.
  - **Fleet:** **3+ states** reaching day 3 within **1 day** of each other are one item — one
    cause (01-09: 8 states; 07-18: 19).
  - **Reopen:** a failure back within **7 days** is the same item — FL and MA flapped (12 and 7
    items).
- **Empty scrape:** still empty **3 days** later — the formatter writes nothing from an empty
  scrape, so the data repo isn't damaged; most recover in a day.
- **Bill drop:** **5%+ of the bills (at least 20)** gone, still gone **3 days** from the night of
  the drop — the formatter keeps a missing bill's folder. A whole session leaving while another is
  scraped is a session switch, not a drop.
- **Field loss:** a field emptied on **half or more of the 20+ bills** that had it.
  - **A guarded field** (title, sponsorships, actions, versions, documents, abstracts,
    other_titles, subject, sources): still lost **3 days** later — `bill_guards.py` keeps last
    night's value.
  - **Any other field** (extras, other_identifiers, related_bills, …): **day 1** — it goes into
    `metadata.json` the first night (TX, KS, NH in 2026).
- **Chamber swap:** **50+** actions back under another chamber, **day 1** — the action logs only
  add lines, so a doubled action stays in the data repo for good (TN 07-02).
- **Broken votes:** an error page as a voter (1+) or 20+ roll calls emptied, **2 scrapes in a
  row** — a parsing fix can empty votes once (OK, HI).
- **Special session with no end date:** **day 14** after it convened: "check the state's site" —
  Tamara checks and adds the real end date.
- **No bills from a running session:** a regular or special session in session **14+** green days
  (either source), and no bill in the scrape whose first action is on or after its convene date.
  - Match by **dates, not session names**: states name sessions their own way. Sessions from two
    sources starting within 3 days are one session.
  - **Folds into** an open quiet or empty-scrape item for the same state: one cause, one line.
  - **Skip** a state whose bills carry no action dates (GU).
  - Reason: a session the scraper never picked up. 14 days matches quiet, and TN's lag is about
    10. It caught UT's unrecorded 2026 freeze, the same 8 bills held in session.
- **Session left while running:** a whole session's bills leave the scrape (other sessions' bills
  still there) while either source has it in session, or within the state's tail after its end.
  - Place the departing session by its bills' latest **first** action, not last action (effective
    dates run years ahead).
  - **Normal:** a switch after the tail; or once a **newer regular** session has convened and its
    bills are in the scrape (NJ's 221st → 222nd on 01-29).
  - Reason: FL's 2026 regular session dropped out on 04-25, inside its tail.
- **Missed session:** a regular or special session has ended in every source, and no bill first
  acted on inside its dates ever appeared in the scrape: needs you **the day after it ends**, open
  until one appears.
  - Reason: catches a session lost while the scraper was failing or frozen, which no "while
    running" rule can see: VA 2026 regular on 03-15, AR 2026F on 04-30, TN 114S2 on 05-08.
  - **Carry on, don't duplicate:** when a quiet, empty-scrape or failed-runs item runs up to the
    session's end, the missed session continues that same line instead of opening a new item. A
    fleet failed-runs item stays open for as long as any of its states' sessions is missed.
    In 2026 nearly every missed session was a freeze outliving its session. Carried on, only 3
    stand alone: UT's 2025-12-09 special, VA's 04-23 special, MS's 07-15 special.
- **Data repo lost something:** a bill folder (its `metadata.json`) or a session folder disappears
  from a govbot-data repo, **day 1**. Read from git (`git log --no-renames --diff-filter=D`, or
  `ls-tree` before and after), so a move counts as a loss.
  - Reason: the data repos only add, by design; any loss is a bug.
  - In 2026 it fired only for the 07-21 rebuild, a known maintenance event, across all 56 repos
    (PR checked from the completeness chat's clone). USA and GA filled in later. TX's 592 `891`
    bills never came back.
- **Fleet broken data:** the same kind on **3+ states the same day** is one item — one cause
  (06-26: 5 empty scrapes, 5 bill drops).
- **One line until it clears:** an item comes back within **2 days** → the same item, never raised
  again as new — no flapping.
- **Log only, already handled:** what `log_jsonl.SCRAPER_FAILURES` skips (ND error-page voters, TN
  emptied roll calls) — the formatter already protects the data.
- **Log only, "OpenStates doesn't list this session":** a calendar special with no OpenStates
  session starting within **14 days** of it, in any version of the raw repo's
  `jurisdiction_*.json`. Match by date: OpenStates' `classification` isn't reliable. Regular
  sessions always count as listed, since OpenStates' dates for them go stale. Applies to "no
  bills" and "missed session" — the scraper can't get what OpenStates doesn't have (AK's three
  2026 specials).
- **Log only, accepted:** `tamara-notes/session-dates/accepted.csv` (`state,kind,reason,date`;
  empty for now) sends that state + kind to the log from its date. Kind `off` covers a deliberate
  pause — Tamara decides what she lives with.

**Known ongoing** (one weekly section)
- **A "needs you" quiet or broken-data item open more than 30 days** moves here: one line a week,
  e.g. "IL field_loss (abstracts still lost), day 70", counted from when the damage began — keeps
  "needs you" for new problems; 2026's unfixed failures (median 44 days) filled it otherwise.

**Ready to turn off** (recommendations only)
- **All of these must hold:**
  - **14** green days with nothing new (GU and VI 45, MP 21);
  - out of session in **every** source, with no disagreement;
  - the latest action dated between **7 days before** the session's end and the end **+ the
    state's tail** (its 90th percentile; fleet median where unmeasured);
  - the last **3** runs green.

  Reason: the data reached the session's end, nothing is expected after the tail, and the scraper
  works. Without the lower bound, frozen states were recommended.
- **Not when a regular, special or prefiling starts within 60 days** — it recommended UT on 01-09.
- **Not when the state's quiet began the same day as 3+ other states'** — the cache bug's
  signature (IL and NY on 08-04).
- **Once per out-of-session period** — late actions reset the 14 days (UT was recommended 7
  times).
- **Before recommending, show the evidence:** each source's session end, the latest action, the
  tail, the last runs — decision 7's final checks.

**Turn back on**
- **Off 2+ days in a row while a regular, special or prefiling starts within 30 days** in any
  source (`starts_soon`) — the replay flagged all 15 starts that had the scraper off ahead of
  time, 1 to 30 days early.
- **Off 2+ days in a row while one is already running** (`running_now`) — otherwise a scraper
  switched off mid-session shows on no list (VA's special, NC, PR, VI in 2026).
- **An `accepted.csv` line with kind `off`:** that state's off days go to the log only — a
  deliberate pause ("paused for migration").

**Auditor health** (the build plan's "What it writes", item 5, and "Build order", step 6)
- **Last good run:** the date of the last run that finished and wrote the issue — a silent
  auditor looks like a quiet fleet.
- **Inputs it couldn't read:** each raw repo, run-history call, PDF or API it couldn't read, by
  name; that state is skipped and the rest still run — fail-soft, but never silently.
- **The newest LegiScan PDF's age:** a reminder when it is over **30 days** old from January to
  June — LegiScan is Tamara's download, and specials drop off it once over.
- **MultiState fetch failures:** how many weekly fetches in a row failed; it keeps the last good
  copy and says so, a reminder after a week of failures — the calendar quietly ages otherwise.

**Settings to freeze in January, check against 2027**
- quiet 7 / 14 (45 / 21);
- failed 2 (heads-up) / 3 (needs you), 7-day reopen;
- broken data 3 days, or day 1 for unguarded fields and chamber swaps;
- votes 2 scrapes;
- no new bills 21;
- early deadline 31 days;
- ongoing after 30 days;
- ready to turn off 14 days, 7-day end margin, tail p90, 60-day look-ahead, 3+ states same start;
- turn back on 30 days, off from day 2;
- special default end 30 days, check on day 14, borrow another source's end within 3 days;
- no bills from a running session 14 green in-session days, sessions within 3 days are one;
- session left: while running or within the state's tail, unless a newer regular session's bills
  are in;
- missed session: the day after the session ends;
- data repo lost something: day 1;
- OpenStates listing: a special matches a session starting within 14 days.

**Open (not settled):**
- **GA isn't caught:** `2025_26` left the scrape 75 days after its session ended, beyond its
  40-day tail. Catching it would take a longer GA tail, or treating a two-year session as running
  until its term ends.
- **A maintenance window list** (dates when the auditor tags "data repo lost something" as
  maintenance, like 07-21), so a rebuild's real losses (TX `891`) still show without looking like
  a new failure.
