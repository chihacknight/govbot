# Plan: split raw bill files into a companion repo + build real data-quality signal

**Status:** Drafted 2026-09-29, not yet reviewed/approved. Review before starting any
implementation.

## Context

govbot publishes all 56 US jurisdictions' legislation as git repos so the history
itself is tamper-evident ("Bill Blockchain") — no LFS, no external object storage,
no history rewriting, ever. Today each jurisdiction's `govbot-data/{code}-legislation`
repo holds `metadata.json` + `logs/*.json` + `files/*` all interleaved per bill
(`country:us/state:{code}/sessions/{session}/bills/{id}/`), and `files/` (raw PDFs,
XML, HTML, plus small extracted-text) is by far the bulk of every clone's size for
PDF-heavy states.

Tamara owns this entire data layer (`scrape`, `format`, `extract`, `pipeline-manager`)
and is the only person on the volunteer team who understands its failure modes.
Teammates build on top of it without that visibility — most notably a newly-merged
MCP server + `govbot query` Rust engine (`actions/mcp`, `actions/govbot/src/query/`)
that already lets an AI agent answer questions about legislation by reading
`metadata.json`/`logs/*.json` (confirmed: **nothing existing reads `files/` at all**),
plus a zero-install `llms.txt`/`catalog.json` path for any AI assistant to do the same
directly over raw GitHub URLs, citing the official government source for bill text.

Two problems, one fix:
1. **Repo bloat** — every clone of a PDF-heavy state's data repo pulls every historical
   PDF ever committed, even though nothing consuming this data today needs `files/`
   colocated with `metadata.json`.
2. **No real health signal** — the team's only per-jurisdiction data-quality tool today
   (`govbot query coverage`) describes *what's present* (bill/vote counts, roll-call
   granularity) but has zero concept of staleness or completeness — it never touches
   git history. The open question from `56-state-audit-plan.md` ("what counts as
   confirmed-legit data") was never answered.

Because sessions are out for most states until ~Jan 2027, this cycle's already-scraped
data is being treated as a playground: build and validate the target architecture now,
against real data, so it's simply *live* when real sessions resume — not a migration
of existing repos (their history stays as-is, per the no-rewrite rule), a change to
where *new* data lands going forward. Sartaj (co-maintainer) has already given the
go-ahead for a change of this size.

## Confirmed groundwork (this session)

- `files/` is populated **exclusively by `actions/extract`** — `actions/format`'s
  `handlers/bill.py:60` only `mkdir`s an empty `files/` dir; it never writes content
  into it. So the split is an `actions/extract` git-logic change, not a `format` one
  (format needs one small cleanup, see below).
- `actions/pipeline-manager`'s session-archival code (`close_session.py`) already
  proves the exact pattern needed: provisioning a new per-jurisdiction repo is a
  generic, config/template-driven call to `apply.py`'s `create_repo()` — the same
  function ordinary repo provisioning already uses, invoked via the existing
  scrape-config/files-config "mirrored pair" pattern (`chn-openstates-scrape.yml` /
  `chn-openstates-files.yml`). No bespoke GitHub API work needed.
- The `govbot` Rust CLI's `clone` is currently a **hardcoded one-repo-per-locale**
  model (`git.rs`'s `DEFAULT_REPO_URL_TEMPLATE`, one `{locale}` substitution, no
  concept of multiple repo *roles*). Teaching it to also fetch a companion files-repo
  is a real but contained change (a second template + clone path in `git.rs`, plumbing
  through `pipeline.rs`/`config.rs`). **Nothing needs this today** (no consumer reads
  `files/`), so it's deferred, not blocking.

## Plan

### Phase 1 — Provision the companion repo type (pipeline-manager)
Add a third repo per jurisdiction: `govbot-data/{code}-legislation-files`, holding
just `files/` (PDFs/XML/HTML + `_extracted.txt`). Mirror the existing two-config
pattern:
- New `actions/pipeline-manager/chn-openstates-files-raw.yml` (locales, same 56 codes)
- New template `actions/pipeline-manager/templates/openstates-files-raw/` (minimal —
  this repo has no scheduled workflow of its own; `extract` pushes to it directly)
- Provision via the existing `apply_mod.create_repo()` path `close_session.py` already
  uses — no new GitHub API code required.
- **Pilot on a handful of states first** (`al, ak, de, wy, sd` — `render.py`'s own
  existing default test-state set) before rolling to all 56, consistent with how every
  prior rollout on this project has been staged.

### Phase 2 — Split `actions/extract`'s git logic
Today `action.yml` checks out one repo and does one commit/push cycle for
`country:us/` + `.windycivi/` (main.py → `text_extraction.py` writes `files/` content
directly into the checked-out tree). Change:
- Check out **two** repos in the action: the data repo (as today) and the new files
  repo (new, at a second path).
- Route `text_extraction.py`'s content-writing calls (`open(content_file, ...)` in
  the pdf/xml/html extractor save paths) to write under the files-repo's path instead
  of the data-repo's tree.
