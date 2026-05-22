# CLAUDE.md

This file provides senior engineering-level guidance for Claude Code when working on this codebase.

## Project Overview

This is **govbot** - a monorepo for distributed data analysis of government updates. Git repos function as datasets, including legislation from 47+ states/jurisdictions. The `actions/` folder contains self-contained modules that can run as shell scripts or GitHub Actions.

## Senior Engineering Prompts

Use these meta-prompts to guide architectural decisions and code quality.

### Architecture & Design

- **"What are the second-order effects of this change?"** - Before implementing, consider how changes propagate through the system. Changes to schemas affect downstream consumers. Changes to data formats affect all pipelines.

- **"Does this belong here, or does it belong closer to the data?"** - Prefer transformations at the source. If scraping logic can filter data early, don't defer filtering to format/extract stages.

- **"What's the failure mode?"** - For every external dependency (APIs, file systems, network), define what happens when it fails. Government data sources are notoriously unreliable.

- **"Can this run without network access?"** - Prioritize offline-first design. Snapshots exist for a reason - they enable testing and development without live data.

### Code Quality

- **"Would this work in a fresh clone?"** - No implicit state. All dependencies must be explicitly declared. All paths must be relative or configurable.

- **"Can I understand this in 6 months?"** - Prefer explicit over clever. Government data has edge cases - document them inline, not in external docs that drift.

- **"What's the smallest change that solves this?"** - Resist scope creep. A bug fix is not a refactor opportunity. A new feature doesn't require rewriting adjacent code.

- **"Is this tested by snapshots?"** - If a change affects output, update or add snapshots. Snapshots are the source of truth for expected behavior.

### Data Pipeline Principles

- **"Schema-first thinking"** - Define the shape of data before writing transformation code. Use `/schemas` folder. JSON Schema enables cross-language validation.

- **"Idempotency is non-negotiable"** - Running a pipeline twice should produce the same result. No side effects that accumulate.

- **"Trace data lineage"** - Every output should be traceable to its source. Include metadata about when and how data was fetched.

- **"Fail loudly, recover gracefully"** - Validation errors should halt pipelines. Missing optional data should not.

### Performance & Scale

- **"What happens with 10x the data?"** - Current scale is ~55 dataset repos (all US state/territory legislatures + federal). The runtime registry (`registry.json`) is what makes 10x feasible — adding counties, cities, or agencies is a data change, not a recompile.

- **"Can this be parallelized?"** - State-level operations are inherently parallel. Pipelines should support concurrent execution.

- **"Memory vs. streaming"** - Large datasets should be processed as streams, not loaded entirely into memory.

### Contribution Guidelines

- **"Does this have an `action.yml`?"** - New actions must be GitHub Actions-compatible.

- **"Where are the snapshots?"** - Each action manages snapshots via `render_snapshots.sh`. Add test data in `__snapshots__/`.

- **"CLI-first, API-second"** - Prefer shell-composable tools. Unix pipe friendliness enables automation.

## Monorepo Structure

```
actions/
  extract/      # Data extraction utilities
  format/       # Data transformation and formatting
  govbot/       # CLI tool for interacting with government data
  pipeline-manager/  # Orchestrates data pipelines
  report-publisher/  # Generates reports
  scrape/       # Web scraping for government data sources
schemas/        # Shared JSON schemas for data validation
scripts/        # Repository-level utility scripts
```

## Key Conventions

1. **Snapshots as Tests**: `__snapshots__/` folders contain real outputs used for validation
2. **Schema Validation**: Use JSON Schema from `/schemas` for type definitions
3. **Multi-language**: Actions can be Python, Bash, Rust, or TypeScript
4. **Portable by Default**: Everything should run as basic scripts with args

## Common Commands

```bash
govbot               # Scaffold govbot.yml (interactive wizard), then run the pipeline
govbot pull all      # Download all state legislation datasets
govbot pull wy il    # Download specific states
govbot source        # Stream legislative activity as JSON Lines
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
govbot load          # Load bill metadata into DuckDB
govbot publish       # Run the manifest's publishers (RSS / HTML / JSON / DuckDB / Bluesky)
govbot run           # Run the full pipeline: pull -> classify -> apply -> publish
```

