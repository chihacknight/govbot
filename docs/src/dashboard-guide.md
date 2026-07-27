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
numbers always agree. A "Data as of" badge under the title shows when the snapshot
was built.

Jurisdictions whose upstream scraper repo cloned but published no bills yet are
listed as pending under the jurisdiction chart (rather than silently omitted), and
appear automatically once their `*-legislation` repo starts carrying data.

## Where the data comes from

The page reads a single `data.json` produced by
[`scripts/build_dashboard_data.py`](https://github.com/chihacknight/govbot/blob/main/scripts/build_dashboard_data.py),
which scans cloned govbot dataset repos for bills in either format — govbot's
OCD-files layout (`**/bills/<ID>/metadata.json`) or raw OpenStates scraper
output (`_data/<locale>/bill_<uuid>.json`) — and joins topic tags from
`govbot tag` output (`tags/*.tag.json`).

On every Pages deploy (and on a daily 8am UTC schedule), the workflow shallow-clones
every `*-legislation` repo from the
[govbot-openstates-scrapers](https://github.com/govbot-openstates-scrapers)
organization, tags the bills with govbot's embedding model, and rebuilds `data.json`
from all of them, so the published dashboard covers every tracked jurisdiction. The
topic taxonomy lives in
[`scripts/govbot-dashboard.yml`](https://github.com/chihacknight/govbot/blob/main/scripts/govbot-dashboard.yml);
`scripts/dashboard_tags.json` mirrors the same topic names as a keyword fallback for
any bill the embedding tagger didn't reach.

Tagging is **incremental**: after the first full pass, each run re-embeds only bills
that are new or whose text changed, so the daily build stays fast. This is powered by
two caches (a shared copy of the ~90MB embedding model, and a per-repo ledger +
snapshot of the tag files) plus `scripts/filter_new_bills.py`, which drops unchanged
bills before they reach the tagger. Editing `scripts/govbot-dashboard.yml` changes the
cache key and triggers one full re-tag. Every stage degrades gracefully: a failed
tagger falls back to keyword tags, and a failed data build falls back to the committed
sample data rather than breaking the docs site.

The committed sample data is built from the offline mocks
(`actions/govbot/mocks/govbot_data` — Wyoming and Guam), with demo topics derived from
the keyword definitions in `scripts/dashboard_tags.json` (the same shape as the
`tags:` section of `govbot.yml`, keyword-only mode):

```bash
python3 scripts/build_dashboard_data.py \
  --govbot-dir actions/govbot/mocks/govbot_data \
  --tags-config scripts/dashboard_tags.json \
  --output docs/src/dashboard/data.json
```

## Regenerating locally with real data

```bash
govbot clone all                       # clone the dataset repos (~/govbot_data/repos)
cp scripts/govbot-dashboard.yml govbot.yml   # tag definitions (govbot tag reads ./govbot.yml)
govbot logs --join bill --limit none | govbot tag --overwrite   # score bills (embedding mode)
python3 scripts/build_dashboard_data.py --output docs/src/dashboard/data.json
```

`govbot tag` downloads the embedding model (all-MiniLM-L6-v2) to `./govbot_data` on
first use and writes `tags/*.tag.json` next to each session's `bills/`. When those
files exist for a session they take precedence over the keyword fallback; a bill gets a
tag when its `final_score` meets the tag's configured threshold. Commit the regenerated
`data.json` and the Pages workflow publishes it with the rest of the docs.

The Pages workflow does the same across all repos but per-repo (so tags land inside each
clone) and incrementally — see `scripts/tag_dashboard_repo.sh` and
`scripts/filter_new_bills.py`.
