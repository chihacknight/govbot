# Lean data org (goal 7) — next, after the current work

**Folder:** none yet · **Branch:** none yet · **Start:** after the JSONL conversion is pushed and
the Python fix is merged. Target: a design and one pilot state before the December presentation.

## Kickoff prompt

> Read `tamara-notes/processes/handoff-2026-11-24.md` and
> `tamara-notes/processes/workstreams/lean-org.md`, then help me design the lean data org.
> Start with the open questions. Don't create repos or orgs yet.

## Goal

The data repos are too big, mostly because of the bill PDFs stored in each bill's `files/`
folder. Earlier we decided on two orgs:

1. **The full org**, structured as `govbot-data` is today, PDFs included.
2. **A lean org** without the PDFs. Instead it holds everything we can extract from each bill.
   What can be extracted differs by state, so the extraction is its own project.

## How big the problem is (measured 2026-11-25 on the drive's live clones)

| Repo | Total on disk | Git history | `files/` folders |
|---|---|---|---|
| CT | 1,058 MB | 439 MB | 578 MB |
| MI | 1,017 MB | 200 MB | 733 MB |
| WY | 201 MB | 89 MB | 97 MB |

## Constraints already decided

- **Git history is never rewritten.** It is the tamper-evident record. So the PDFs stay in the
  full org's history forever, and the full org will not get smaller. Only the lean org is lean,
  because it starts as new repos. No Git LFS and no external storage for authoritative content.
- **The full org stays the source of truth.** The lean org is derived from it. Each lean record
  should say which full-org commit it came from, so it can be traced back.
- **This is the full-text project.** Per-state extraction (`files/`, `actions/extract`) was
  already planned as the next project after the scrapers work. The lean org is where its output
  lives.

## Open questions

1. What is the lean org called, and what does a lean bill folder contain? Metadata and the JSONL
   logs, plus extracted text, structured fields, or both?
2. Does the lean org also use one repo per state per session (goal 1)? If so, build both at once
   with the repo-rewrite chat, so new repos are created only once.
3. Which org do readers use: `govbot clone`, `govbot load`, the MCP server, the site's downloads,
   `catalog.json` and `llms.txt`? AI agents probably want the lean one.
4. Which state is the pilot? Pick one whose bill text is easy to extract.
5. How does the lean org stay current: a workflow triggered by each full-org commit, or a
   nightly job?

## Status

- 2026-11-25: recorded. Not started.