## DuckDB Integration

The `govbot load` command loads bill metadata into a DuckDB database for SQL analysis.

**Prerequisites**: DuckDB CLI must be installed (`brew install duckdb` or see https://duckdb.org/docs/installation/)

**How it works**:
- Shells out to `duckdb` binary (not a Rust library dependency)
- Reads all `metadata.json` files from cloned repos
- Creates `bills` table and `bills_summary` view
- Database saved to `~/.govbot/govbot.duckdb`

**Usage**:
```bash
govbot pull all                     # First, get the data
govbot load                         # Load into DuckDB
govbot load --memory-limit 32GB     # For large datasets
duckdb --ui ~/.govbot/govbot.duckdb # Open in browser UI
```

See `actions/govbot/DUCKDB.md` for query examples and schema documentation.

## Classifying with fastclass

Classification is a **pipe** of two composable tools that compose over a
process boundary — govbot streams the data, **fastclass** (a standalone,
self-improving text classifier) classifies it, govbot persists the result:

```bash
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
```

- **`govbot source --select docs`** emits one `{"id","text","kind":"docs"}`
  document per bill carrying the **full bill text** from `metadata.json`; the
  `id` is the bill's dataset path, which routes the result back.
- **`fastclass classify -`** scores each document against a **classifier
  bundle** — a fastclass-native directory (`classifier.yml` + `fusion.yml` +
  `eval/`). govbot passes only the bundle path; it never reads the bundle.
- **`govbot apply`** reads fastclass's result JSON from stdin and writes per-tag
  `.tag.json` files into the dataset — the files `govbot publish` turns into
  feeds. It classifies nothing itself; it is purely the persistence sink.

**`govbot.yml` is NOT the classifier — it is a manifest.** It declares
`datasets`, `transforms`, `publish`, and `pipelines`; it has **no `tags:`
block**. The tag taxonomy lives in a separate **fastclass classifier bundle**
that the manifest's `transforms.<name>.classifier` field references by path.
The two configs change at different cadences and are read by different tools:
`govbot.yml` answers *"what data, what transforms, what publishers"*; the
classifier bundle's `classifier.yml` answers *"what's relevant"*.

To run the self-improving loop, work inside the classifier bundle directory and
use the fastclass Claude Code plugin (`/fastclass:improve`, `/fastclass:ratify`)
and the fastclass `classify --eval` / `--backtest` / `--promote` primitives. The
retired `fastclass --propose` flag no longer exists.

**Prerequisite**: the `fastclass` binary must be resolvable on `PATH`,
`~/.cargo/bin`, or `~/.govbot/bin` (`cargo install --path <fastclass repo>`).
`govbot run`'s transform stage resolves transform binaries the same way.

To improve tag quality, read **`AGENTS.md` in the fastclass repo** — the
operational playbook for the classify → eval → propose → backtest → promote
loop. Its one hard rule: never show the frozen `eval/constitution.yml` gold set
to an LLM.

## Testing with Mock Data

Mock legislative data is available for offline development:
- Location: `actions/govbot/mocks/.govbot/repos/`
- Contains: Wyoming (wy) and Guam (gu) sample data
- Usage: `govbot source --govbot-dir ./actions/govbot/mocks/.govbot`

## govbot Development

```bash
cd actions/govbot
just setup           # Install Rust toolchain and dependencies
just test            # Run snapshot tests
just review          # Review snapshot changes (insta)
just govbot source   # Run CLI in dev mode (uses mocks/.govbot)
just mocks wy il     # Update mock data for testing
```

## When in Doubt

1. Check existing snapshots for expected behavior
2. Look at similar actions for patterns
3. Prefer explicit failure over silent corruption
4. Keep changes minimal and focused
5. Consider the data pipeline as a whole, not just isolated components
