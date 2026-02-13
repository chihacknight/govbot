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

- **"What happens with 10x the data?"** - Current scale is ~47 jurisdictions. Consider: What if we add counties? Cities? Federal agencies?

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
govbot init          # Create govbot.yml config
govbot clone all     # Download all state legislation datasets
govbot clone wy il   # Download specific states
govbot logs          # Stream legislative activity as JSON Lines
govbot logs | govbot tag  # Process and tag data
govbot build         # Generate RSS feeds
```

## Testing with Mock Data

Mock legislative data is available for offline development:
- Location: `actions/govbot/mocks/.govbot/repos/`
- Contains: Wyoming (wy) and Guam (gu) sample data
- Usage: `govbot logs --govbot-dir ./actions/govbot/mocks/.govbot`

## govbot Development

```bash
cd actions/govbot
just setup           # Install Rust toolchain and dependencies
just test            # Run snapshot tests
just review          # Review snapshot changes (insta)
just govbot logs     # Run CLI in dev mode (uses mocks/.govbot)
just mocks wy il     # Update mock data for testing
```

## When in Doubt

1. Check existing snapshots for expected behavior
2. Look at similar actions for patterns
3. Prefer explicit failure over silent corruption
4. Keep changes minimal and focused
5. Consider the data pipeline as a whole, not just isolated components