- Split the commit/push step into two — same auto-commit/conflict-resolution pattern
  already used (30-min periodic commits, `git checkout --theirs`/`--ours` merge
  handling), just duplicated per repo instead of one shared tree.
- `metadata.json`'s `_processing.text_extraction_latest_update` timestamp (what drives
  incremental skip logic) stays in the data repo — unaffected.

### Phase 3 — Clean up `actions/format`
- Drop the now-pointless empty `files/` `mkdir` in `handlers/bill.py:60` (nothing
  will ever populate it in this repo anymore).
- Remove the `git checkout --theirs "**/files/"` line from `format/action.yml`'s
  merge-conflict step — dead code once `files/` no longer lives in this repo's tree.

### Phase 4 — Give `govbot query coverage` a real staleness signal
Extend `actions/govbot/src/query/mod.rs`'s `CoverageReport`/`coverage_for()` (currently
computed purely by scanning the working tree, no git history at all) with the same
signal `actions/pipeline-manager/scripts/audit-data-staleness.sh` already proved out
manually: the most recent commit that actually touched a `sessions/` path (not the
noisy daily tracking-file commit). Surface it as a new field plus a plain-English
caveat in the same style as the existing roll-call-data caveats, so it's visible
automatically wherever `coverage` is called — CLI, MCP, everywhere — without anyone
needing tribal knowledge of the staleness trap. This is the "data quality" story for
Dec 15, built on top of a teammate's existing, tested surface rather than a competing
tool.

Full bill-*count* completeness (cross-checking against an outside source) stays
blocked on the still-unapproved LegiScan API key — note it as a known gap in the
caveats rather than trying to solve it now.

### Deferred, not blocking Dec 15
- Teaching `govbot clone`/MCP to fetch the new files-repo (Phase 1's groundwork makes
  this possible later; nothing needs it until full-text Q&A over extracted bill text
  is actually built).
- Migrating/backfilling existing repos' historical `files/` content into the new
  companion repos — explicitly out of scope; old repos keep their full history as the
  archive, per the no-rewrite rule. Point people at `git clone --filter=blob:none` for
  today's repos in the meantime (already the project's own audit-tooling technique).

## Verification
- Phase 1: `apply.py --dry-run --test-states al,ak,de,wy,sd -c chn-openstates-files-raw.yml` shows 5 repos to create, 0 errors; then apply for real on just those 5.
- Phase 2: run `extract` manually (`workflow_dispatch`) against one pilot state, confirm `files/` content lands in the new companion repo (not the data repo) and `metadata.json`/`_extracted.txt` pointers still resolve; confirm the data repo's diff no longer touches `files/`.
- Phase 3: re-run `format` on a pilot state, confirm no `files/` dir gets created in the data repo anymore, confirm no merge-conflict regression on a forced concurrent run.
- Phase 4: `cargo test` in `actions/govbot` (add a unit test for the new staleness field, since `coverage_for` currently has none), then `govbot query coverage --jurisdiction wy` against real cloned data and confirm the caveat text reads correctly.

## Still open / to discuss tomorrow
- Exact naming for the companion repo (`{code}-legislation-files` used above as a
  placeholder — confirm before Phase 1).
- Whether the companion repo needs any workflow of its own, or is purely a push
  target for `extract`.
- Sequencing against the rest of the Dec 15 prep (this plan covers architecture;
  still need to fold in the earlier discussion about scoping "full text extraction
  for all 56" down to "for every state where it's structurally feasible").
