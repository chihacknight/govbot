---
name: ky
description: KY's scrape has had no sponsors on any bill since 2026-08-20 (1,707 bills); govbot keeps the old ones through option C's empty-field guard. Also whitespace inside action descriptions and abstracts. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Kentucky

## Status: 🟡 Scraper regression, data protected in govbot, not reported upstream yet

## What's wrong

**Sponsors disappeared from the scrape on 2026-08-20.** Every bill that had sponsors lost them,
1,707 of 1,707. They haven't come back: the latest scrape (2026-09-29) has none. The bills are
otherwise there (1,737 bill files every night). Example, SB101 in the raw history
(`govbot-openstates-scrapers/ky-legislation`):

| Scrape | SB101 sponsors |
|---|---|
| 2026-08-19 | M. Nunn, S. Madon, G. Boswell |
| 2026-08-20 onward | (none) |

Found 2026-11-24 while checking bill skipping, and measured 2026-11-25 by replaying the raw
history (`/Volumes/govbot-data/scratch/backfill/field_loss.py`). Root cause not traced into the
scraper source yet.

**Whitespace inside text fields.** KY's scrapes also started putting line breaks (`\r\n`) and
indentation inside action descriptions (SB4: 9 actions) and abstracts (SB4).

## What govbot does about it

- **Sponsors:** nothing was lost. Before option C, the old "same action count, skip the bill"
  shortcut happened to protect them. Since PR #311 (option C), the empty-field guard keeps last
  night's sponsors on purpose:
  - all 1,707 are listed in `.windycivi/errors/kept_empty_fields.json`;
  - `field_regressions.json` carries a `sponsorships` entry every night it's still missing.

  Checked 2026-11-25: 1,707 of 1,737 KY bills have sponsors in `metadata.json`; the other 30
  never had any.
- **Whitespace in actions:** the log and `metadata.json` treat a whitespace-only change as the
  same action (PR #306, #311).
- **Whitespace in abstracts:** not covered. SB4's abstract rewrote `metadata.json` once in the
  option C dry run. Extend the rule only if it turns out to flip back and forth every night.

## What would actually fix this

1. Report it to OpenStates (`openstates/issues`; see the contribution notes in memory), with the
   SB101 example and the 2026-08-20 date. Ask why the `ky` scraper stopped reading sponsors.
2. Or fix it ourselves: a PR to `openstates-scrapers` (`scrapers/ky/`).

**When the fix is live,** the kept sponsors are replaced by the scraper's, and the entries
leave `kept_empty_fields.json` by themselves. Then update this file and the README index.

## Timeline

- 2026-08-20: sponsors gone from every KY bill in the scrape.
- 2026-09-29: latest raw scrape, still none. Whitespace in SB4's actions.
- 2026-11-24: found while checking bill skipping.
- 2026-11-25: measured; option C (PR #311) keeps the sponsors on purpose.

## Related

- [`il.md`](il.md): IL lost its synopses (`abstracts`) the same way on 2026-07-13. Found in the
  same scan.
