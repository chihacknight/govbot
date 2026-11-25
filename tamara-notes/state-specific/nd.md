---
name: nd
description: ND's scraper saves "Service Unavailable" as a voter's name on nights the legislature's site is down (6 nights, ~1,150 votes each). govbot works around it with a per-state rule in log_jsonl.py; delete that rule once OpenStates fixes the scraper. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# North Dakota

## Status: 🟡 Scraper bug, worked around in govbot, not reported upstream yet

## What's wrong

On nights when `ndlegis.gov` is down or overloaded, the OpenStates `nd` scraper doesn't fail.
It saves the error page's text as a voter. Roll calls come back with a voter named
**"Service Unavailable"**, and the right names return the next night. Example from the raw
history (`govbot-openstates-scrapers/nd-legislation`), HB 1626, 2026-01-22, Motion for Final
Passage: `['Daniel R. Vollmer'] → ['Service Unavailable']`.

Found 2026-11-25 while converting `nd-legislation` to the JSONL logs (run 2 of the conversion,
report at `/Volumes/govbot-data/scratch/backfill/reports/run2.md`). Counted in the converted
logs, by the night the bad version was first seen:

| Night | Votes with a "Service Unavailable" voter |
|---|---|
| 2025-12-30 | 1,137 |
| 2026-04-22 | 1,149 |
| 2026-04-30 | 1,166 |
| 2026-06-20 | 1,166 |
| 2026-06-24 | 1,166 |
| 2026-08-11 | 34 |

That's 5,818 bad versions on 1,170 of ND's 2,180 votes. Each bad night garbles different
voters, so no two bad versions match.

Root cause not traced into the scraper source yet. It's probably the vote page parser not
checking for an error response before reading names.

## Workaround in govbot

`actions/format/utils/log_jsonl.py` has a per-state table of scraper-failure rules. ND's entry
treats a vote version with a voter named "Service Unavailable" as not scraped that night, so
it's never logged. Status as of 2026-11-25: added in PR #308 (`_nd_service_unavailable`, tested in
`test_log_jsonl.py`; see `tamara-notes/processes/workstreams/shared-docs/jsonl-log-conversion-results.md`,
section 3). Without it, ND's logs would show a garbled roll call as current on more than 1,100
votes.

## What would actually fix this

1. File the bug with OpenStates (`openstates/issues`; see the contribution notes in memory).
   Include the HB 1626 example and the six nights. Ask for the scraper to fail, or skip the
   vote, when the vote page returns an error instead of a roll call.
2. Or fix it ourselves: a PR to `openstates-scrapers` (`scrapers/nd/`) that detects the error
   page.

**When the fix is merged and live, delete ND's entry from the table in `log_jsonl.py`** (and
its test), then update this file and the README index.

## Timeline

- 2025-12-30 to 2026-08-11: six nights of "Service Unavailable" voters in the raw scrapes.
- 2026-11-25: found during the JSONL log conversion. Per-state workaround agreed.

## Related

- [`tn.md`](tn.md): the other state with a scraper failure caught by the same table (TN
  roll calls going empty). Found in the same investigation.
