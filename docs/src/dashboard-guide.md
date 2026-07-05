# Legislation Dashboard

**[Open the dashboard →](./dashboard/index.html)**

A static, client-side dashboard over bill data from every tracked jurisdiction,
filterable by state/territory, session, chamber, topic tag, and free-text search.
It is plain HTML/JS with no external dependencies, deployed as part of this docs
site by the existing GitHub Pages workflow.

## What it shows

- **Stat tiles** — bill count, jurisdictions, sessions, and share of bills with topic tags
- **Bills by jurisdiction** and **bills by topic** bar charts (click a bar to filter)
- **Activity by month** — bills by the month of their most recent recorded action
- **Bills table** — sortable, with topic chips and links to each bill's official source

All charts, tiles, and the table re-render against the same filtered slice, so the
numbers always agree.

## Where the data comes from

The page reads a single `data.json` produced by
[`scripts/build_dashboard_data.py`](https://github.com/chihacknight/govbot/blob/main/scripts/build_dashboard_data.py),
which scans every `metadata.json` in cloned govbot dataset repos and joins topic
tags from `govbot tag` output (`tags/*.tag.json`).

The committed sample data is built from the offline mocks
(`actions/govbot/mocks/.govbot` — Wyoming and Guam), with demo topics derived from
the keyword definitions in `scripts/dashboard_tags.json` (the same shape as the
`tags:` section of `govbot.yml`, keyword-only mode):

```bash
python3 scripts/build_dashboard_data.py \
  --govbot-dir actions/govbot/mocks/.govbot \
  --tags-config scripts/dashboard_tags.json \
  --output docs/src/dashboard/data.json
```

## Regenerating with real data

```bash
govbot clone all        # clone the dataset repos (~/.govbot/repos)
govbot tag              # optional: score bills against your govbot.yml tags
python3 scripts/build_dashboard_data.py --output docs/src/dashboard/data.json
```

When real `tags/*.tag.json` files exist for a session, they take precedence over
the keyword fallback; a bill gets a tag when its `final_score` meets the tag's
configured threshold. Commit the regenerated `data.json` and the Pages workflow
publishes it with the rest of the docs.
