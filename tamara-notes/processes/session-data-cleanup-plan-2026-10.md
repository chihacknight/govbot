---
name: session-data-cleanup-plan-2026-10
description: Plan for cleaning up messy/duplicated/possibly-cross-session govbot-data (and legacy) repos before archiving each state to a clean "1 repo = 1 state session" record via close_session.py. Drafted 2026-10-03, not yet reviewed or started -- read top-down before picking this up.
metadata:
  type: project
---

# Session data cleanup — plan (drafted 2026-10-03, not started)

**Status: planning only.** Nothing in this doc has been executed. Written up at the end of a
long session so the plan survives to be picked up fresh, not re-derived from scratch.

## Goal

Before archiving each state's 2025/2026 session data (via `close_session.py`, which already
exists and handles the actual repo-transfer/rename/re-create mechanics), get to a state where
it's true that **1 repo = 1 state session** — clean, deduplicated, not bleeding across session
boundaries, and reflecting *current* formatting logic (not whatever bugs existed when the data
was first processed). Right now that's not reliably true, and the scale of the mess isn't
fully characterized yet.

## Context — what prompted this

Reviewing three GitHub orgs Tamara flagged as holding "a bunch of old repos with lots of messy
data": `windy-civi-pipelines-V1-archived`, `windy-civi-pipelines`, `govbot-archive`.

**What's actually in each (confirmed 2026-10-03):**
- `windy-civi-pipelines-V1-archived` (94 repos) — a pre-govbot prototype generation
  (`*test*`/`*old*`/`*-with-text-archive` naming), last touched Oct 2025–Mar 2026. Looks fully
  superseded by the current architecture.
- `windy-civi-pipelines` (60 repos) — the architecture *before* govbot split scraping and
  formatting into two orgs (one combined `<state>-data-pipeline` repo instead of today's
  `govbot-openstates-scrapers` + `govbot-data` split), last touched Oct–Dec 2025. Also looks
  superseded.
- `govbot-archive` (100 repos) — **this one is live infrastructure, not just old cruft**: it's
  `close_session.py`'s actual default `--archive-org` target. But it currently holds **three
  confusingly similar generations per state**, not one:
  1. The real live repo — lives in `govbot-data`, not `govbot-archive`, so not confused with
     the other two directly, but worth naming for contrast.
  2. `<state>-legislation-pre-rebuild-2026-07-21` — the legitimate July 21 rebuild safety
     snapshot. Properly GitHub-archived (read-only), clearly named, clearly dated.
  3. **A bare `<state>-legislation` (no suffix)** — confirmed present for every state checked
     (ct, mo, oh, pa, mt, usa, wa). Created **2025-11-26/27**, last pushed **2026-07-15** (the
     same date across every state checked — a batch cutover, 6 days before the rebuild), much
     smaller than the live/pre-rebuild repos (3-27MB vs. 400+MB), and critically **not
     GitHub-archived** despite sitting in the org literally named "archive." Confirmed same
     real pipeline shape (`country:us/`, `.windycivi/`) via a direct content check on
     `mo-legislation` — so it's a genuine earlier generation of real data, not junk, just
     superseded and orphaned. This is a real collision/confusion risk for `close_session.py`
     going forward: it writes into `govbot-archive` by name, and an unarchived same-named repo
     already sits exactly where a future close-out would try to write.
- A spot-check of the **current live** `govbot-data/ct-legislation` repo looked clean on the
  surface (one session folder, human-readable bill-ID folder names like `HB05001`, not raw
  UUIDs — `actions/format` already collapses scraper-side UUID duplicates by the time data
  lands here). So the suspected mess is probably concentrated in the old/archived generations
  and in whatever `actions/format` hasn't caught, not uniformly everywhere — not yet confirmed
  at scale.

**Resource note:** space is no longer the constraint it was earlier this session (a 1TB SSD
removed that pressure) — full local clones across generations/states are viable now if needed,
not just API-based sampling. Worth deciding per-step which is actually faster/simpler, not
defaulting to one or the other on space grounds alone.

## Proposed method (refined from Tamara's initial sketch, not yet executed)

Two separate checks, not one combined pass — they catch different things and conflating them
will produce confusing results:

1. **Duplicate / cross-session-bleed detection.** Does a bill identifier appear more than once
   within a session, or appear in more than one session folder when it shouldn't? This needs
   its own detection method (likely: enumerate every bill-ID folder per session per repo,
   flag any identifier collision within a session and any identifier appearing in multiple
   session folders for the same state) — *before* or *alongside* enumeration, not inferred
   from formatting results.
2. **Format-correctness check against current logic.** For each distinct bill, sample one
   metadata file (maybe a few, if a bill's shape genuinely needs more than one representative
   file to judge) and run it through the *current* `actions/format` pipeline. Compare the
   freshly-generated output against what's actually committed. A real diff means the committed
   data reflects formatting logic that's since been fixed/changed (confirmed this has happened
   multiple times this session alone: shrink-guard identifier logic, timestamp tracking,
   vote_event handling) and is a candidate for reformatting before archiving.

**Open design question, not yet decided:** what counts as a mismatch worth acting on vs. noise?
Needs a threshold/triage rule before running this at scale, or the output will be unreadable.

## Suggested sequence

1. **Pilot on 1-2 known-messy states first** — CT or MO look like reasonable candidates (both
   have historical shrink-guard/duplicate-bloat findings in `tamara-notes/archived_docs/`).
   Validate the whole method end-to-end before committing to all 56 states.
2. Build/decide the dedup + cross-session-bleed detection method, test it on the pilot state(s).
3. Build/decide the format-re-check method (sample → run through `actions/format` → diff
   against committed), test it on the same pilot state(s).
4. Decide the mismatch threshold/triage rule from what the pilot actually turns up — don't
   guess ahead of real data, same principle the daily digest's noise filter and the flatline
   check's exceptions were built on.
5. Roll out to the remaining states, prioritizing ones closest to session close (ties back to
   `tamara-notes/state-specific/` and `docs/src/state-status-reference.md` for current
   scraper-health status — don't archive a state's data while it's still silently broken).
6. Separately: resolve the `govbot-archive` orphan-generation collision risk (decide: archive
   the bare orphans in place, delete them, or something else) before `close_session.py` gets
   run in earnest across many states — don't let a future close-out collide with leftover
   clutter from a prior generation.
7. Only then: run `close_session.py` per state as each 2025/2026 session is confirmed closed.

## Not yet done / explicitly out of scope for this doc

- No repos have been downloaded, deleted, archived, or renamed as part of this investigation —
  tonight's work was read-only reconnaissance via the GitHub API.
- The two legacy orgs (`windy-civi-pipelines-V1-archived`, `windy-civi-pipelines`) are treated
  as a separate, lower-urgency cleanup (confirm fully superseded, then likely delete) — not
  blocking the `govbot-data`/`govbot-archive` cleanup above, and not covered further here.
- The dedup/cross-session-bleed detection method and the format-recheck method are both
  unbuilt — this doc only sketches the shape, not an implementation.
- Mismatch threshold/triage rule: undecided, deliberately, until real pilot data exists.

## Related

- `actions/pipeline-manager/close_session.py` — the existing, human-triggered archival
  mechanism this whole effort is building toward actually using.
- `tamara-notes/state-specific/README.md` — current per-state scraper-health status, needed
  before archiving any state's data (don't archive a state that's still silently broken).
- `tamara-notes/archived_docs/` — `state-problems.md`, `scraper-health.md`, and others hold
  the historical shrink-guard/duplicate-bloat findings (CT, MO, OH, PA, PR, USA, MT) that
  motivate starting the pilot there.
