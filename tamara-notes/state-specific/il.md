---
name: il
description: IL's scraper was paused 2026-09-30 as "out of session" but Illinois files bills year-round, so every bill filed after 2026-09-24 was missing (found by a volunteer's ilga.gov scan). Unpaused and pinned on with keep_active. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Illinois

## Status: 🟢 Fix in flight: scraper unpaused and pinned on (`keep_active`)

## What was found (volunteer ilga.gov scan, 2026-10)

A volunteer walked every section of <https://ilga.gov/Legislation/> and checked each bill
number against `govbot-data/il-legislation` (`country:us/state:il/sessions/104th/bills/`).
Findings:

1. **11 recent bills on ilga.gov but not in our repo:** HB5817, HB5818, HB5819, HR1037–HR1044.
   Confirmed 2026-10-09: `HB5816` / `HR1036` (filed 2026-09-24) exist, everything after does not.
   The site's newest Illinois bill was also from 2026-09-24.
2. **Two document types we don't have at all:** Executive Orders (16) and Joint Session
   Resolutions (3). See "Scope" below.

## Root cause of the missing bills

- **When it stopped:** the scraper's last run that saved new data was around 2026-09-25 (the fleet monitor showed the scraper repo's last data commit ~159h before 2026-10-02).
- **The pause:** on **2026-09-30**, PR #180 paused scraping for 46 jurisdictions that LegiScan's calendar listed as out of session. Illinois was one of them, because its spring session adjourned 2026-05-31.
- **Why that's wrong for Illinois:** the General Assembly is a two-year body (104th: Jan 2025 – Jan 2027). It **files bills year-round** and holds a fall veto session.
- **Why it would have stayed paused:**
  - The daily `check-sessions.py` reads OpenStates' session dates, and OpenStates lists the 104th as ending **2025-05-31** (a known data error; see `tamara-notes/session-dates/session-dates-comparison.md`). So it would have kept Illinois paused indefinitely.
  - The weekly flatline audit only watches in-session states, and the session calendar had Illinois as out of session. So no alarm fired.
- **Timeline gap:** what happened between ~09-25 and the 09-30 pause (no new data saved) wasn't checked; the scraper repo's run logs weren't reachable from the session that found this.

## Fix

- `chn-openstates-scrape.yml` / `chn-openstates-files.yml`: `il` switched back to the active templates (`openstates-scrape`, `openstates-to-ocd-files`).
- New per-locale `keep_active: "<reason>"` setting (in `config.schema.json`). `check-sessions.py` never pauses a `keep_active` locale and makes no API call for it. Offline check: `python3 check-sessions.py --self-test`.
- `session-calendar-2026.md`: `il` marked ✅, so the weekly flatline audit now watches Illinois.
- **Going live:** the config change reaches the scraper repos via the Sunday full reconcile in `check-sessions.yml`, or right away via the "Apply Templates to State Repos" workflow (`config: both`, `states: il`).
- **Verify after the first run:** HB5817–HB5819 and HR1037–HR1044 appear in `govbot-data/il-legislation`, and the dashboard's newest IL bill moves past 2026-09-24.

## Keeping it from happening again (every state)

- `check-sessions.py` now also keeps a locale on when OpenStates shows a bill action in the last 14
  days, whatever its session dates say (`RECENT_ACTIVITY_DAYS`).
- The weekly audit's new "Behind the legislature" check flags any state, paused or active, whose
  legislature acted in the last 14 days while our newest action is 7+ days older.
- Details: `actions/openstates-scrape-audits/README.md`.

## Scope: what the Illinois scraper collects

The OpenStates `il` scraper (`scrapers/il/bills.py`, `DOC_TYPES`) collects bills (HB/SB),
resolutions (HR/SR), joint resolutions (HJR/SJR), constitutional amendments (HJRCA/SJRCA) and
appointment messages (AM).

It does **not** collect **Executive Orders (EO)** or **Joint Session Resolutions (JSR)**. This
is **left out on purpose** (decided 2026-10-09):
- Executive Orders are the Governor's orders filed with the General Assembly for the record, not legislation.
- Joint Session Resolutions are procedural; they convene a joint session.

Their absence from `il-legislation` is expected, not a data gap.

## Field audit

The volunteer's next steps (empty fields, fields on ilga.gov we don't capture, values that
differ) are investigated in `actions/openstates-scrape-audits/internal/il_field_audit.py`, with
the report alongside it in `internal/audit_output/`.

## Related

- `tamara-notes/session-dates/session-dates-comparison.md`: the OpenStates IL session-date mismatch.
- `tamara-notes/archived_docs/paused-states-audit-2026-10.md`: the audit behind PR #180.
