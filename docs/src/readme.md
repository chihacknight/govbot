![Govbot icon](https://manband.one/assets/govbot-logo-transparent.png)

# Mission

> Why don't we pay attention to our representatives between elections?

Legislative data is hard to parse, track, and organize. Activists, concerned citizens, and the curious may not have the time, resources, or expertise to build out duplicative tech stacks. Existing solutions may be limited by the willingness of organizations and companies to continue to run and host them - such as in the case of [Google's Civic Information API](https://developers.google.com/civic-information/), which was shut down earlier this year. What would a decentralized, open-source legislative data solution look like?

The Govbot team's goal is to bridge this gap - building the framework for the building and use of federated, open-source, non-profit legislative data. Built as a [Chi Hack Night](https://chihacknight.org) [Breakout Group](https://github.com/chihacknight/breakout-groups/issues/219), the project includes an open-source, simplified, and expanded version of [OpenStates'](https://open.pluralpolicy.com/data/) data on state and federal legislation, as well as example applications. 

# What We Offer

The main Govbot dataset currently includes legislative updates from bills in the U.S. House & Senate, all 50 states, territories like Guam, and the city of Chicago, as .json files organized using the [Project Open Data](https://project-open-data.cio.gov/) catalog format. The Govbot scrapers update regularly, appending new logs, and then running them through Claude to provide topic-based tagging and summaries. This data can then be analyzed using SQL, via an interface built with DuckDB, or plugged into applications like [our example website, WindyCivi](https://windycivi.com/), and a test BlueSky bot built in collaboration with U.S. Representative Hoan Huynh. (https://bsky.app/profile/test-hoan-huynh.bsky.social).

# How Do I Use It?
You can install govbot, and access the 47 currently existing datasets with a simple one-line install from our GitHub repository - the example below is done in Bash.

## Installation

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/windy-civi/toolkit/main/actions/govbot/scripts/install-nightly.sh)"
```

Once installed, you can call Govbot and be provided with options to:
- clone the entire dataset, as it exists currently (this is 47 locales' worth of data!)
- clone specific items (such as only items in a specific state, session, or for a specific bill)
- delete specific items
- delete everything
- load metadata into a SQL-accessible DuckDB database

An example of each of the above commands is provided below, as well as a key for dataset updates.

Dataset Key:
- 🆕: the locale's data recieved updates since your last cloning
- ✅: the data you've cloned is up-to-date with the most current version
- 🔄: the data is currently being updated
- ❌: the data is not currently accessible  

```bash
govbot # to see help
govbot clone # to show
govbot clone {{locale}} {{locale}} # to download specific items
govbot delete {{locale}} # to delete specific items
govbot delete all # to delete everything
govbot load # load bill metadata into DuckDB database
```

## Querying in SQL using DuckDB

You can query the data using SQL, via DuckDB, which creates a simiulated database from the .json log files. See [DUCKDB.md](./DUCKDB.md) for more details.

### Running Queries in the Command Line

```sql
-- Load JSON extension
INSTALL json;
LOAD json;

-- Query all bill metadata
SELECT * 
FROM read_json_auto('~/.govbot/repos/**/bills/*/metadata.json')
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
Yes! Our main repo can be found [here](https://github.com/windy-civi/windy-civi). The repo that is being used to run and store the data - the 'toolkit' repo - can be found [here](https://github.com/windy-civi/toolkit).

## How Is The Data Structured?
You an find the file format structure and .json schema in the readme.md located [here](https://github.com/windy-civi/toolkit/blob/main/actions/format/docs/DATA_STRUCTURES.md).

## How Do I Clone This Data?
Each locale is scaped using a GitHub Actions tempate that is defined and explained in detail [here](https://github.com/windy-civi/toolkit/blob/main/actions/format/docs/for-caller-repos/README_TEMPLATE.md). You can follow this template to create a new repository of locale data.

To help manage multiple pipelines or locales, look at our [pipeline manager documentation](https://github.com/windy-civi/toolkit/tree/main/actions/pipeline-manager)

## How Can I Stay Updated, Or Get In Touch?
You can stay updated by following our work at [Chi Hack Night](chihacknight.org), as well as on the related Slack (see below). You can also follow our commits and updates on [Github](https://github.com/windy-civi) and this [Docs page](https://docs.windycivi.com),

You can message us on the [Chi Hack Night Slack](https://chihacknight.slack.com/archives/C047500M5RS) - we have our own channel.

![Govbot icon](https://manband.one/assets/govbot-icon-transparent.png)
