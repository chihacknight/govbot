---
name: il
description: IL is out of session and its scraper is paused on purpose while the team migrates scraping to a new system, so bills filed after 2026-09-24 are expected to be missing for now. A volunteer's ilga.gov scan led to a field audit. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Illinois

## Status: ⏸️ Paused on purpose (out of session; scrapers paused during the migration to a new system)

## What was found (volunteer ilga.gov scan, 2026-10)

A volunteer walked every section of <https://ilga.gov/Legislation/> and checked each bill
number against `govbot-data/il-legislation` (`country:us/state:il/sessions/104th/bills/`).
Findings:

1. **11 recent bills on ilga.gov but not in our repo:** HB5817, HB5818, HB5819, HR1037–HR1044.
   Confirmed 2026-10-09: `HB5816` / `HR1036` (filed 2026-09-24) exist, everything after does not.
   The site's newest Illinois bill was also from 2026-09-24.
2. **Two document types we don't have at all:** Executive Orders (16) and Joint Session
   Resolutions (3). See "Scope" below.

## Why those bills are missing

Expected, not a bug. Illinois is out of session, and on 2026-09-30 (PR #180) the team paused the
scrapers on purpose while everything moves to a new system. Our newest Illinois bill is from
2026-09-24; the bills filed since will come in once scraping runs on the new system.

(A first reading treated this as a bug and pinned Illinois "on" (PR #214) plus added a keep-on rule
and a "behind the legislature" alarm (PR #215). Both were undone once the migration pause was
confirmed. None of it reached the live scrapers: the session-check workflow that applies config has
been disabled since July.)

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
