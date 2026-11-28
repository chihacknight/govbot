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
appear automatically once their data repo starts carrying data.

## Where the data comes from

The page reads a single `data.json` produced by
[`scripts/build_dashboard_data.py`](https://github.com/chihacknight/govbot/blob/main/scripts/build_dashboard_data.py),
which scans cloned govbot dataset repos for bills in either format — govbot's
OCD-files layout (`**/bills/<ID>/metadata.json`) or raw OpenStates scraper
output (`_data/<locale>/bill_<uuid>.json`) — and joins topic tags from
`govbot tag` output (`tags/*.tag.json`).

On every Pages deploy (and on a daily 8am UTC schedule), the workflow runs
`govbot clone all` to fetch govbot's processed dataset (every data repo in
`actions/pipeline-manager/jurisdictions.yml`: each state's older repo, in `govbot-history` for
most, plus one repo per session from 2027, all in govbot's OCD-files layout), tags the bills with govbot's
embedding model, and rebuilds `data.json` from all of them, so the published
dashboard covers every tracked jurisdiction. (The embedding tagger needs that
layout — `govbot logs`/`govbot tag` read each bill's `action_logs.jsonl` (or, in a repo not
yet converted, its `logs/` folder), which the
raw OpenStates scraper repos don't have.) The topic taxonomy lives in
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

## Committee Hearings & Witness Slips (separate page)

A second site, **[Govbot Public Hearings ↗](https://govbot-public-hearings.vercel.app/)**, lists upcoming committee
hearings where the public can weigh in — live for Illinois, Washington, Massachusetts and Alaska
plus federal rules open for comment — and a how-to-participate directory for every state. It is an
entirely separate pipeline from the bill data: hearings are live artifacts each statehouse
publishes on its own endpoint (not OpenStates). It lives in its own repository,
[frankies2727/govbot-public-hearings](https://github.com/frankies2727/govbot-public-hearings), which scrapes every 12 hours; Govbot's deploy
copies its `hearings.json`, `hearings.xml` and `hearings/*.xml` feeds into this site so old feed
addresses and this site's homepage, search and elections pages keep working, and
`dashboard/hearings.html` forwards there.

The hearings page also **uses govbot's own bill data**: at build time each hearing's
bills are cross-referenced against `data.json` (govbot tracks Illinois & Washington
bills), and where a match is found the bill shows its **govbot title and topic tags** plus
a **"via govbot ↗"** link that opens that bill in the Legislation Dashboard tab
(`index.html#q=<bill>`).
