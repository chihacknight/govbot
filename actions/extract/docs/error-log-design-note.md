# Extraction Error Log — Design Note

**Status:** Not built yet. Written 2026-07-14 to capture the idea before implementing, so it
doesn't get lost mid-investigation. Companion to
`actions/pipeline-manager/docs/staleness-audit-spec.md`, which is the same kind of "figure
out what to build, write it down, build it later" note for a related problem.

## The problem

`extract-text.yml` currently treats **any single failed bill as a hard job failure** —
`conclusion: failure`, exit code 1 — regardless of whether it's 1 bill out of 6,640 or a
sign of something systemically broken. That was a deliberate choice (don't let missed bills
go unnoticed), but it has a real cost: a state with 5 known, minor, already-understood dead
links (e.g. HI's `data.capitol.hawaii.gov` 404s) looks exactly as broken in a status check
as a state that's fully blocked. There's no way to tell them apart without opening the log
every time, which defeats the point of having a status check at all.

## The fix: separate "did the job complete" from "were there errors"

- **Job outcome** should reflect whether the extraction process ran to completion, not
  whether every individual bill succeeded. A run that finishes with 5 known misses is a
  fundamentally different situation from one that crashed or got blocked mid-run, and the
  job status should say so.
- **Per-bill error tracking** should still happen — losing that visibility is not the goal —
  it just shouldn't be the same signal as the job's exit code.

## Where to put the error list: a git-tracked JSON file, not an external service

Recommend something like `.windycivi/extraction-errors.json` in each state repo, rewritten
each run with the currently-known failures (bill ID, source URL, error type, timestamp).
Reasons to do it this way rather than reaching for a database or a tracking service:

- Matches the project's existing principle that git history is the tamper-evident source of
  truth (see `[[project-govbot-immutability-principle]]` in Claude memory) — no new external
  dependency, and every run's version is preserved automatically since it's just a commit.
- `git log` on that one file becomes the audit trail for free — when a bill started failing,
  when (if ever) it got fixed, whether it's a one-off or recurring.
- Same shape as `scrape-summary.json`, which `scrape.sh` already writes today. This is doing
  the same thing one layer over, for extraction instead of scraping — not a new pattern, an
  extension of one that already exists.

Keep the existing Slack notification step, but treat it as a doorbell, not the filing
cabinet — Slack messages scroll away, the committed JSON file is the persistent record.

## Seeing it across all states at once

The staleness-audit script (`actions/pipeline-manager/scripts/audit-data-staleness.sh`)
already establishes the pattern for "loop over every repo, pull one signal, build one
table." The same shape works here: loop over every `govbot-test` (soon to be `govbot-data`)
repo, read `.windycivi/extraction-errors.json`, build a table of which states have
outstanding extraction errors, how many, and since when — without needing to open 56 repos
individually.

## Open question, not resolved here

Whether "job completed but had errors" should still trigger *some* visible signal in the
Actions UI (a warning annotation, a specific job summary section) versus relying entirely on
the committed error file + Slack. Worth deciding when this actually gets built, informed by
how it feels to use in practice — not worth over-designing now.
