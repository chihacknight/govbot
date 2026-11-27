# Session dates

`sessions.csv` is the legislative calendar: one row per session or dated event (regular,
special, veto, reconvene, organizational, informal, recess, or `none` for no regular session),
with the source each row came from. `build_sessions_csv.py` builds it from what is in this folder.
Don't edit the CSV by hand: a rebuild overwrites it. Corrections go in the script's `MANUAL` rows.

```
sources/legiscan/<year covered>/<updated date>.pdf     LegiScan session calendars
sources/multistate/<year covered>/<updated date>.pdf   MultiState session-dates PDFs
congress/congress-<n>.json                             congress.gov API, /v3/congress/<n>
old-notes/                                             the hand-written calendars sessions.csv replaced
```

## The PDFs live on the SSD, not in git

The calendar PDFs are LegiScan's and MultiState's, so they aren't redistributed: `sources/` is in
`.gitignore`. The master copy is on the SSD, `/Volumes/govbot-data/session-calendars/sources/`
(same layout), and the builder reads a working copy in `sources/` here. Two older LegiScan PDFs
(`sources/legiscan/2026/2026-07-08.pdf` and `2026-08-20.pdf`) were committed before this rule and
stay tracked. `sessions.csv` is committed, so a fresh clone has the calendar; to rebuild it, copy
`sources/` from the SSD first.

## Adding a new calendar

1. Save the PDF as `sources/<legiscan|multistate>/<year it covers>/<YYYY-MM-DD>.pdf`, here and in
   the SSD copy. The date is
   the one the PDF says it was updated: LegiScan prints "Updated <date>" at the top, MultiState
   "last updated: <date>". LegiScan's calendar for next year usually comes out in November, so
   `11-23-2026_2027_Session_Calendar.pdf` became `sources/legiscan/2027/2026-11-23.pdf`.
2. Keep the older versions. The newest PDF for a year gives its regular sessions, but LegiScan
   drops a special session once it's over, so specials and other dated events are kept from
   every version.
3. Run `python3 build_sessions_csv.py`. It needs poppler (`pdftohtml`, `pdftotext`), and it stops
   with a message if a file is named or placed wrong.
4. Check what changed: `git diff sessions.csv`.

For Congress, save the API's answer for `/v3/congress/<n>` as `congress/congress-<n>.json` and
update `CONGRESS_FETCHED` in the script.

## accepted.csv: problems Tamara has accepted

One row per known problem she has decided to live with: `state,kind,reason,date`. `kind` is a
"needs you" rule (`quiet_14`, `empty_scrape`, `bill_drop`, `field_loss`, `chamber_swap`,
`broken_votes`, `failed_3`); `date` (YYYY-MM-DD) is when it was accepted. From that date that
state's items of that kind go to the log only, not to "needs you". Edit it by hand; it starts empty.
For example: `il,field_loss,IL abstracts gone since 2026-07-13; OpenStates issue filed,2026-12-01`.

## Who reads what

- `sessions.csv` is read by `actions/openstates-scrape-audits/sessions/status.py`, the daily
  session status.
- `old-notes/session-calendar-2026.md` is still read by older scripts: `weekly-scraper-audit.py`
  (run by the weekly audit and daily error-digest workflows), `history/daily.py` and three
  scripts under `internal/` (`session_coverage_check.py`, `audit_states.py`,
  `audit_new_bill_flatline.py`; plus a copy in `internal/archive/`). Moving them to
  `sessions.csv` is later work.
