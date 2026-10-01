# About govbot

**Every U.S. legislature, as data you can clone.** `govbot` is a terminal-native toolkit that turns government updates into git repositories you can analyze, query, and build on — no scraper to maintain, no data platform to pay for.

- 📥 **Clone the legislation of [56 jurisdictions](https://github.com/orgs/govbot-data/repositories) in under a minute** — every dataset is just a git repo.
- 🔒 **Tag and summarize bills with private, local models** — optimized to run for free on GitHub Actions. No API keys, no per-token bill.
- 🔎 **Analyze it your way** — stream it as JSON Lines through Unix pipes, or load it into DuckDB for SQL across every state at once.

[▶ Project overview and demo (video)](https://youtu.be/IFnE1oeUIXo)

## By the numbers

| | |
|---|---|
| **56** | jurisdictions covered — all 50 states + Federal + DC + 4 territories |
| **19,186** | distinct federal bills in the 119th Congress (as of Sept 30, 2026), and counting |
| **< 1 min** | to clone every dataset |
| **$0** | cost to tag bills — models run locally on free CI |

## What you can do with it

The dataset covers **56 jurisdictions** — all 50 states, the U.S. House & Senate (Federal), DC, and the territories of Puerto Rico, Guam, the U.S. Virgin Islands, and the Northern Mariana Islands — as `.json` files, one git repo per jurisdiction.

The scrapers update regularly, appending new logs. New bills are tagged and scored **on-device by a private sentence-transformer model (ONNX) with a keyword fallback** — small enough to run for free on GitHub Actions, so no bill text leaves your pipeline and there's no per-token cost.

Projects built on it:

- [**Legislation dashboard**](dashboard/legislation.html) — every jurisdiction's bills by place, topic, sponsor and status.
- [**Hearings & public comment**](dashboard/hearings.html) — upcoming hearings and how to weigh in.
- [**Illinois elections**](dashboard/elections.html) — every race and candidate on your ballot.
- [**Transportation Legislation** Bluesky bot](https://bsky.app/profile/govbottransport.bsky.social) — transportation bills across all jurisdictions, posted as they move.
- [**Data Center & AI Legislation** Bluesky bot](https://bsky.app/profile/govbotaidatacenter.bsky.social) — AI and data-center bills nationwide.

# Why govbot?

> Why don't we pay attention to our representatives between elections?

Legislative data is hard to parse, track, and organize. Activists, concerned citizens, and the curious may not have the time, resources, or expertise to build out duplicative tech stacks. Existing solutions depend on the organizations and companies willing to keep running them — Google's [Civic Information API](https://developers.google.com/civic-information/) representatives lookup, for example, was shut down in 2025. What would a decentralized, open-source legislative data solution look like?

The Govbot team's goal is to bridge this gap — building the framework for federated, open-source, non-profit legislative data. Built as a [Chi Hack Night](https://chihacknight.org) [Breakout Group](https://github.com/chihacknight/breakout-groups/issues/219), the project includes an open-source, simplified, and expanded version of [Open States'](https://open.pluralpolicy.com/data/) data on state and federal legislation, plus the example applications above.

# Quick start

## 1. Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

## 2. Set up your project

```bash
govbot
```

Running `govbot` with no config file launches an interactive setup wizard that:

1. Asks what data sources you want (all 56 jurisdictions or specific ones)
2. Guides you through creating tags for topics you care about
3. Creates `govbot.yml`, `.gitignore`, and a GitHub Actions workflow

## 3. Run the pipeline

```bash
govbot
```

With a `govbot.yml` in your directory, running `govbot` executes the full pipeline:

1. Clones/updates legislation repositories
2. Tags bills based on your tag definitions
3. Generates RSS feeds in the `docs/` directory

## Other commands

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

## Querying with SQL (DuckDB)

`govbot load` reads every cloned `metadata.json` into a DuckDB database (default `./govbot_data/govbot.duckdb` — data lives under `./govbot_data/` in the folder you run govbot from, or `$GOVBOT_DIR`). The [DuckDB CLI](https://duckdb.org/docs/installation/) must be installed. See [DUCKDB.md](https://github.com/chihacknight/govbot/blob/main/actions/govbot/DUCKDB.md) for the schema and example queries.

```bash
govbot load                                  # load all data into the default database
govbot load --database my-bills.duckdb       # or choose a database file
govbot load --memory-limit 32GB --threads 8  # for large datasets
duckdb --ui govbot_data/govbot.duckdb        # open it in DuckDB's browser UI
```

Or query the JSON directly:

```sql
INSTALL json;
LOAD json;

SELECT *
FROM read_json_auto('govbot_data/repos/**/bills/*/metadata.json')
LIMIT 10;
```

# The data catalogs

Formatted legislation data for all 56 jurisdictions lives at [github.com/govbot-data](https://github.com/orgs/govbot-data/repositories) — one repo per jurisdiction (`govbot-data/{code}-legislation`). The root of each repo *is* the dataset:

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
```

Federal and state jurisdictions share one path pattern (`state:usa` for federal). See [DATA_STRUCTURES.md](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/DATA_STRUCTURES.md) for the full schema reference.

## Read it from an AI assistant (no install)

Two files let any AI assistant (Claude, ChatGPT, etc.) read the data straight from GitHub — great from a phone:

- [`llms.txt`](https://github.com/chihacknight/govbot/blob/main/llms.txt) — a plain-language guide the AI reads first.
- [`catalog.json`](https://github.com/chihacknight/govbot/blob/main/catalog.json) — a machine-readable directory of every jurisdiction repo plus the bill path pattern.

**Try it:** paste this into Claude or ChatGPT —

> Read this guide, then follow it to answer my question:
> https://raw.githubusercontent.com/chihacknight/govbot/main/llms.txt
>
> Question: What's the status of Wyoming HB0001 in the 2025 session, who sponsored it, and what's the official source link?

This works best for **specific** questions. For big cross-state number-crunching, use the CLI + DuckDB above.

# Contribute

The repo is a monorepo; everything under `actions/` is a self-contained module that runs as a plain script and as a GitHub Action. Each action:

- Runs as a basic script (Python, Bash, Rust or TypeScript) with args.
- Has an `action.yml`.
- Defines its types with JSON Schema (in `schemas/`), so other actions can validate against them.
- Keeps real outputs in `__snapshots__/` as its tests (rendered by its `render_snapshots.sh`, validated in CI).

## The govbot CLI

Contributors need [Rust & Cargo](https://rustup.rs/) and the `just` task runner (`cargo install just`). Then, in `actions/govbot`:

- `just setup` — install the toolchain and dependencies
- `just govbot ...` — run the CLI in dev mode
- `just test` — run all tests
- `just review` — review snapshot test changes
- `just mocks [LOCALES...]` — update mock data for testing

## Advanced

Point govbot at your own data repos:

```bash
GOVBOT_REPO_URL_TEMPLATE="https://gitsite.com/org/{locale}.git" govbot ...
```

# Project history

Govbot began in 2022 with a simple goal: a place for simplified, summarized updates on legislative action that you could follow or filter by topic.

- **2022 — [Socratic Center](2022-Socratic-Center/index.html):** find who represents you. The project then joined Chi Hack Night as a breakout group.
- **2023 — [Civi Social](2023-Civi-Social/index.html):** Chicago residents talk directly with their elected officials.
- **2024 — [Windy Civi](2024-Windy-Civi/index.html):** the [app](https://apps.apple.com/us/app/windy-civi/id6737817607) and [website](https://windycivi.com), launched in beta — local, state and federal bills with AI summaries and topics.
- **2025 — [Decentralize](2025-Decentralize/index.html):** building it showed the limits of a centrally managed platform. The vision pivoted to an open, decentralized dataset anyone can run — plus sample applications so government accountability is accessible to all.
- **2026 — today:** 56 open datasets and the civic tools built on them.

# FAQs

## Can I see the code?

Yes. The toolkit, the pipelines and this site are at [chihacknight/govbot](https://github.com/chihacknight/govbot). The data lives in one repo per jurisdiction at [govbot-data](https://github.com/orgs/govbot-data/repositories).

## How is the data structured?

Each bill is a folder with its metadata, action logs and bill text — see [The data catalogs](#the-data-catalogs) above and [DATA_STRUCTURES.md](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/DATA_STRUCTURES.md).

## How do I get the data?

Run `govbot clone il` (or `govbot clone all`), or browse and `git clone` any repo at [govbot-data](https://github.com/orgs/govbot-data/repositories).

To add a **new** jurisdiction, each one is scraped by a GitHub Actions template explained in the [caller-repo README template](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/for-caller-repos/README_TEMPLATE.md); to run many pipelines, see the [pipeline manager](https://github.com/chihacknight/govbot/tree/main/actions/pipeline-manager).

## How can I stay updated, or get in touch?

Join our channel on the [Chi Hack Night Slack](https://chihacknight.slack.com/archives/C047500M5RS), follow along at [Chi Hack Night](https://chihacknight.org) and on [GitHub](https://github.com/chihacknight/govbot), or follow us on [Bluesky](https://bsky.app/profile/govboteducation.bsky.social), [X](https://x.com/govbot27) and [Instagram](https://www.instagram.com/legislationtracker.govbot/?hl=en).
