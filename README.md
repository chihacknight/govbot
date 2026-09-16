[![Validate Snapshots](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml/badge.svg)](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml)
[![Nightly E2E](https://github.com/chihacknight/govbot/actions/workflows/test-nightly.yml/badge.svg)](https://github.com/chihacknight/govbot/actions/workflows/test-nightly.yml)
[![Nightly Release](https://github.com/chihacknight/govbot/actions/workflows/release-nightly.yml/badge.svg)](https://github.com/chihacknight/govbot/actions/workflows/release-nightly.yml)

**Project overview and demo**
[![Govbot presentation video](https://img.youtube.com/vi/IFnE1oeUIXo/maxresdefault.jpg)](https://youtu.be/IFnE1oeUIXo)

# 🏛️ govbot

**Every U.S. legislature, as data you can clone.** `govbot` tracks bills in all 50 states, Congress, DC, and the territories, and turns them into git repositories you can analyze, query, and build on — no scraper to maintain, no data platform to pay for.

It is for **journalists** watching a beat, **researchers** comparing policy across states, **advocates** who need to know the moment a bill moves, and **civic hackers** building feeds, bots, and dashboards on open legislative data.

- 📥 **Clone the legislation of [56 jurisdictions](https://github.com/orgs/govbot-data/repositories) in under a minute** — every dataset is just a git repo.
- 🔒 **Tag and summarize bills with private, local models** — optimized to run for free on GitHub Actions. No API keys, no per-token bill.
- 🔎 **Analyze it your way** — stream it as JSON Lines through Unix pipes, load it into DuckDB for SQL across every state at once, or just ask an AI assistant to read a bill straight from GitHub (no install — see below).

### By the numbers

| | |
|---|---|
| **56** | jurisdictions covered — all 50 states + Federal + DC + 4 territories |
| **14,474** | distinct federal (Congress) bills, and counting |
| **< 1 min** | to clone every dataset |
| **$0** | cost to tag bills — models run locally on free CI |

## Table of Contents

- [Use Cases](#use-cases)
- [Example Projects](#example-projects)
- [Quick Start](#quick-start)
- [What the Output Looks Like](#what-the-output-looks-like)
- [How It Works](#how-it-works)
- [Legislation Data Catalogs](#data-catalogs)
  - [Data Structure](#data-structure)
  - [Read it from an AI assistant (no install)](#read-it-from-an-ai-assistant-no-install)
- [Contribute](#contribute)

## Use Cases

Concrete things people do with govbot today:

- **Track housing bills across 5 states.** Define a `housing` tag once in `govbot.yml`; every run tags matching bills in every cloned jurisdiction and publishes one RSS feed.
- **Get notified when education bills are introduced.** Run the pipeline on a schedule with the [Govbot GitHub Action](actions/govbot/action.yml) and subscribe to the feed in any RSS reader — no code.
- **Ask about one specific bill from your phone.** Paste the [`llms.txt`](llms.txt) recipe into Claude or ChatGPT: *"What's the status of Wyoming HB0001, who sponsored it, and what's the official source link?"* — no install needed.
- **Compare policy across all states in SQL.** `govbot clone all`, then `govbot load` into DuckDB and query every bill at once (sponsors, subjects, timelines).
- **Publish a topic bot.** Point govbot at a topic and it publishes a live feed for it — see the [running Bluesky bots](#example-projects) below.

## Example Projects

Point govbot at a topic and it publishes a live feed for it. Two running today:

- [**Transportation Legislation** Bluesky bot](https://bsky.app/profile/govbottransport.bsky.social) — transportation bills across all jurisdictions, posted as they move.
- [**Data Center & AI Legislation** Bluesky bot](https://bsky.app/profile/govbotaidatacenter.bsky.social) — tracks AI and data-center bills nationwide.

## Quick Start

### 1. Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

### 2. Set up your project

```bash
govbot
```

Running `govbot` with no config file launches an interactive setup wizard that:
1. Asks what data sources you want (all 56 jurisdictions or specific ones)
2. Guides you through creating tags for topics you care about
3. Creates `govbot.yml`, `.gitignore`, and a GitHub Actions workflow

### 3. Run the pipeline

```bash
govbot
```

With a `govbot.yml` in your directory, running `govbot` executes the full pipeline:
1. Clones/updates legislation repositories
2. Tags bills based on your tag definitions
3. Generates RSS feeds in the `docs/` directory

### Other Commands

```bash
govbot clone all           # download all state legislation datasets
govbot clone il ca ny      # download specific states
govbot logs                # stream legislative activity as JSON Lines
govbot logs | govbot tag   # process and tag data
govbot build               # generate RSS feeds
govbot load                # load bill metadata into DuckDB
govbot delete all          # remove all downloaded data
govbot update              # update govbot to latest version
govbot --help              # see all commands and options
```

**No install?** You can still read any bill through an AI assistant — see [Read it from an AI assistant](#read-it-from-an-ai-assistant-no-install).

## What the Output Looks Like

`govbot logs` streams one JSON record per legislative event (abbreviated here — real records carry the full bill metadata):

```json
{"timestamp": "20250129T022703Z", "log": {"bill_id": "HB0001",
  "action": {"date": "2025-01-29", "description": "Bill number assigned",
  "classification": ["introduction"]}}}
```

Pipe it anywhere Unix text goes:

```bash
govbot logs --repos="il" --limit=10 | jq '{bill: .log.bill_id, action: .log.action.description}'
```

`govbot build` turns tagged bills into RSS feeds (one per tag) you can subscribe to or post from — that is what powers the Bluesky bots above.

## How It Works

```
government sites (50 states + Congress + territories)
  │  actions/scrape      fetch bills, votes, hearings
  ▼  actions/format      normalize to one schema
govbot-data/*-legislation — one public git repo per jurisdiction (the dataset)
  │  govbot clone        git clone / pull into govbot_data/repos
  │  govbot logs         stream legislative events as JSON Lines
  │  govbot tag          match your tags (keywords or local models)
  ▼  govbot build/load   RSS feeds · DuckDB database
```

Two ways to read the data: the **CLI path** above for pipelines and cross-state analysis, and the **lookup path** — [`llms.txt`](llms.txt) + [`catalog.json`](catalog.json) teach any AI assistant to fetch individual bills straight from GitHub, no install. For big number-crunching across states, use the CLI + DuckDB.

Want to hack on the pipeline itself? See [Contribute](#contribute) — pipeline code lives in `actions/`, one self-contained module per stage.

<a id="data-catalogs"></a>

# 🏛️ Govbot Legislation Data Catalogs

Formatted legislation data for all 56 jurisdictions is available at [github.com/govbot-data](https://github.com/orgs/govbot-data/repositories).

- All 50 US states
- Federal (USA)
- DC, Puerto Rico, Guam, US Virgin Islands, Northern Mariana Islands

### Data Structure

Each jurisdiction has its own repo. The root of that repo IS the dataset — no wrapper folders:

```
{state}-legislation/
├── country:us/
│   └── state:{code}/                  # state:usa (federal), state:il, state:tx, etc.
│       └── sessions/{session_id}/
│           ├── bills/{bill_id}/
│           │   ├── metadata.json      # Bill metadata + _processing timestamps
│           │   ├── logs/              # Action/vote-event logs
│           │   └── files/             # Bill text: original .pdf/.xml/.html + *_extracted.txt
│           └── events/                # Committee hearings, etc.
└── .windycivi/                        # Pipeline metadata (committed & reused)
    ├── sessions.json                  # Session id -> name/dates
    ├── bill_session_mapping.json      # Bill-to-session mappings
    ├── latest_timestamp_seen.txt      # Incremental-processing cursor
    └── errors/                        # Text-extraction failures, missing-session bills, orphan tracking
```

Federal and state jurisdictions share one path pattern (`state:usa` for federal), so downstream tooling doesn't need special-casing.

See [`actions/format/docs/DATA_STRUCTURES.md`](actions/format/docs/DATA_STRUCTURES.md) for the full schema reference (bill metadata, logs, events, error tracking).

### Read it from an AI assistant (no install)

You don't need the CLI to explore the catalogs. Two files let any AI assistant
(Claude, ChatGPT, etc.) read the data directly from GitHub — great from a phone:

- [`llms.txt`](llms.txt) — a plain-language guide an AI reads first: the filing
  rule that turns a jurisdiction + bill number into a fetchable URL, the bill
  fields, discovery recipes, and guardrails (cite official sources, read the
  timeline, don't invent bills).
- [`catalog.json`](catalog.json) — a machine-readable directory of every
  jurisdiction data repo plus the bill path pattern.

**Try it:** paste this into Claude or ChatGPT on your phone —

> Read this guide, then follow it to answer my question:
> https://raw.githubusercontent.com/chihacknight/govbot/main/llms.txt
>
> Question: What's the status of Wyoming HB0001 in the 2025 session, who
> sponsored it, and what's the official source link?

This lookup-by-reading path is best for **specific** questions ("what is IL
SB0813", "what did this sponsor introduce"). For big cross-state number-crunching,
use the CLI + DuckDB above.

## Contribute

User docs end here — contributor docs live in [`CONTRIBUTING.md`](CONTRIBUTING.md):
how each `actions/` module is structured (`action.yml`, schemas, `__snapshots__`
via `render-snapshots.sh`), CLI-first and offline-first conventions, mock data,
and how to open a PR. `CLAUDE.md` holds the same guidance tuned for AI coding assistants.
