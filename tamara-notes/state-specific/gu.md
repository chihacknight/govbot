---
name: gu
description: GU scrape crashes on a schema-validation failure -- a bill version's note field comes back empty, hitting the Jurisdiction's minLength:1 requirement. Confirmed on 3 different bills across 3 retries. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Guam

## Status: 🟡 Broken — real scraper code bug, not yet fixed

**Active state** (`template: openstates-scrape`, `runner: ubuntu-latest` default) in
`chn-openstates-scrape.yml`, scheduled daily.

## What's wrong

Scrape crashes on `openstates.exceptions.ScrapeValueError`, classified `S6_VALIDATION`.
Confirmed on run [37049579741](https://github.com/govbot-openstates-scrapers/gu-legislation/actions/runs/37049579741)
(2026-10-02): hit on **3 different bill UUIDs across the 3 retry attempts** — a recurring
defect in the scraper, not a one-off bad record.

```
openstates.exceptions.ScrapeValueError: validation of Bill 97ca2c24-be91-11f1-9c5b-1650976c306a failed:
	'' is too short

Failed validating 'minLength' in schema['properties']['versions']['items']['properties']['note']:
    {'minLength': 1, 'type': 'string'}

On instance['versions'][0]['note']:
    ''
```

A bill `version`'s `note` field comes back as an empty string, which fails the OCD schema's
`minLength: 1` requirement and crashes the entire scrape rather than just that one bill/version.

## Root cause

**Not yet traced into the actual scraper source.** Likely in `scrapers/gu/bills.py`,
wherever a version's `note` gets set — probably constructed from some upstream field that's
sometimes blank, with no fallback/default applied before being handed to `add_version_link`
or equivalent. Not yet confirmed against the live source.

## What would actually fix this

Same shape as the USA fix (`usa.md`) and the general pattern of "one bad record crashes the
whole scrape": either (a) give the `note` field a sane default/fallback when the source data
is blank, or (b) catch the validation failure for just that one version and skip it rather
than letting it propagate and kill the whole run. Not yet decided which; not yet built.

## Timeline

- **2026-10-02**: found during a review of the 9 currently-active states' latest runs
  (prompted by the usa-legislation investigation the same day). Not yet fixed.

## Related

- `usa.md` — same general pattern (one bad record crashes the entire scrape), different
  specific bug.
- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
