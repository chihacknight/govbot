# AGENTS.md

Instructions for AI coding agents working in this repo. The full contributor
reference is [`CLAUDE.md`](CLAUDE.md); the contributor workflow is
[`CONTRIBUTING.md`](CONTRIBUTING.md). This file is the short pointer sheet.

## What this is

**govbot** — a monorepo turning U.S. legislative updates (56 jurisdictions) into
git repositories of JSON data. `actions/` holds self-contained modules that run
as shell scripts or GitHub Actions. Git repos are the datasets; snapshots are
the tests.

## Layout

- `actions/govbot/` — Rust CLI (`cargo` + `just`; see its `justfile`: `setup`,
  `test`, `review`, `check`, `govbot`, `mocks`, `tag`)
- `actions/scrape*/`, `actions/format/`, `actions/extract/`, `actions/report-publisher/`,
  `actions/pipeline-manager/`, `actions/fleet-monitor/`, `actions/mcp/` — Python/shell/TS pipeline modules
- `schemas/` — shared JSON Schemas (validate against these)
- `scripts/` — repo-level utilities (dashboard tagging, people roster)
- `docs/` — GitHub Pages dashboards (Legislation · Hearings · Elections · Architecture)
- `llms.txt` + `catalog.json` — AI-readable catalog guide + machine-readable repo directory

## First commands (repo root)

```bash
just test    # offline Python suites (stdlib unittest, no network) + scrape-maps self-test
just check   # cargo fmt --check + clippy in actions/govbot (needs Rust toolchain)
just info    # toolchain status + task list
```

Rust CLI dev: `cd actions/govbot && just setup && just test`.
Offline mock data: `actions/govbot/mocks/govbot_data/repos/` (Wyoming + Guam samples).

## Rules that matter most

1. Additive, minimal changes. A bug fix is not a refactor.
2. Offline-first: tests must pass with no network. Use mocks/snapshots, never live sources.
3. Output change → snapshot change (`__snapshots__/` + `render-snapshots.sh`; `cargo insta` for Rust).
4. Schema-first: types live in `schemas/` as JSON Schema.
5. New actions need `action.yml` + `schemas/` + `__snapshots__/`.
6. Data paths look like `country:us/state:wy/sessions/2025/bills/HB0001/metadata.json`
   — the `:` characters are legal on Linux/macOS but **cannot be checked out on
   Windows (NTFS)**. On Windows use a sparse checkout excluding those subtrees.
7. Keep `llms.txt`, `catalog.json`, and the README catalog section in sync when
   the data layout changes.

## When in doubt

Check existing snapshots for expected behavior, mirror a sibling action's
patterns, fail explicitly (say what was expected, what was found, how to fix),
and keep the data pipeline as a whole in mind — not just the isolated piece.
