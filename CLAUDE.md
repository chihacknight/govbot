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

- **"Where are the snapshots?"** - Each action manages snapshots via `render-snapshots.sh`. Add test data in `__snapshots__/`.

- **"CLI-first, API-second"** - Prefer shell-composable tools. Unix pipe friendliness enables automation.

## Monorepo Structure

```
actions/
  extract/      # Data extraction utilities
  fleet-monitor/     # Observability for the scraper and data-repo fleets
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
govbot load          # Load bill metadata into DuckDB
govbot build         # Generate RSS feeds
```

## DuckDB Integration

The `govbot load` command loads bill metadata into a DuckDB database for SQL analysis.

**Prerequisites**: DuckDB CLI must be installed (`brew install duckdb` or see https://duckdb.org/docs/installation/)

**How it works**:
- Shells out to `duckdb` binary (not a Rust library dependency)
- Reads all `metadata.json` files from cloned repos
- Creates `bills` table and `bills_summary` view
- Database saved to `~/govbot_data/govbot.duckdb`

**Usage**:
```bash
govbot clone all                    # First, get the data
govbot load                         # Load into DuckDB
govbot load --memory-limit 32GB     # For large datasets
duckdb --ui ~/govbot_data/govbot.duckdb # Open in browser UI
```

See `actions/govbot/DUCKDB.md` for query examples and schema documentation.

## Testing with Mock Data

Mock legislative data is available for offline development:
- Location: `actions/govbot/mocks/govbot_data/repos/`
- Contains: Wyoming (wy) and Guam (gu) sample data
- Usage: `govbot logs --govbot-dir ./actions/govbot/mocks/govbot_data`

## Pages Dashboard

The GitHub Pages dashboard's topic taxonomy lives in `scripts/govbot-dashboard.yml`
(the canonical `tags:` config the deploy workflow runs `govbot tag` against). Its topic
names must stay in sync with the keyword fallback in `scripts/dashboard_tags.json`. See
`docs/src/dashboard-guide.md` for the data flow; tagging in CI is incremental via
`scripts/filter_new_bills.py` + `scripts/tag_dashboard_repo.sh`.

The Pages site has **three dashboards plus a Site Architecture page**, linked by a tab bar:
`docs/src/dashboard/index.html` (the Legislation Dashboard above),
`docs/src/dashboard/hearings.html` (**Committee Hearings & Witness Slips**),
`docs/src/dashboard/elections.html` (**Elections Happening in IL**), and
`docs/src/dashboard/architecture.html` (a static, no-data explainer of all three backend
pipelines — keep its tab bar and the `.tab-arch` accent in sync with the other pages
whenever the tab bar changes). Tab order is Legislation · Hearings · Elections Happening in IL ·
Site Architecture across all four pages, with accents `.tab-legis` (blue), `.tab-hearings`
(gold), `.tab-elections` (green), `.tab-arch` (purple). All four pages share a floating
`.to-top` "Back to top" button (fixed bottom-right, shown after ~400px of scroll). The
elections page additionally has a **"New Design"** switch under the theme toggle that sets
`data-design="new"` on `<html>` (persisted in `localStorage['govbot-elections-design']`),
which applies a Robinhood-inspired override skin (bright green #00C805, near-black/white
ground, flat rounded cards) via `:root[data-design="new"]` token + component rules placed
last in that page's stylesheet; it is scoped to elections.html only. The hearings
page is a *separate* pipeline: `actions/scrape-hearings/` taps ilga.gov, leg.wa.gov,
malegislature.gov, and akleg.gov directly (not OpenStates), plus **USA (Federal)** open comment periods from the
Regulations.gov API (needs `REGULATIONS_GOV_API_KEY`; falls back to the committed
`actions/scrape-hearings/federal_seed.json` when unset/unreachable) — federal leads the
list, above the states. It writes `docs/src/dashboard/hearings.json` + a whole-calendar
RSS `hearings.xml` + granular RSS feeds under `docs/src/dashboard/hearings/` — per bill
(`<jurisdiction>-<NORMALIZED_ID>.xml`), per jurisdiction (`<code>.xml`), and per hearing
(`hearing-<id>.xml`) — so a reader can follow one bill, a whole state, or a single hearing
(schema `schemas/govbot.hearings.schema.json`), plus a static 56-jurisdiction participation
directory `docs/src/dashboard/participation.json` (schema
`schemas/govbot.participation.schema.json`). `deploy-docs.yml` rebuilds both the bill
`data.json` and the hearings feed on the twice-daily schedule. Hearings parsers are
offline-snapshot-tested: `python3 actions/scrape-hearings/test_scrape_hearings.py`.

The **Elections Happening in IL** page is a *third* pipeline: `actions/scrape-elections/` builds
`docs/src/dashboard/elections.json` (schema `schemas/govbot.elections.schema.json`) — every
office on upcoming Chicago/Illinois ballots (citywide, Alderperson wards 1–50, CPS board
president + subdistricts 1A–10B, and 22 Police District Councils). The ballot *structure*
(offices, districts, ballot dates, and a "why this race exists" note) is a committed seed,
`actions/scrape-elections/elections_seed.json`; the scrapers only *populate candidates* onto
it from official candidate lists (Chicago Board of Elections; Illinois SBE "Who Is Running";
Cook County Clerk, future). A candidate attaches to a race only when office+district resolve
exactly (`race_id_for`) — unplaceable rows are dropped, never invented, and a race with no
confirmed candidate keeps an empty list + a source link. It also writes a whole-ballot RSS
`elections.xml` + granular feeds under `docs/src/dashboard/elections/` (per office group
`group-<group>.xml`, per race `race-<id>.xml`). It also attaches a top-level
`springfield` list — the **"rules of the game"**: IL bills from the legislation
`data.json` tagged `elections & voting` or `education` (the elected CPS board, ward/runoff
rules, campaign finance), cross-referenced with `hearings.json` for upcoming ILGA hearings,
shown on the page as context *beside* the races (never mixed into candidate lists) plus a
`springfield.xml` feed. `deploy-docs.yml` runs this after `data.json`+`hearings.json` are
built so it reads the fresh copies. Fail-soft: with sources down the seed's structure still
ships (empty rosters/springfield), and the deploy keeps the committed sample unless the
fresh run produced candidates or Springfield bills. Parsers are offline-snapshot-tested:
`python3 actions/scrape-elections/test_scrape_elections.py`.

Per-race **locator maps** come from a separate action, `actions/scrape-maps/`: it fetches
ward (`p293-wvbd`) + police-district (`24zt-jpfn`) boundaries from the City of Chicago Data
Portal, projects + Douglas-Peucker-simplifies them at build time, and writes a compact
`docs/src/dashboard/maps.json` (`{view, context, districts}` keyed by race id). The elections
page draws each race's ward/police polygon as an inline-SVG locator inside a light city
outline (citywide offices tint all of Chicago); CPS subdistricts have no published polygon
so their map is omitted. Fail-soft: a portal outage leaves the committed `maps.json` in
place. Geometry helpers are offline-tested: `python3 actions/scrape-maps/main.py --self-test`.

**Campaign money** (Illinois SBE) attaches to each candidate via the SBE ID crosswalk
(candidate name → `Candidates.txt` ID → `CmteCandidateLinks` → `Committees` → latest
`D2Totals` row): receipts, spending, cash on hand. Only unambiguous name matches are kept
(never fuzzy dollar matching). Because the SBE bulk files are ~70MB, `deploy-docs.yml`
runs it as a **separate step gated on candidates being present** —
`main.py --enrich-money docs/src/dashboard/elections.json --money-dir <sbe-files>` — so the
committed sample (empty rosters) carries no money. Parsers/aggregation are offline-tested
in `test_scrape_elections.py`.

**Results** (post–Election Night) are scaffolded: each race can carry a `results` block
(per-candidate votes/%/winner, precincts reporting) attached by
`main.py --enrich-results <elections.json> --results-file <csv>` from the authority's
results export (Chicago BOE / Cook County Clerk). Header-driven + fail-soft; it counts every
reported candidate (official results are authoritative) and flags a winner only when the
source does — never projected. The deploy step runs only when the `ELECTION_RESULTS_URL`
repo variable/secret is set, so it is inert until an election happens. This completes the
"five drawers" per race: map · candidates · money · results · context (Springfield).

## govbot Development

```bash
cd actions/govbot
just setup           # Install Rust toolchain and dependencies
just test            # Run snapshot tests
just review          # Review snapshot changes (insta)
just govbot logs     # Run CLI in dev mode (uses mocks/govbot_data)
just mocks wy il     # Update mock data for testing
```

## When in Doubt

1. Check existing snapshots for expected behavior
2. Look at similar actions for patterns
3. Prefer explicit failure over silent corruption
4. Keep changes minimal and focused
5. Consider the data pipeline as a whole, not just isolated components
