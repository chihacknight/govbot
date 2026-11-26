# State auditor: design (draft)

A scheduled check that lists the states whose scrapes may not be working, so a silent failure
in the 2027 sessions is caught in days, not months. This draft comes from the state history
analysis (`history-analysis-plan.md`, sections 6 and 7). Its starting values are the settings
frozen on 2026-11-26 for the held-out test (`frozen-settings.json`, sha256 `e5c67717…0b18e`).

**Status:** design, nothing built or scheduled yet.

- Drafted overnight on 2026-11-26 while the third wave was scanned.
- Updated the same day with Tamara's decisions (section 7) and the step 5 changes ("after
  tuning").
- The blind held-out baseline is recorded in section 6, before any of those changes.

## 1. What it does

**Every day:**

1. Read the new scrapes of every state since its last run. It's the history scanner
   (`actions/openstates-scrape-audits/history/scan.py`) run incrementally from a cursor.
2. Run the checks below against each state's own settings (its **profile**).
3. Publish one list: the states that may not be working today, each with:
   - the check that fired;
   - since when;
   - what it saw;
   - two or three example bills.

**What it doesn't do:**

- fix scrapers;
- restore data;
- unpause anything;
- judge a state's data against the legislature's website.

A listed state is a prompt for a person to look, not a verdict.

## 2. The checks

Seven are ready: the history replay caught every known failure of their kind, with few or no
alarms that match nothing known. One isn't ready yet, and one is dropped for 2027. The scores in
the table are the blind ones, from before tuning (section 6 has the after-tuning scores).

**Not scrapes:** a commit under `_data/` that a scrape didn't write is left out of every check.
There are 9 in the whole year, all by hand:

- 7 "chore: clear duplicate-accumulated scrape data" commits on 07-21;
- "Delete _data/sd directory";
- NH's "fix: restore ... wiped".

They are neither freshness nor an empty scrape (`daily.is_scrape`).

