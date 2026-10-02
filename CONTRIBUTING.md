# Contributing to govbot

Thanks for contributing! govbot is a monorepo of small, self-contained data-pipeline
modules ("actions") that turn U.S. legislative updates into git repositories of JSON
data. This guide distills the working rules from `CLAUDE.md` (the full
contributor reference — read it before making changes).

## Getting oriented

- `actions/` — self-contained modules (run as shell scripts or GitHub Actions):
  `extract`, `fleet-monitor`, `format`, `govbot` (the Rust CLI), `pipeline-manager`,
  `report-publisher`, `scrape`, `scrape-hearings`, `scrape-elections`, `scrape-maps`, `mcp`.
- `schemas/` — shared JSON Schemas for cross-language validation.
- `scripts/` — repo-level utilities (dashboard tagging, roster builds).
- `docs/` — GitHub Pages dashboards + guides.
- `llms.txt` + `catalog.json` (repo root) — the AI-readable catalog guide and the
  machine-readable directory of every jurisdiction data repo. **Keep both in sync
  with the real data layout** (the authoritative per-repo pattern lives in each
  data repo's own `data.json`); the README's "Read it from an AI assistant"
  section links them.

## Requirements for each action

Every action must:

1. Run as a basic script with args (Python, Bash, Rust, or TypeScript — no hidden
   state; portable by default, CLI-first and pipe-friendly).
2. Ship an `action.yml` so it runs as a GitHub Action.
3. Define its types in a `schemas` folder using JSON Schema (schema-first: define
   the shape of data before writing transformation code).
4. Keep `__snapshots__/` with real outputs: they show expected results AND serve
   as inputs for downstream snapshot tests. Each action manages its own snapshot
   rendering through a `render-snapshots.sh` script.

## Working rules

- **Smallest change that solves it.** A bug fix is not a refactor opportunity.
- **Offline-first.** Snapshots and mock data exist so development and tests run
  without network access. Never require live government sources in tests —
  government data sources are notoriously unreliable.
- **Idempotency is non-negotiable.** Running a pipeline twice must produce the
  same result; no accumulating side effects.
- **Trace data lineage.** Every output should carry metadata about when and how
  it was fetched.
- **Fail loudly, recover gracefully.** Validation errors halt pipelines; missing
  *optional* data does not. Prefer explicit failure over silent corruption.
- **State-level work parallelizes; large datasets stream.** Don't load whole
  datasets into memory; consider what happens at 10x scale.
- **Government data has edge cases — document them inline**, not in external docs
  that drift. Add comments for non-obvious handling.
- **Error messages must let the next person (or agent) self-correct**: say what
  was expected, what was found, and how to fix it.

## Testing

- If a change affects output, update or add snapshots (`__snapshots__/` +
  `render-snapshots.sh`; Rust `cargo insta` flow in `actions/govbot`).
- Mock legislative data (Wyoming + Guam samples) lives at
  `actions/govbot/mocks/govbot_data/repos/` — use it for offline development:
  `govbot logs --govbot-dir ./actions/govbot/mocks/govbot_data`.
- Offline test suites (all stdlib, no network):
  `actions/scrape-hearings/test_scrape_hearings.py`,
  `actions/scrape-elections/test_scrape_elections.py`,
  `scripts/test_build_people_roster.py`, plus
  `python3 actions/scrape-maps/main.py --self-test`.
  Run them from the repo root with `just test` (see the root `justfile`), or
  directly — each file runs standalone, e.g.
  `python3 actions/scrape-hearings/test_scrape_hearings.py`.
- Rust CLI (`actions/govbot`): `just setup`, `just test`, `just review`,
  `just check` (fmt + clippy + tests). Review snapshot diffs with
  `just review` before accepting.

## Dashboards

The Pages dashboards share a tab bar and conventions across
`docs/src/dashboard/{index,hearings,elections,architecture}.html` — tab order
(Legislation · Hearings · Elections Happening in IL · Site Architecture), the
`.to-top` button, feed XSL styling (`feed.xsl`), Central-time feed dates, and
per-page design skins. See `CLAUDE.md` ("Pages Dashboard") and
`docs/src/dashboard-guide.md` before touching dashboard pages, and keep the
taxonomy in `scripts/govbot-dashboard.yml` in sync with the keyword fallback in
`scripts/dashboard_tags.json`.

## Pull requests

1. Branch from `main`, keep the change focused.
2. Update/add snapshots for any output change; run the relevant offline suites.
3. Keep `llms.txt`, `catalog.json`, and the README catalog section in sync when
   the data layout changes.
4. Describe the data-flow impact (source → transform → snapshot → dashboard).
