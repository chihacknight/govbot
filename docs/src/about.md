![Govbot icon](https://manband.one/assets/govbot-logo-transparent.png)

# govbot

**Every U.S. legislature, as data you can clone.** govbot turns government updates into git repositories you can analyze, query, and build on — no scraper to maintain, no data platform to pay for.

- 📥 **Clone the legislation of 56 jurisdictions in under a minute** — every dataset is just a git repo.
- 🔒 **Tag and summarize bills with private, local models** — optimized to run for free on GitHub Actions. No API keys, no per-token bill.
- 🔎 **Analyze it your way** — stream it as JSON Lines through Unix pipes, or load it into DuckDB for SQL across every state at once.

## By the numbers

| | |
|---|---|
| **56** | jurisdictions covered — all 50 states + Federal + DC + 4 territories |
| **14,474** | distinct federal (Congress) bills, and counting |
| **< 1 min** | to clone every dataset |
| **$0** | cost to tag bills — models run locally on free CI |

## What We Offer

The main Govbot dataset covers **56 jurisdictions** — all 50 states, the U.S. House & Senate (Federal), DC, and the territories of Puerto Rico, Guam, the U.S. Virgin Islands, and the Northern Mariana Islands — as `.json` files organized using the [Project Open Data](https://project-open-data.cio.gov/) catalog format.

The Govbot scrapers update regularly, appending new logs. New bills are then tagged and scored **on-device by a private sentence-transformer model (ONNX) with a keyword fallback** — small enough to run for free on GitHub Actions, so no bill text ever leaves your pipeline and there's no per-token cost. From there, the data can be analyzed with SQL via a [DuckDB](https://duckdb.org/) interface, browsed on our [live legislation dashboard](https://docs.windycivi.com), or plugged into applications like:

- [**Transportation Legislation** Bluesky bot](https://bsky.app/profile/govbottransport.bsky.social) — transportation bills nationwide, posted as they move.
- [**Data Center & AI Legislation** Bluesky bot](https://bsky.app/profile/govbotaidatacenter.bsky.social) — AI and data-center bills across every jurisdiction.
- [**WindyCivi**](https://windycivi.com/), our example website, and an early BlueSky bot built in collaboration with U.S. Representative Hoan Huynh.

# Why govbot?

> Why don't we pay attention to our representatives between elections?

Legislative data is hard to parse, track, and organize. Activists, concerned citizens, and the curious may not have the time, resources, or expertise to build out duplicative tech stacks. Existing solutions may be limited by the willingness of organizations and companies to continue to run and host them - such as in the case of [Google's Civic Information API](https://developers.google.com/civic-information/), which was shut down earlier this year. What would a decentralized, open-source legislative data solution look like?

The Govbot team's goal is to bridge this gap - building the framework for the building and use of federated, open-source, non-profit legislative data. Built as a [Chi Hack Night](https://chihacknight.org) [Breakout Group](https://github.com/chihacknight/breakout-groups/issues/219), the project includes an open-source, simplified, and expanded version of [OpenStates'](https://open.pluralpolicy.com/data/) data on state and federal legislation, as well as example applications.

# How Do I Use It?

## 1. Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

## 2. Run govbot

```bash
govbot
```

That's it. If no `govbot.yml` exists, an interactive wizard walks you through setup:

1. **Sources** - Choose all 56 jurisdictions or pick specific ones
2. **Tags** - Start with an example tag, or get an AI prompt you can copy-paste to create your own
3. **Publishing** - RSS feeds configured automatically

The wizard creates `govbot.yml`, `.gitignore`, and a GitHub Actions workflow.

## 3. Run the pipeline

Once set up, running `govbot` again executes the full pipeline:

1. Clones/updates legislation repositories
2. Tags bills based on your tag definitions
3. Generates RSS feeds in the `docs/` directory

## Other Commands

```bash
govbot clone all           # download all state legislation datasets
govbot clone il ca ny      # download specific states
govbot logs                # stream legislative activity as JSON Lines
govbot logs | govbot tag   # process and tag data
govbot build               # generate RSS feeds
govbot load                # load bill metadata into DuckDB database
govbot delete all          # remove all downloaded data
govbot update              # update govbot to latest version
govbot --help              # see all commands and options
```

Dataset Key:
- 🆕: the locale's data received updates since your last cloning
- ✅: the data you've cloned is up-to-date with the most current version
- 🔄: the data is currently being updated
- ❌: the data is not currently accessible

## Querying in SQL using DuckDB

You can query the data using SQL, via DuckDB, which creates a simiulated database from the .json log files. See [DUCKDB.md](./DUCKDB.md) for more details.

### Running Queries in the Command Line

```sql
-- Load JSON extension
INSTALL json;
LOAD json;

-- Query all bill metadata
SELECT * 
FROM read_json_auto('~/govbot_data/repos/**/bills/*/metadata.json')
LIMIT 10;
```

### Additional Commands, and Querying via the Web UI

Additional examples of commands, and setup for the web UI, can be found below: 

```bash
# Load all data into a database (default: govbot.duckdb)
govbot load

# Or specify a custom database file
govbot load --database my-bills.duckdb

# With memory limit and thread settings
govbot load --memory-limit 32GB --threads 8

# Open in DuckDB UI (opens in your browser)
duckdb --ui govbot.duckdb
```

### Helper Scripts

```bash
# Run example queries
./duckdb-query.sh examples/duckdb-example.sql
```

## Contributing & Testing

### Prerequisites

Folks looking to contirbute should have knowledge of Rust:  `just`. `just setup` to start, and then `just govbot ...` to develop the cli.

The following should also be installed:

1. **Rust & Cargo**: Install the [Rust Toolchain](https://rustup.rs/)
2. **Just**: Install the task runner: `cargo install just`

### Development Workflow

Use `just govbot ...` as your cli "dev" environment.

### Other Useful Commands

- `just` - See all available tasks
- `just test` - Run all tests
- `just review` - Review snapshot test changes
- `just mocks [LOCALES...]` - Update mock data for testing

We build snapshots off `examples`. Add examples to make a test.

## Advanced

```bash
GOVBOT_REPO_URL_TEMPLATE="https://gitsite.com/org/{locale}.git" govbot ...
```

# Project History

The Govbot project began in 2022, with a vision to create a destination for simplified, summarized updates on legislative action, with the ability to follow or filter for certain legislative topics. The result was the initial Windy Civi [app](https://apps.apple.com/us/app/windy-civi/id6737817607), and [website](https://windycivi.com), launched in beta in 2024. 

While building the solution, the team began to consider the limitations of a centrally-managed data source and platform, versus one that could be decentralized, that was open-source, and that allowed for exploration and use of the data in ways beyond initial designs.

Our vision now has pivoted to building that data set, as well as building sample applications and solutions to ensure that government accountability can be accessible to all.

# FAQs

## Can I See The Repo?
Yes! Our main repo can be found [here](https://github.com/windy-civi/windy-civi). The repo that is being used to run and store the data - the 'toolkit' repo - can be found [here](https://github.com/chihacknight/govbot).

## How Is The Data Structured?
You an find the file format structure and .json schema in the readme.md located [here](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/DATA_STRUCTURES.md).

## How Do I Clone This Data?
Each locale is scaped using a GitHub Actions tempate that is defined and explained in detail [here](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/for-caller-repos/README_TEMPLATE.md). You can follow this template to create a new repository of locale data.

To help manage multiple pipelines or locales, look at our [pipeline manager documentation](https://github.com/chihacknight/govbot/tree/main/actions/pipeline-manager)

## How Can I Stay Updated, Or Get In Touch?
You can stay updated by following our work at [Chi Hack Night](chihacknight.org), as well as on the related Slack (see below). You can also follow our commits and updates on [Github](https://github.com/windy-civi) and this [Docs page](https://docs.windycivi.com),

You can message us on the [Chi Hack Night Slack](https://chihacknight.slack.com/archives/C047500M5RS) - we have our own channel.

![Govbot icon](https://manband.one/assets/govbot-icon-transparent.png)
