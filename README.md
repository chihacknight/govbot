[![Validate Snapshots](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml/badge.svg)](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml)

**Project overview and demo**  
[![Govbot presentation video](https://img.youtube.com/vi/IFnE1oeUIXo/maxresdefault.jpg)](https://youtu.be/IFnE1oeUIXo)

# 🏛️ govbot

**Every U.S. legislature, as data you can clone.** `govbot` is a terminal-native toolkit that turns government updates into git repositories you can analyze, query, and build on — no scraper to maintain, no data platform to pay for.

- 📥 **Clone the legislation of [56 jurisdictions](https://github.com/orgs/govbot-data/repositories) in under a minute** — every dataset is just a git repo.
- 🔒 **Tag and summarize bills with private, local models** — optimized to run for free on GitHub Actions. No API keys, no per-token bill.
- 🔎 **Analyze it your way** — stream it as JSON Lines through Unix pipes, or load it into DuckDB for SQL across every state at once.

### By the numbers

| | |
|---|---|
| **56** | jurisdictions covered — all 50 states + Federal + DC + 4 territories |
| **14,474** | distinct federal (Congress) bills, and counting |
| **< 1 min** | to clone every dataset |
| **$0** | cost to tag bills — models run locally on free CI |

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

## Contribute

### Folder Structure

This repo is a monorepo, with `actions` being self contained. `actions` as a name is because it's what Github expects.

### Requirements For Each Action

- Be a runnable as basic scripts in python, bash, rust, or typescript which can run as shell scripts with args.
- Have an `action.yml` file to run as a runner, most likely in GitHub Actions.
- Have a `schemas` folder that uses JSON schema to define types.
  - This allow other actions to import your schema for validation.
- Have `__snapshots__` that contain real file/folder outputs. This serves two purposes: (1) they show expected results and (2) they can be directly used as inputs for downstream snapshot tests.
  - Each action manages its own snapshot rendering through a render_snapshots.sh script.
  - Validation occurs via .github/validate-snapshots.yml for each specific module.
