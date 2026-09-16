# Contributing to govbot

Thanks for helping out. This file is the human-oriented contributor guide,
distilled from `CLAUDE.md` (the same guidance, tuned for AI coding assistants).
User docs live in [`README.md`](README.md); the AI-readable data guide is
[`llms.txt`](llms.txt) with its machine-readable companion [`catalog.json`](catalog.json).

## Repo layout

This is a monorepo. `actions/` holds self-contained pipeline modules
(the name is what GitHub expects for Actions):

```
actions/
  extract/            # Data extraction utilities
  fleet-monitor/      # Observability for the scraper and data-repo fleets
  format/             # Data transformation and formatting
  govbot/             # CLI tool for interacting with government data
  mcp/                # Model Context Protocol server
  pipeline-manager/   # Orchestrates data pipelines
  report-publisher/   # Generates reports
  scrape/             # Web scraping for government data sources
  scrape-elections/   # Illinois/Chicago elections pipeline
  scrape-hearings/    # Committee-hearings pipeline
  scrape-maps/        # Race locator-map builder
schemas/              # Shared JSON schemas for data validation
scripts/              # Repository-level utility scripts
docs/                 # GitHub Pages dashboards
```

## Requirements for each action

Every module under `actions/` must:

- **Run as plain scripts with args** — Python, Bash, Rust, or TypeScript that
  works from a shell, not only inside CI.
- **Ship an `action.yml`** so it can run as a GitHub Action.
  See [`actions/govbot/action.yml`](actions/govbot/action.yml) for the pattern
  (inputs like `tags`, `limit`, `output-dir`, `govbot-dir`; outputs like `feed-path`).
- **Define types in a `schemas/` folder** using JSON Schema, so other actions
  can import them for validation. Shared schemas live in repo-root `schemas/`.
- **Carry `__snapshots__/` with real file/folder outputs.** Snapshots show
  expected results *and* double as inputs for downstream snapshot tests.
  Each action renders its own via a `render-snapshots.sh` script
  (e.g. `actions/fleet-monitor/render-snapshots.sh`).
- **Be CLI-first, API-second.** Prefer shell-composable tools — Unix-pipe
  friendliness (`govbot logs | govbot tag`) enables automation.

## Conventions that matter

- **Idempotency is non-negotiable.** Running a pipeline twice produces the same
  result — no side effects that accumulate.
- **Offline-first.** Government sources are flaky; snapshots and committed seed
  files exist so tests and development work without live data. New parsers must
  be offline-snapshot-tested (see `test_scrape_hearings.py`,
  `test_scrape_elections.py` for the pattern).
- **Schema first.** Define the shape of data before writing transformation code.
- **Trace lineage.** Every output should record when and how it was fetched
  (see the `_processing` timestamps in bill `metadata.json`).
- **Fail loudly, recover gracefully.** Validation errors halt pipelines; missing
  optional data does not.
- **Smallest change that solves it.** A bug fix is not a refactor opportunity.
- **Keep `llms.txt` + `catalog.json` in sync** with the real data layout
  whenever paths or bill fields change (the authoritative per-repo pattern lives
  in each data repo's own `data.json`).

## Developing the govbot CLI

```bash
cd actions/govbot
just setup           # Install Rust toolchain and dependencies
just test            # Run snapshot tests
just review          # Review snapshot changes (insta)
just govbot logs     # Run CLI in dev mode (uses mocks/govbot_data)
just mocks wy il     # Update mock data for testing
```

**Mock data** for offline development lives at
`actions/govbot/mocks/govbot_data` (Wyoming + Guam samples):

```bash
govbot logs --govbot-dir ./actions/govbot/mocks/govbot_data
```

from `actions/govbot/`. `just mocks [LOCALES...]` refreshes the mocks
(defaults to `wy gu`, prunes bill text and trims logs/bills).

**DuckDB** queries shell out to the `duckdb` binary
(`brew install duckdb`); `govbot load` builds `~/govbot_data/govbot.duckdb`.
See [`actions/govbot/DUCKDB.md`](actions/govbot/DUCKDB.md) and
[`actions/govbot/TAGGING.md`](actions/govbot/TAGGING.md) for details.

## Docs checks

There is no markdown linter configured; before pushing docs changes, verify:

1. Every relative link target exists (`llms.txt`, `catalog.json`,
   `actions/format/docs/DATA_STRUCTURES.md`, `actions/govbot/action.yml`,
   `actions/govbot/DUCKDB.md`, `actions/govbot/TAGGING.md`).
2. Fenced code blocks are balanced (every opening fence has a closing fence).
3. `catalog.json` still parses (`python3 -c "import json; json.load(open('catalog.json'))"`).

## Opening a PR

1. Branch off `main` (`readme-27-overhaul`-style topic branches).
2. Keep the change minimal and focused; docs-only PRs should touch only docs.
3. Run the checks for what you touched:
   - `actions/govbot` (Rust): `just check` (`fmt-check` + `clippy` + `test`)
     from `actions/govbot/`.
   - Snapshot actions (Python): `./render-snapshots.sh`, then
     `../../scripts/verify-snapshots.sh __snapshots__` (or
     `examples/__snapshots__` for report-publisher) from the action dir.
   - `actions/format`: schema validation runs in CI (`.github/workflows/validate-snapshots.yml`).
   - CI runs `validate-snapshots.yml` on every pull request automatically —
     docs-only changes outside `actions/` skip those jobs by design.
4. Push and open a PR with `gh pr create` (draft for work in progress).
   Link the issue it closes (e.g. `Closes #27`).