| Check | Fires when | Known failures caught | Days to catch | Status |
|---|---|---|---|---|
| `no_scrape` | No scrape commit touching `_data/<st>/` for more than N days. N is per state: at most 7 in session; 7 out of session in practice. **It waits during a fleet outage:** if the silence began in a fleet alarm that names the state, it fires only once the silence passes 14 days. | 28 of 28 | 6 (worst 6) | Ready |
| `fleet_no_scrape` | 3+ states each reach 2 days without a data commit within 2 days of each other | All the shared nights (23 state gaps), none unexplained | 1 (worst 2) | Ready |
| `unchanged` | In session (the whole window), scrapes keep coming but nothing new (bill, action or vote) for N days. N is per state: 7 by default, **at most 10**. | 5 of 5 (KY, WY, IL, NC, PA) | 6 after the session starts (worst 12) | Ready |
| `empty_scrape` | A committed scrape with 0 readable bills, after one with bills | 7 of 7 | Same day | Ready |
| `field_loss` | A top-level field emptied on at least half of the 20+ bills that had it (option C's guard (c)) | 6 of 6 (IL synopses, KY sponsors, NH ×4) | Same day | Ready |
| `broken_votes` | In one scrape, 1+ roll call with an error page as a voter, or 20+ roll calls emptied | 9 of 9 (ND ×8, TN) | Same day | Ready |
| `chamber_swap` | 50+ actions in one scrape back under another chamber, same date and words | 1 of 1 (TN) | Same day | Ready |
| `no_new_bills` | In session, new actions but no new bill for 21 days | 1 of 1 (MA), but 7 unexplained alarms | 20 | **Dropped for 2027.** It needs per-state filing deadlines, and `unchanged` plus `bill_drop` cover most of it. |
| `bill_drop` | 5%+ of bills (20+) gone in one scrape **and still gone in the next**, not a whole session leaving | No test case | — | **Not ready:** no known failure to test on |

**Two levels for "no scrape".**

- **The per-state check** catches every outage, including a state that stops alone (DE, HI,
  VI).
- **The fleet check** catches a shared outage within a day or two. It's what would have flagged
  February, when about 20 scrapers stopped together. The 06-26 restart shows they had stopped
  together.
- **Both count only data commits.** Every raw repo has about 30 commits that touch only
  `.windycivi/` or workflows. VI's "Scrape data" commits since 2025-12-07 hold no data at all.

**What "in session" means:**

- The 2026 window in `tamara-notes/session-dates/session-calendar-2026.md`.
- **All year for full-time legislatures:** CA, IL, MA, MI, NJ, NY, OH, PA, WI, plus USA and DC.
- **Special sessions aren't in the calendar yet,** so they count as out of session. Decided:
  add them when the auditor is built (section 7).

## 3. Per-state settings (profiles)

Each state's profile (`profiles.py`) is computed from its **healthy days**: outside every known
failure (`known_events.py`) and every gap of more than 14 days.

| Setting | How it's set |
|---|---|
| `no_scrape`, in session | Longest healthy in-session gap + 1 day; at least 3, **at most 7** (Tamara, 2026-11-26) |
| `no_scrape`, out of session | Longest healthy out-of-session gap + 1 day; at least 7 |
| `unchanged` | Longest healthy in-session quiet run of at most 21 days + 2; at least 7, **at most 10** |

- **Gaps during a fleet-wide outage don't count as normal.** Early July's 7–13-day outage would
  otherwise have set several states' limits to two weeks.
- **A quiet run in session over 21 days is a suspected freeze,** reported and not taken as
  normal. That's how PA's 229-day freeze was found instead of being learned as PA's normal.
- **A thin state** (under 60 healthy days, or under 10 in session) takes the **fleet fallback:**
  - `no_scrape` 3 days in session, 7 out;
  - `unchanged` 7 days.
- **Every setting says how it was set.**

**Starting values** (after tuning, 2026-11-26, all 56 states).

- These are the profiles the 2027 auditor starts from (section 7, decision 6).
- **Thin states take the fleet fallback:**
  - `no_scrape` 3 / 7;
  - `unchanged` 9 (the median of the 56 states' measured values, after the 10-day cap).
- **The confirmed freezes now count as unhealthy days.** That's why many states are thin.
- The frozen values used for the blind test are kept in `frozen-settings.json`.

| State | `no_scrape` in / out of session (days) | `unchanged` (days) |
|---|---|---|
| AK, AR, AZ, CT, FL, ID, IL, KS, KY, MA, MD, MO, MS, MT, ND, NE, NH, NM, NV, OR, PA, SC, SD, TX, UT, VA, VT, WA, WI, WV, WY | 3 / 7 | 9 |
| AL, CO, DC, GU, HI, IA, LA, ME, PR, VI | 3 / 7 | 7 |
| CA, IN, MI, NC, NY, OH, OK, USA | 3 / 7 | 10 |
| DE, MP, NJ | 4 / 7 | 10 |
| GA | 4 / 7 | 7 |
| MN | 5 / 7 | 10 |
| RI | 3 / 7 | 8 |
| TN | 5 / 7 | 7 |

The other per-scrape checks have fixed limits (section 2), the same for every state.

## 4. Caveats: states whose data misleads

Some states' raw history can't be read at face value. Their caveats travel with the profile and
print with every alarm (`known_events.CAVEATS`).

- **FL** (`fl.md`, "Reading FL's raw history"). A green run is a sample:
  - `flhouse.gov`'s bot detection answers with HTTP 200;
  - House committee roll calls are lost or deleted on blocked bills (987 of 988 missing votes);
  - judge a bill by its best version ever seen;
  - 07-23 is a change point;
  - count distinct bills, never files.

  **FL's House committee vote loss is a known cost,** not a new alarm each night. Each run's
  report gets one line with the block rate and its trend instead ("direction, not presence").
- **GU:** no bill has actions, so "nothing new" is normal and `unchanged` fires all the time. GU
  needs another freshness signal (new bills or versions).
- **VI:** no data commit since 2025-12-07, behind commits that look like scrapes.
- **WY** (profile note, not a caveat): joint-committee and veto-override votes list both
  chambers, so vote counts and voter lists don't match. That's normal for WY.

## 5. Output and where it runs

- **The list:** one row per state that may not be working. Its fields:
  - state;
  - check;
  - since;
  - days;
  - what it saw;
  - examples;
  - caveats.

  States not on the list are quiet, which is not the same as healthy: a state with no profile
  yet is listed as "no profile".
- **The tables stay in SQLite** (`history.sqlite`, the same schema), so profiles and checks can
  be re-run over the whole year at any time.
- **Where it runs and where the list is posted:** open (section 7). The scan needs the full raw
  history, so the self-hosted runner next to the SSD is the natural place. A GitHub Actions run
  would need blobless clones.

## 6. How good is it? (evidence)

### Blind held-out baseline (recorded before any tuning)

- **Scored on 2026-11-26** with the settings frozen before the third wave was scanned
  (`frozen-settings.json`, sha256 `e5c67717…0b18e`).
- **29 states:** AK, AL, IA, ID, IN, KS, MD, ME, MI, MN, MO, MS, MT, NE, NV, NY, OH, OK, OR, PR,
  RI, SC, SD, USA, UT, VT, WA, WI, WV.
- **This is the honest number.** A held-out score can only be blind once. The scores after
  tuning (below) were made with the answers in hand.

| Check | Known failures caught | Days to catch, median (worst) | Alarms matching nothing known |
|---|---|---|---|
| `no_scrape` | 6 of 6 | 6 (6) | 28 |
| `unchanged` | 10 of 11 (the miss, WA, was out of session, where it doesn't run) | 6 (9) | 13 |
| `empty_scrape` | none known | — | 7 |
| `field_loss` | none known | — | 1 |
| `broken_votes` | none known | — | 0 |
| `chamber_swap` | none known | — | 1 |
| `no_new_bills` | none known | — | 2 |
| `bill_drop` | none known | — | 4 |
| Total | 39 caught, 12 missed (11 of them the shared fleet check, which isn't held out) | | 56 |

**What the 56 unmatched alarms turned out to be:**

- **About 15 are real failures nobody had written down:**
  - 13 `unchanged` alarms, each a session freeze with zero new bills, actions or votes, in WI,
    MD, KS, ID, SD, MS, WA, MN and OR;
  - KS's `field_loss`;
  - ME's empty scrape.
- **About 20 repeat a fleet alarm or are maintenance commits:**
  - 14 `no_scrape` alarms inside the July fleet outage;
  - 6 `empty_scrape` alarms on manual commits.
- **The rest are short real gaps or brief partial scrapes.**
- Before WV's freeze was added to the answer key during scoring, the totals were 38 caught and
  59 unmatched.

### Before tuning, in-sample (the 27 states the settings were made from)

- Every known failure of a ready check's kind was caught:
  - `no_scrape` and `fleet_no_scrape` within 6 days and 2 days;
  - `unchanged` within 6 days of the session starting (worst 12);
  - the per-scrape checks the same day.
- **37 unmatched alarms:**
  - 22 `no_scrape` (mostly the July fleet outage);
  - 4 `unchanged`;
  - 7 `no_new_bills`;
  - the rest 1–2 per check.

### After tuning (both samples; not blind)

The changes:

- hand commits left out;
- `no_scrape` waits during a fleet outage;
- `bill_drop` needs two scrapes;
- `unchanged` capped at 10;
- the scanner's vote fixes for USA and AZ;
- 19 confirmed known events (plan doc, "after tuning" entry).

| | In-sample before → after | Held-out blind → after |
|---|---|---|
| Caught / missed | 80 / 11 → 82 / 11 | 39 / 12 → 54 / 12 |
| Alarms matching nothing known | 37 → 26 | 56 → 16 |
| Either no-scrape check: caught, median (worst) days | 28 of 28, 2 (6) → 29 of 29, 1 (6) | 6 of 6, 1 (6) → 6 of 6, 1 (6) |
| `no_scrape` alone: median (worst) | 6 (6) → 13 (13) | 6 (6) → 13 (13) |
| `unchanged`: caught, median (worst), unmatched | 5 of 5, 6 (12), 4 → 5 of 5, 8 (9), 15 | 10 of 11, 6 (9), 13 → 23 of 24, 8 (10), 7 |

- **`no_scrape` alone is slower on purpose.** Inside a fleet outage it waits, and the fleet
  check has already reported it. Together they're no slower than before.
- **The 10-day `unchanged` cap costs about 11 in-sample alarms:**
  - 8 are MP (10-day quiet stretches; MP's own runs reached 21);
  - NJ ×2, NC ×2, CA and DE make up the rest;
  - it also shortens the worst catch from 12 days to 9.
  - Held-out, it leaves 7 short alarms (4–12 days): MI, NY and USA all on 07-31 → 08-08 (an
    August recess?), plus MN, OK and WI ×2.
  - Whether 10 is right for MP and NJ is still open. The 2027 recompute (section 7, decision 6) will show it.
- **The held-out catch count rises only because confirmed failures were added to the answer
  key.** That's not evidence that the checks got better.

## 7. Decisions (Tamara, 2026-11-26, on the reviewer's recommendations)

1. **Where it runs: GitHub-hosted Actions, not the home laptop.**
   - It has to work when the laptop is off, and it only reads git history (blobless clones).
   - **Output:** one rolling GitHub issue in `chihacknight/govbot`, rewritten each run, with
     alarms by state and evidence links, so nothing piles up. A page can come later.
2. **Long `unchanged` limits:** capped at 10 days in session.
   - WI's 22 and MN's 17 had been learned from quiet runs that were themselves freezes.
   - The after-tuning replay shows what the cap costs in alarms.
3. **Special sessions:** add them to the calendar (they're in OpenStates' session list), so
   `unchanged` runs during them.
   - FL (04-25 to 07-24) and GA (06-20) both lost their regular session from the scrape when a
     special one started.
   - Not built yet; part of the auditor build.
4. **`no_new_bills`:** dropped for 2027.
5. **Caveated losses** (FL's House committee votes): no alarm. One line per run in the report
   with the block rate and its trend.
6. **The 2027 profiles:**
   - Start each state on its 2026 profile (after tuning), with the fleet fallback for thin
     states, from day one.
   - Recompute after the first 2–3 weeks of each session.
