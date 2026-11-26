---
name: il
description: IL is out of session and its scraper is paused on purpose while the team migrates scraping to a new system, so bills filed after 2026-09-24 are expected to be missing for now. Michael Neuman's ilga.gov scan led to a field audit. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Illinois

## Status: ⏸️ Paused on purpose (out of session; scrapers paused during the migration to a new system)

## What was found (Michael Neuman's ilga.gov scan, 2026-10)

**Michael Neuman** walked every section of <https://ilga.gov/Legislation/> and checked each bill
number against `govbot-data/il-legislation` (`country:us/state:il/sessions/104th/bills/`),
shared in Slack. Findings:

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

Michael's proposed next steps (empty fields, fields on ilga.gov we don't capture, values that
differ) are investigated in `actions/openstates-scrape-audits/internal/il_field_audit.py`, with
the report alongside it in `internal/audit_output/`.

## The synopsis (`abstracts`) disappeared from the scrape on 2026-07-13

Status: 🟡 Scraper regression, not reported upstream yet. Found 2026-11-25 by replaying the raw
history (`/Volumes/govbot-data/scratch/backfill/field_loss.py`).

- **What:** until the 2026-07-01 scrape, every IL bill carried the official synopsis as its
  `abstracts`. Example: SB2310, "Amends the Public Utilities Act. Changes the name of the
  Retail Electric Competition Article…". From the 2026-07-13 22:55 scrape on, no bill has one:
  8,648 of 8,648 lost it, and 0 of 400 sampled bills in the latest scrape (2026-09-25) have it.
- **This explains two things already in the repo:**
  - The field audit's finding that the synopsis is "never stored". It was stored until July.
  - `scripts/build_il_summaries.py`, which pulls "SYNOPSIS AS INTRODUCED" out of each bill's PDF
    for the dashboard. It works around this regression.
- **Why `il-legislation` has none:** the data repo was created on 2026-07-21, eight days after the
  loss, so no `metadata.json` ever had an abstract. Option C's empty-field guard (PR #311) had
  nothing to keep.
- **Possible cause, unconfirmed:** IL moved to the self-hosted runner on 2026-07-14, the day after.
  A different scraper image or settings might have dropped the field. Not traced.
- **Two empty scrapes were committed just before:** 2026-07-03 04:46 and 2026-07-13 21:00 have
  **0 bill files** in `_data/il/`. They show up in the history as green runs. A case for the
  state auditor.
- **Recovery: wanted** (Tamara, 2026-11-25). The synopses for the 8,648 bills scraped by 07-01
  are in the raw history, to be restored into `metadata.json`. Getting as much information about
  each bill as possible, from non-PDF sources first, is the next major project, and a structured
  synopsis is far more reliable than one pulled out of a PDF. Bills filed after 07-01 still need
  the PDF route until the scraper is fixed.
- **Fix:** report it to OpenStates (`openstates/issues`) with the SB2310 example and the dates.
  Check first whether the `il` scraper still reads abstracts.

## Related

- `tamara-notes/session-dates/session-dates-comparison.md`: the OpenStates IL session-date mismatch.
- `tamara-notes/archived_docs/paused-states-audit-2026-10.md`: the audit behind PR #180.
