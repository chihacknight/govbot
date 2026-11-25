---
name: az
description: AZ's scraper works only on our custom image (az-fix-test); the 2026-09-30 pause sync removed that image and upstream PR #5742 was closed unmerged, so AZ will fail again when unpaused unless --fastmode is dropped or the image is restored. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Arizona

## Status: 🟡 Clean on its final run, will break again when unpaused

**Paused state.** Last run before pausing:
[36568674231](https://github.com/govbot-openstates-scrapers/az-legislation/actions/runs/36568674231)
(2026-09-29): exit 0, `failure_type: NONE`, on `ghcr.io/tamara-builds/openstates-scrapers:az-fix-test`.

## What's wrong

`az/bills.py` sets the session with a POST, then GETs the bill list again to check it. Our
`actions/scrape/scrape.sh` passes `--fastmode` to every scraper, which turns on a cache that
answers that second GET with the first GET's page, so the session never looks set
(`AssertionError: Session ID not in bill list`). Fails the same way on every network.

Our fix (force a live fetch for that one GET) ran from the custom image from 2026-07-24 to
2026-09-29.

## Why it will break again

- The custom image was set by hand in `az-legislation`'s workflow (commit `96441cf2`,
  2026-07-24), not in `chn-openstates-scrape.yml`. The pause re-sync on 2026-09-30
  (`23eb6caf`, "update template files from config") removed it. AZ now defaults to
  `openstates/scrapers:latest`.
- Upstream PR [#5742](https://github.com/openstates/openstates-scrapers/pull/5742) was closed
  without merging on 2026-08-26. The maintainer asked whether simply not using `--fastmode` for AZ
  would solve it.

## Before unpausing

Pick one:
1. Drop `--fastmode` for AZ, the way NH does (PR #95). This is what upstream suggested and needs
   no custom image.
2. Add `docker_image: ghcr.io/tamara-builds/openstates-scrapers:az-fix-test` to AZ's entry in
   `chn-openstates-scrape.yml` so `apply.py` keeps it.

## Timeline

- **2026-07-14**: Sucuri WAF theory disproven (fails on non-cloud IPs too). PR #5722 (cookie
  merge) merged 07-15 but didn't fix it.
- **2026-07-24**: real cause found (`--fastmode` cache). First successful AZ scrape ever on the
  custom image (2,190 bills). PR #5742 filed.
- **2026-08-26**: PR #5742 closed unmerged.
- **2026-09-29**: final run before pause, clean on the custom image.
- **2026-09-30**: pause sync removes the custom image.

## Related

- `tamara-notes/archived_docs/not-working.md` — the full July write-up of the AZ root cause.
- `tamara-notes/archived_docs/upstream-pr-todo.md` — the old revert checklist (now moot).
- NH in the master list — the other state scraped without `--fastmode`.
