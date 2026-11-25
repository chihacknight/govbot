---
name: openstates-pr-conventions
description: How to open an upstream fix PR + companion issue against openstates-scrapers, including the jurisdiction-prefix title convention a maintainer requested on #5847 (2026-10-13). Read before filing the next one.
metadata:
  type: reference
---

# Contributing fixes to OpenStates — conventions

## Repos involved

| Repo | Purpose |
|------|---------|
| `openstates/openstates-scrapers` | Where scraper code lives — submit fix PRs here |
| `openstates/issues` | Unified issue tracker — file a companion bug here, maintainers watch it for triage |

## PR title: prefix with the jurisdiction

**Added 2026-10-13**, per direct maintainer feedback on
[#5847](https://github.com/openstates/openstates-scrapers/pull/5847):

> "please prefix the pull request title with the jurisdiction, when the code is a fix for the
> jurisdiction. Makes it easier to track what's changing in the repo (common part of workflow
> is, 'has anyone fixed this problem yet?')."

Format: `<JURISDICTION>: <normal title>` — e.g.
`USA: fix: handle "Concurrent Resolution Rejected" Senate vote result`. Use the two-letter
state/territory code or `USA` for federal, matching the code used everywhere else in this repo
(`chn-openstates-scrape.yml`, `tamara-notes/state-specific/<code>.md`, etc.) — not the scraper
module name if it differs.

**Retroactively applied to #5847** (renamed in place, 2026-10-13) rather than left inconsistent
with the ask.

## The full process

1. **Submit the fix PR** to `openstates/openstates-scrapers`, title prefixed with the
   jurisdiction per above.
2. **File a companion issue** in `openstates/issues` (not in `openstates-scrapers`) — this is
   what maintainers actually watch for triage, separate from the PR thread.
3. **Cross-link both directions** — don't just link the issue to the PR; the PR needs to
   reference the issue too (learned this the hard way on #5847: initially only linked one way,
   had to go back and add `Issue: openstates/issues#1422` to the PR body after the fact). Use
   full cross-repo syntax: `openstates/openstates-scrapers#NNNN` from the issue,
   `openstates/issues#NNNN` from the PR.
4. **Label the issue:**
   - `type:bug` for broken scrapers
   - `component:bill-data` for scraper/bill-data issues (maps to `openstates-scrapers`)
   - Maintainers will retag as needed — just do your best with labels, don't agonize.

## Verification discipline before filing

Established across the FL and USA fixes — don't file without:
1. **Reproducing the bug offline first**, ideally against a minimal fixture matching the real
   data shape, not just reading the code and guessing.
2. **Confirming the fix resolves the offline repro.**
3. **Verifying live against production** where practical (a real scrape run, not just CI) —
   "built successfully" is not the same as "confirmed working." This exact mistake (a Docker
   image built from the wrong branch, never caught) cost a full night once on FL — see
   `tamara-notes/state-specific/fl.md`.

## After merge — don't assume merged means live

Upstream only rebuilds `openstates/scrapers:latest` on their own cadence. Before reverting any
`docker_image` override pointed at a temporary fix image:
1. Confirm the PR actually merged (not just approved).
2. Confirm a new `openstates/scrapers:latest` was actually cut *after* the merge — check Docker
   Hub's `last_updated` timestamp, or pull and grep the image directly. Don't trust "it's been a
   few days, it's probably rebuilt by now."
3. Only then revert the override and verify live.

See `tamara-notes/archived_docs/upstream-pr-todo.md` for the per-state tracking template this
feeds into, and its USA entry for a worked example of the full cycle (filed → merged → verified
live → override reverted).

## Our account

Tamara files under her personal GitHub account (`tamara-builds`). No org account for Chi Hack
Night.

## Label reference

**type:** `type:bug` · `type:upstream` · `type:proposal` · `type:historical`

**component:** `component:bill-data` → openstates-scrapers · `component:people-data` →
openstates/people · `component:web` → openstates.org · `component:infrastructure` →
openstates-core
