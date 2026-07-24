# PDF Visual-Markup Audit

Audits how often bill PDFs from each "PDF-only" state (no HTML/XML alternative,
per the Machine-Readable Bill Text column in docs/src/state-status-reference.md,
sourced from the now-archived `bill-format-audit.md`) show detectable redline
(strikethrough/underline) markup — the signal that decides whether a document
needs full-fidelity handling (e.g. handing the raw PDF to a vision-capable
model) versus plain-text extraction being trustworthy on its own.

Run with `actions/extract/scripts/audit_pdf_visual_markup.py`, which samples
up to 10 bills per state from the most recent session in `govbot-data`,
downloads each bill's earliest and latest available PDF version directly from
its original government source, and checks for real drawn line/rect objects
overlapping text (the same `has_visual_markup` check used in production
extraction — see `actions/extract/utils/pdf_extractor.py`).

## Results (394 documents checked across 27 of 28 PDF-only states)

| State | Checked | Markup | % | Notes |
|---|--:|--:|--:|---|
| AL | 16 | 16 | 100 | |
| CO | 20 | 13 | 65 | |
| CT | 14 | 14 | 100 | |
| DC | 18 | 3 | 17 | |
| FL | 9 | 9 | 100 | |
| GA | 20 | 0 | 0 | |
| GU | 10 | 10 | 100 | |
| IA | 10 | 3 | 30 | |
| ID | 11 | 11 | 100 | |
| IN | 15 | 0 | 0 | |
| KY | 12 | 11 | 92 | |
| LA | 19 | 0 | 0 | |
| MA | 10 | 1 | 10 | |
| MD | 15 | 14 | 93 | |
| ME | 8 | 0 | 0 | |
| MO | 11 | 4 | 36 | |
| MP | 12 | 1 | 8 | 1 error |
| NC | 20 | 18 | 90 | |
| ND | 20 | 20 | 100 | |
| NE | 14 | 12 | 86 | |
| NV | 20 | 16 | 80 | |
| OK | 17 | 16 | 94 | |
| OR | 14 | 13 | 93 | |
| RI | 10 | 10 | 100 | |
| TN | 17 | 9 | 53 | |
| VT | 14 | 14 | 100 | |
| WY | 18 | 11 | 61 | |
| VI | 0 | — | — | Connection timeout to a non-standard port (8082); URL pattern (`/preview/Bill%2F...`) looks like it may not even be a direct PDF link. Not investigated further — one small territory, not worth blocking on. |
| **TOTAL** | **394** | **249** | **63** | |

## Reading

- **Consistently high (~85-100%)**: AL, CT, FL, GU, ID, MD, ND, NE, NC, OK, OR, RI, VT, KY. These states' PDF generators appear to always draw redline-style marks, even on "as introduced"/"filed" versions that haven't been amended yet -- possibly a house style (e.g. always underlining new/added statutory language on first introduction), not just amendment tracking. Full-fidelity handling should be the default for these, not the exception.
- **Consistently zero**: GA, IN, LA, ME (0% across 8-20 samples each). Plain text extraction is likely trustworthy for these without special handling.
- **Mixed**: CO, DC, IA, MA, MO, MP, TN, WY, NV -- markup detected on a meaningful minority to majority of documents. These likely need the geometry check run per-document (which production already does) rather than a static per-state assumption either way.

## Caveats

- Sample is skewed toward each state's *most recent* session only, and mostly toward whatever version types happened to be available (many states only had one PDF version per bill this early in getting government scraped, so "earliest vs. latest version" comparison wasn't always possible).
- This doesn't distinguish *why* markup is detected -- a states with a "100%" rate could be drawing lines for something other than redline (underlining bill numbers, etc.), though spot-checks against ID (H0493) and the synthetic clean-PDF test suggest the detector is behaving correctly, not over-firing on unrelated marks.
- VI is an open gap (see above).

## Related finding, not part of this audit

While digging into a separate reported issue, found that **SD's HTML bill
pages are JS-rendered loading shells** (a Vue.js SPA) -- `text/html` versions
return "please enable JavaScript" boilerplate, not real bill text. SD also
serves working PDFs for the same bills, but production's format preference
(`text/xml > text/html > application/pdf`) picks the broken HTML over the
working PDF, since nothing currently detects the HTML is a placeholder.
Spot-checked MN and WV (the two states listed as HTML-only, no PDF fallback,
per the now-archived `bill-format-audit.md`) and both show genuine real content -- this appears
specific to SD's site, not a systemic HTML-only-states problem. Not fixed as
part of this audit; tracked separately.
