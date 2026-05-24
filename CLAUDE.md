# CLAUDE.md

This file provides senior engineering-level guidance for Claude Code when working on this codebase.

## Project Overview

**govbot is a 4-tool stack for civic-data publishing**, built so an
activist crew can run a credible news-bot at nearly-free cost on commodity
infrastructure (GitHub Actions + a laptop with local models). The stack
exists to clear one bar: the first user, the **climate-activist** userland
repo, must be able to ship Bluesky posts that are "worth reading" at
"nearly free to run/improve". Every architectural choice in this repo
should be checked against that.

The 4 tools, with the honest state of each:

1. **Select real gov data** — `govbot pull` over 55 OCD dataset git repos
   (every US state + DC + territories + federal Congress), content-
   addressed in `~/.govbot/cache/`. `govbot doctor` validates. Today
   `govbot source --select docs` ships bill text + subjects; **sponsors
   and voting records are captured in metadata but not yet projected
   into `--select docs`** — a recall gap for sponsor-pattern signals.
2. **Filter / transform** — fastclass tagging is the shipped transform
   (Wave A). The planned **`summarize` transform** (local-LLM digests
   of grouped bills, emitted with model id + source bill ids + prompt
   revision so the digest is reproducible) **does not exist** —
   userland holds a `summarizer/prompt.md` stub.
3. **Publish with receipts** — RSS, HTML, JSON, DuckDB, and a Bluesky
   posting bot ship today. **X is not built. AI digest publishing is
   not built.** **"Receipts" as defined in the vision** — a GitHub
   Pages artifact carrying the deterministic provenance behind every
   AI digest (model used, source bill ids, fastclass scores +
   reasoning, regen command) — **is a new capability that does not yet
   exist**. The current classification evidence chains carry most of
   the data a receipt would need; they are not yet packaged into a
   public artifact.
4. **Coding-agent-native dev experience** — `AGENT.md` provides the
   make/manage/update flow that a fresh Claude Code session can follow
   without other onboarding. The fastclass plugin
   (`/fastclass:from-intent`, `/fastclass:improve`, `/fastclass:ratify`,
   `/fastclass:install-model`) handles the classifier loop. `govbot
   doctor` validates installations. This is the one tool that is
   already shipping its vision.

Operators: keep the gap map above honest as features land. The README's
Roadmap section is the public version of this list; this CLAUDE.md is the
internal version, biased toward what the code actually does today.

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

## govbot source — streaming legislative activity

`govbot source` walks every linked dataset and emits one JSON record per
bill log entry. It is the **source** stage of the stream protocol — the
records `govbot publish` and `fastclass classify` consume.

### The `--filter default` policy

`--filter` defaults to `default`, which applies the per-dataset filter under
`actions/govbot/src/filters/<dataset>/default.rs`. Each dataset's `default.rs`
implements an **action-based** rule that drops *routine* log entries —
introductions, committee referrals, "Bill Number Assigned", "Placed on
General File", boilerplate "President Signed" lines, prefiling, status
updates — so the stream emits only **substantive** events (passage votes,
executive signatures, amendments, defeats, committee reports with content).

This is not a recency cut. A bill whose only log entries are routine
actions — e.g. a freshly-filed bill with just an "Introduction" log —
emits **zero records** under `--filter default` until a substantive event
lands. The bill itself is not deleted; it simply produces no stream rows
yet. Once a substantive log appears (e.g. a passage vote later in the
session), the bill flows through.

If a bill is unexpectedly missing from `source` output:
```bash
govbot source --filter none --repos <dataset>   # confirm it's the filter
```
If `--filter none` shows the bill and `--filter default` does not, the
fix is to add a substantive log entry, not to change the filter.

### The `--select docs` projection

`--select docs` collapses each surviving entry to the
`{"id","text","kind":"docs"}` document the stream protocol defines
(`schemas/STREAM_PROTOCOL.md` §1) — the record `fastclass classify -`
consumes. The default `--select default` keeps the full joined record
for `govbot publish` and ad-hoc analysis.

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
  `.tag.json` files under `<project>/tags/<dataset>/country:.../sessions/<id>/`
  — the files `govbot publish` turns into feeds. It classifies nothing
  itself; it is purely the persistence sink.

### Project layout — `tags/` vs `.govbot/` vs `dist/`

A govbot project has three top-level tool-managed dirs, each with a
distinct role; do not conflate them:

- **`.govbot/`** — the tool's **cache**, the `node_modules/` equivalent.
  Cloned datasets, content-addressed sync state, an optional registry
  override. Fully regenerable; safe to `rm -rf` to start fresh.
  **Never edited by hand, never written to by `apply`.** It does NOT
  hold user-meaningful state — the bluesky publisher's posted-state
  ledger lives under `state/`, not here.
- **`tags/`** — **classification output**, written by `govbot apply`. The
  layout mirrors the source path with a dataset prefix:
  `tags/<dataset>/country:.../state:.../sessions/<id>/<tag>.tag.json`.
  Regenerated by every classify run; the dataset prefix is what isolates
  same-named tag files across jurisdictions in a multi-dataset project.
- **`state/`** — **publisher state**, written by `govbot publish`. The
  bluesky publisher's posted-state ledger lives at
  `state/bluesky-<name>.ledger`. Regenerable-but-operational: deleting
  it makes the next run double-post. Peer of `tags/` and `dist/`.
- **`dist/`** — **publisher output**, written by `govbot publish` (RSS /
  HTML / JSON feeds).

**`govbot.yml` is NOT the classifier — it is a manifest.** It declares
`datasets`, `transforms`, `publish`, and `pipelines`; it has **no `tags:`
block**. The tag taxonomy lives in a separate **fastclass classifier bundle**
that the manifest's `transforms.<name>.classifier` field references by path.
The two configs change at different cadences and are read by different tools:
`govbot.yml` answers *"what data, what transforms, what publishers"*; the
classifier bundle's `classifier.yml` answers *"what's relevant"*.

To run the self-improving loop, work inside the classifier bundle directory and
use the fastclass Claude Code plugin (`/fastclass:improve`, `/fastclass:ratify`)
and the fastclass `compile evaluate` / `compile backtest` / `compile ratify` primitives. The
retired `fastclass --propose` flag no longer exists. For activists who have
ratified one proposal end-to-end, `/fastclass:improve autonomous` becomes the
ongoing default — constitution-passing proposals apply as usual, coverage-gap
proposals re-test against the rolling eval set and land only if rolling proves
them safe (`generated_by: autonomous-coverage-gap` in `fastclass.lock`).
AGENT.md §2 carries the activist-facing framing.

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
