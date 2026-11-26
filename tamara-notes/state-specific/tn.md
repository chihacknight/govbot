---
name: tn
description: TN's scraper sometimes saves roll calls with no voters (6,787 votes, mostly 2026-07-02), then the names return. govbot works around it with a per-state rule in log_jsonl.py; delete that rule once OpenStates fixes the scraper. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Tennessee

## Status: 🟡 Scraper bug, worked around in govbot, not reported upstream yet

## What's wrong

The OpenStates `tn` scraper sometimes saves a roll call with **an empty voter list**. The
vote's date, motion and result are still there, and the names come back in later scrapes.
Examples from the raw history (`govbot-openstates-scrapers/tn-legislation`), session 114S1,
2025-01-29 House committee votes:

- HB 6005: `['Baum', 'Boyd', …] → []`
- HB 6002: `['Baum', 'Boyd', …] → []`
- HB 6003: `['Bricken', 'Brooks', …] → []`

Found 2026-11-25 while converting `tn-legislation` to the JSONL logs (run 2 of the conversion,
report at `/Volumes/govbot-data/scratch/backfill/reports/run2.md`). 6,787 votes went from
names to empty, over 63 nights. 5,839 of them were on 2026-07-02 alone; others were spread
through July onward. In today's latest raw scrape, the names are back.

Root cause not traced into the scraper source yet. It's probably a vote page that failed to
load or changed shape, parsed as "no voters" instead of an error.

**Not every change to an empty roll call is a failure.** In OK
(`HB2374 ['STRIKE THE TITLE - ADOPTED'] → []`) and HI (`GM730 ['Senator(s'] → []`), the scraper
is fixing its own parsing: the "voter" was never a person. That's why this is a TN-only rule,
not a general one.

## Workaround in govbot

`actions/format/utils/log_jsonl.py` has a per-state table of scraper-failure rules. TN's entry
treats a vote version as not scraped that night if its roll call is empty while the last
logged version has voters. Status as of 2026-11-25: added in PR #308 (`_tn_empty_roll_call`,
tested in `test_log_jsonl.py`; see `tamara-notes/processes/workstreams/shared-docs/jsonl-log-conversion-results.md`,
section 3). Without it, TN's logs would show an empty roll call as current on about 6,900 votes.

A TN vote that really has no voters would also be skipped while an earlier version has names.
No real case has been seen, but check the skipped-versions count in each conversion report.

## What would actually fix this

1. File the bug with OpenStates (`openstates/issues`; see the contribution notes in memory).
   Include the three examples and the 2026-07-02 night. Ask for the scraper to fail, or skip
   the vote, when the roll-call page can't be read, rather than saving an empty voter list.
2. Or fix it ourselves: a PR to `openstates-scrapers` (`scrapers/tn/`).

**When the fix is merged and live, delete TN's entry from the table in `log_jsonl.py`** (and
its test), then update this file and the README index.

## Timeline

- 2026-06-26 onward: empty roll calls in the raw scrapes, worst on 2026-07-02 (5,839 votes).
- 2026-11-25: found during the JSONL log conversion. Per-state workaround agreed.

## Related

- [`nd.md`](nd.md): the other state with a scraper failure caught by the same table (ND
  "Service Unavailable" voters). Found in the same investigation.
