# Dream list — known imperfections, not blocking

Running backlog of real problems found while building toward the state audit / data
quality work, deliberately **not** being fixed right now. Current mandate: any real
data beats the zero we started from — don't gold-plate correctness on the way to
getting something working. Revisit this list once the basics are solid.

## 1. `find_new_actions`'s dedup key is fragile (found 2026-09-30)

`actions/format/utils/processing_tracker.py` — `create_action_identifier()` keys an
action purely on `f"{description}|{date}"` (string concat, scoped per-bill). Two
failure directions, severity unconfirmed against real scraper behavior:

- **False negative** (worse for an audit): a bill gets a genuinely new action with the
  *same* description+date as an existing one (e.g. a generic "Referred to Committee"
  description with no committee name, happening twice same-day to different
  committees) — the second collides with the first's identifier and never gets logged.
  A bill that really moved looks like nothing happened.
- **False positive** (noisier, self-corrects): the *same* historical action's raw
  description/date string isn't byte-stable across repeat scrapes (whitespace,
  punctuation, date precision drift) — looks like a new action, writes a spurious log
  file, makes stale data look falsely fresh.

Matters because the state audit's staleness signal (see below) depends on "a new
`logs/*.json` file appearing" meaning "something genuinely new happened." Not yet
confirmed whether either failure mode actually occurs across the 56 scrapers in
practice — worth watching for, not worth hardening preemptively.

**Concrete trigger found 2026-10-01, via the real MP future-date bug (see
`presentation-talking-points.md` item 1):** if a government source ever *corrects* a
typo we already captured, `find_new_actions` has no notion of "this supersedes that" —
it only asks "have I seen this exact description+date pair before?" A correction
changes the date, so it's a different identifier, so it's treated as a brand-new
action. Traced through what actually happens: `write_action_logs` builds the new
file's name from the *corrected* date, so there's no filename collision with the
original (wrong-dated) log file — both get written and kept permanently side by side,
never merged or overwritten. Confirmed this is **the desired behavior, not a bug** —
Tamara: "more [log files] are always better than less." Worth knowing if a bill's
`actions[]` ever shows what looks like a duplicate entry: it may be exactly this — the
original typo plus its later correction, both preserved as separate historical facts,
consistent with the project's never-rewrite-history principle. No fix needed; flagging
only so a future "why are there two of these" question isn't mistaken for corruption.

## 2. `.windycivi/latest_timestamp_seen.txt` is unreliable as a staleness signal

**Fixed 2026-09-30/10-01** on `fix/format-timestamp-tracking-accuracy` — see that
branch's commits for the full fix (gated `logs_latest_update`, added the independent
`action_log_files_created` counter, added `actions_implausible_date_fallbacks` plus a
future-date guardrail after finding the real MP typo). Original finding kept below for
context on *why* the fix looks the way it does.

Only tracked two narrow OCD record types (`events`, `vote_events`), not ordinary bill
actions — bills use a separate, newer incremental mechanism. States without
roll-call-vote or calendar-event coverage (e.g. MA, which has zero published roll-call
votes — a known, documented gap, not a bug) showed it permanently stuck at the
1900-01-01 sentinel, indistinguishable from "pipeline broken" at a glance. Also found
the per-bill `_processing.logs_latest_update` field (`actions/format/handlers/bill.py`)
had the *same* disease one level down — it was written unconditionally on every
processing run, not gated on whether anything new was actually found.
