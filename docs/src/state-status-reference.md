# State Status Reference

The master list of all 56 jurisdictions (50 states, DC, federal, 4 territories). Each row says
whether the legislature is in session, whether we're scraping it, when new data last landed,
and whether the scraper works. **If a row and another doc disagree, this page wins.**

Detail lives in one file per state under
[`tamara-notes/state-specific/`](https://github.com/chihacknight/govbot/tree/main/tamara-notes/state-specific),
linked from the last column. Older tracking docs are in
[`tamara-notes/archived_docs/`](https://github.com/chihacknight/govbot/tree/main/tamara-notes/archived_docs)
for history only.

## Right now (checked 2026-11-24)

- **No scraper has run since 2026-10-29.** The 9 active scrapers have failed every day since
  2026-10-30. GitHub's `ubuntu-latest` runner moved to Ubuntu 26.04, which has no Python 3.9,
  and `actions/scrape/action.yml` asks for `python-version: "3.9"`. The run stops at "Setup
  Python", before scraping starts. (States flagged `runner: self-hosted` are hit too, because
  scheduled runs use GitHub-hosted runners unless `use-self-hosted: true` is passed.) The daily
  digest (issue #202) lists all 9 under "never completed", but no issue or fix exists yet.
- **47 scrapers are paused on purpose** since 2026-09-30 (PR #180), during the move to the new
  data layout. Don't unpause a state to fix missing recent bills.
- So **every state's newest bill is from 2026-10-29 or earlier.**

## Columns

- **In session**: ✅ / ⏸️. From
  [`session-calendar-2026.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/session-dates/old-notes/session-calendar-2026.md)
  (LegiScan, Aug 20 PDF, checked by hand on 2026-09-29). Re-checked 2026-11-24: USA is in
  its lame-duck session (back since Nov 9); no other special sessions found. Territories GU,
  MP and VI meet all year.
- **Scraping**: ✅ if `actions/pipeline-manager/chn-openstates-scrape.yml` gives the state the
  `openstates-scrape` template, ⏸️ if `openstates-scrape-paused`.
- **Last new data**: date of the last `🕷️ Scrape data for <state>` commit in
  `govbot-openstates-scrapers/<state>-legislation`. A commit is only made when the bills changed,
  so an old date on a working state can just mean nothing changed.
- **Bills, last 7 days**: new distinct bills found, summed over the last 7 days *that have data*
  (not the last 7 calendar days), from
  `actions/openstates-scrape-audits/output/weekly_bill_counts.json` (as of 2026-11-22). Read it
  next to "Last new data": the active states' counts are from late October.
- **Healthy**: ✅ works · ❌ broken · 🟡 works with a known problem. For active states, based on the
  latest run. For paused states, based on their final run before the pause (2026-09-29, PR
  2026-10-01). Those were checked one by one on 2026-10-03; nothing has run since.
- **Last checked**: when this row was last verified against GitHub. Treat a row older than a
  month as unknown.
- **Notes**: the short version. The state file has the full story.

For failure-type codes (`S6_VALIDATION`, `P1_SHRINKING_OUTPUT`, …) see
[`scrape-failure-types.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/archived_docs/scrape-failure-types.md).

## The list

| State | In session | Scraping | Last new data | Bills, last 7 days | Healthy | Last checked | Notes |
|---|---|---|---|---|---|---|---|
| AK | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | One session ("34") covers the whole 2-year Legislature, so the 2026 special sessions are included. |
| AL | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| AR | ⏸️ | ⏸️ | 2026-08-21 | — | ✅ | 2026-11-24 | Current session (2026S1) has only 2 bills; a small count is correct. |
| AZ | ⏸️ | ⏸️ | 2026-09-29 | — | 🟡 | 2026-11-24 | Final run was clean, but only on our custom image `az-fix-test`. The 09-30 pause sync removed that image, and upstream PR #5742 was closed unmerged, so AZ will break again when unpaused. [`az.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/az.md) |
| CA | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| CO | ⏸️ | ⏸️ | 2026-08-26 | — | 🟡 | 2026-11-24 | Final run hit a real 429 rate limit. Low priority. [`co.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/co.md) |
| CT | ⏸️ | ⏸️ | 2026-09-25 | — | ✅ | 2026-11-24 | |
| DC | ✅ | ✅ | 2026-10-29 | 70 | ❌ | 2026-11-24 | Down since 10-30 (Python 3.9, see top). Clean on 10-29 (1,937 bills). |
| DE | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| FL | ⏸️ | ⏸️ | 2026-08-07 | — | ❌ | 2026-11-24 | Final runs were cancelled after waiting 24h for a self-hosted runner. Runs on our custom image `fl-fix-test`; upstream PR #5724 was closed unmerged on 2026-08-08. `flhouse.gov` bot detection loses House committee votes. [`fl.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/fl.md) |
| GA | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | Data was corrupted by git conflict markers on 2026-07-21 and replaced by a clean run; none at HEAD now (see "Open across states"). |
| GU | ✅ | ✅ | 2026-10-29 | — | ❌ | 2026-11-24 | Down since 10-30 (see top). Before that: a bill version's empty `note` fails validation (`S6_VALIDATION`), still happening on 10-29. [`gu.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/gu.md) |
| HI | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | Text extraction (not scraping) is blocked by Cloudflare. |
| IA | ⏸️ | ⏸️ | 2026-09-24 | — | ✅ | 2026-11-24 | |
| ID | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | May undercount finished sessions (see "Open across states"). |
| IL | ⏸️ | ⏸️ | 2026-09-24 | — | ✅ | 2026-11-24 | Needs self-hosted. Executive Orders and Joint Session Resolutions are not collected, by design. [`il.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/il.md) |
| IN | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| KS | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| KY | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| LA | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| MA | ⏸️ | ⏸️ | 2026-08-07 | — | ❌ | 2026-11-24 | Final runs were cancelled after waiting 24h for a self-hosted runner. [`ma.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/ma.md) |
| MD | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | May undercount finished sessions (see "Open across states"). |
| ME | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| MI | ✅ | ✅ | 2026-10-29 | 47 | ❌ | 2026-11-24 | Down since 10-30 (see top). Clean on 10-29 (4,242 bills). |
| MN | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| MO | ⏸️ | ⏸️ | 2026-09-27 | — | ✅ | 2026-11-24 | |
| MP | ✅ | ✅ | 2026-10-29 | 19 | ❌ | 2026-11-24 | Down since 10-30 (see top). Clean on 10-29 (353 bills); blank-title fix merged upstream (#5744). |
| MS | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| MT | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | No regular session in 2026. |
| NC | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | Needs self-hosted. |
| ND | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| NE | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| NH | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | The site blocks scraping 6am–9pm ET; runs at night work. Scraped without `--fastmode` (PR #95). |
| NJ | ✅ | ✅ | 2026-10-29 | 286 | ❌ | 2026-11-24 | Down since 10-30 (see top). Clean on 10-29 (11,384 bills). |
| NM | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | Final run clean: 812 bills over HTTPS. The July FTP outage no longer applies (the scraper doesn't use FTP now). |
| NV | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | No regular session in 2026. About 1,000 bills from 2025 were never backfilled. |
| NY | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| OH | ✅ | ✅ | 2026-10-29 | 40 | ❌ | 2026-11-24 | Down since 10-30 (see top). Clean on 10-29 (2,614 bills). |
| OK | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| OR | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| PA | ✅ | ✅ | 2026-10-29 | 397 | ❌ | 2026-11-24 | Down since 10-30 (see top). The October block on our proxy had cleared: 10-29 scraped 5,259 bills, but the shrink guard held the commit (5,259 vs 5,264 saved). In session until about 11-30. [`pa.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/pa.md) |
| PR | ⏸️ | ⏸️ | 2026-10-01 | — | ✅ | 2026-11-24 | Regular session ended 06-30. |
| RI | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| SC | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| SD | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| TN | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| TX | ⏸️ | ⏸️ | 2026-09-27 | — | ✅ | 2026-11-24 | No regular session in 2026. Blocks GitHub's IPs, yet the config has no `runner: self-hosted`; check before unpausing. See [`tx-backfill-runbook.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/archived_docs/tx-backfill-runbook.md). |
| USA | ✅ | ✅ | 2026-10-29 | 155 | ❌ | 2026-11-24 | Down since 10-30 (see top). Clean on 10-29 (19,782 bills); Senate vote fix merged upstream (#5847). [`usa.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/usa.md) |
| UT | ⏸️ | ⏸️ | 2026-08-12 | — | ❌ | 2026-11-24 | Final run: `CommandError: no sessions`. Not root-caused. May also undercount finished sessions. [`ut.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/ut.md) |
| VA | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| VI | ✅ | ✅ | 2026-10-29 | — | ❌ | 2026-11-24 | Down since 10-30 (see top). Before that: 0 bills, `billtracking.legvi.org:8082` unreachable (still true on 10-29). [`vi.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/vi.md) |
| VT | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| WA | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | |
| WI | ⏸️ | ⏸️ | 2026-09-26 | — | ❌ | 2026-11-24 | Final run hit GitHub's 6-hour limit. Probably needs self-hosted and a longer timeout, like FL. [`wi.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/wi.md) |
| WV | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | Needs self-hosted. |
| WY | ⏸️ | ⏸️ | 2026-09-29 | — | ✅ | 2026-11-24 | May undercount finished sessions (see "Open across states"). |

**Totals:** 9 scraping, all ❌ because of the Python 3.9 failure; with that fixed, 3 of them
would still have a problem (GU, PA, VI). 47 paused: 41 ✅, 2 🟡 (AZ, CO), 4 ❌ (FL, MA, UT, WI).

## Open across states

Problems that affect more than one state. "Verified" means checked on the date given.

1. **All scrapers fail at "Setup Python" (verified 2026-11-24).** See "Right now". The fix
   belongs to the scraper-fixes work, not this page.
2. **Conflict-marker bug is still in the code (verified 2026-11-24).** On a `git pull` conflict,
   `actions/scrape/action.yml` (around line 634) runs `git checkout --ours ... || true`, which
   can silently fail and commit files full of `<<<<<<<` markers. That's what corrupted GA on
   2026-07-21. A fix (#100) merged on 2026-07-27 and was reverted the same day; the revert
   doesn't say why. A grep of all 56 raw repos and all 56 `govbot-data` repos (local clones from
   2026-11-24) found **no** conflict markers at HEAD, so no data is corrupted today.
   History: [`critical-merge-conflict-corruption.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/archived_docs/critical-merge-conflict-corruption.md).
3. **Raw repos keep duplicate files (verified 2026-11-24 for PA).** Each scrape gives every bill a
   new file name, and cancelled runs never clean up. PA's raw repo has 53,685 files for 5,264
   bills. `actions/format` removes the duplicates, so the published data is fine; it's disk
   growth in the raw repos.
4. **Possible undercount of finished sessions in ID, MD, UT, WY (not re-checked since July).**
   Confirmed for WY in July (its API leaves out signed/enrolled bills); suspected for the others.
5. **Text extraction treats any single failed bill as a failed job (not re-checked since July).**
   NM's 809-of-812 run looked like a total failure. Design note:
   `actions/extract/docs/error-log-design-note.md`, not built.

## Machine-readable bill text (2026-07-02 audit, not re-checked)

A one-time snapshot of which file formats each state publishes bill text in. Formats rarely
change, so it isn't on the same schedule as the list above.

| State | Formats | State | Formats | State | Formats |
|---|---|---|---|---|---|
| AK | ✅ text/html, pdf | MA | ❌ pdf only | SC | ✅ text/html, docx |
| AL | ❌ pdf only | MD | ❌ pdf only | SD | ✅ text/html, pdf |
| AR | ❌ no bills yet as of audit | ME | ❌ pdf only | TN | ❌ pdf only |
| AZ | TBD | MI | ✅ pdf, text/html | TX | ✅ text/html, pdf |
| CA | ✅ text/html, pdf | MN | ✅ text/html | USA | ✅ text/xml, pdf |
| CO | ❌ pdf only | MO | ❌ pdf only | UT | ✅ text/xml, pdf |
| CT | ❌ pdf only | MP | ❌ pdf only | VA | ❌ no bills yet as of audit |
| DC | ❌ pdf only | MS | ✅ text/html, pdf | VI | ❌ pdf only |
| DE | ✅ pdf, text/html | MT | ❌ no version links | VT | ❌ pdf only |
| FL | ❌ pdf only | NC | ❌ pdf only | WA | ❌ no version links |
| GA | ❌ pdf only | ND | ❌ pdf only | WI | ✅ pdf, text/html |
| GU | ❌ pdf only | NE | ❌ pdf only | WV | ✅ text/html |
| HI | ❌ no bills yet as of audit | NH | ❌ no version links | WY | ❌ pdf only |
| IA | ❌ pdf only | NJ | ✅ text/html, pdf | | |
| ID | ❌ pdf only | NM | ❌ no bills yet as of audit | | |
| IL | ✅ pdf, text/html | NV | ❌ pdf only | | |
| IN | ❌ pdf only | NY | ✅ text/html, pdf | | |
| KS | ✅ pdf, text/html | OH | ✅ pdf, text/html | | |
| KY | ❌ pdf only | OK | ❌ pdf only | | |
| LA | ❌ pdf only | OR | ❌ pdf only | | |
| | | PA | ✅ pdf, text/html, msword | | |
| | | PR | ✅ msword | | |
| | | RI | ❌ pdf only | | |

## Keeping this page current

- Update a row when you learn something about that state, and set its "Last checked" date.
  Put the long version in the state's file under `tamara-notes/state-specific/` (start one from
  the [index](https://github.com/chihacknight/govbot/blob/main/tamara-notes/state-specific/README.md)
  if it doesn't exist).
- A green ✅ on a GitHub run is not proof. A run can say "success" while falling back to old
  data. Check the run's scrape summary for the failure type and bill count.
- Sources used for the 2026-11-24 check: `gh run list` on every
  `govbot-openstates-scrapers/<state>-legislation` repo, the logs of each active state's last
  successful run, the 2026-10-03
  [paused-states audit](https://github.com/chihacknight/govbot/blob/main/tamara-notes/archived_docs/paused-states-audit-2026-10.md),
  and local clones of all 112 repos on the `govbot-data` drive.
- Older history: [`hosting-path-history-2026-07.md`](https://github.com/chihacknight/govbot/blob/main/tamara-notes/archived_docs/hosting-path-history-2026-07.md)
  (which runner each broken state used in July), and the retired tracking docs
  `not-working.md`, `working-in-session.md`, `working-out-of-session.md`, `morning-todo.md`,
  `pending-branches.md` and `upstream-pr-todo.md`, all in `archived_docs/`.
