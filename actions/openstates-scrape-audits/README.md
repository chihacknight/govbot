# OpenStates Scrape Audits

Two independent, complementary checks catch scraper problems that a green GitHub Actions
checkmark hides. Neither replaces the other — they watch for different failure shapes on
different cadences.

**Scope — OpenStates pipeline only.** This covers `actions/scrape/` (the OpenStates-based
bill scraper, `chn-openstates-scrape.yml`, the `govbot-openstates-scrapers`/`govbot-data`
orgs) specifically — hence "openstates" in the name. It has **no visibility into the other
scraper pipelines** in this repo: `actions/scrape-elections/`, `actions/scrape-hearings/`,
`actions/scrape-maps/`. Those would need their own equivalent checks if/when they need one;
nothing here reads their output.

**Why its own action, separate from `actions/pipeline-manager/`:** pipeline-manager's job is
repo/template provisioning — generating and pushing the per-state workflow files, managing
which locales exist, flipping active/paused status. This is a different concern: watching the
*output* of the OpenStates scrapers for health problems. The two share one real dependency
(reading pipeline-manager's `chn-openstates-scrape.yml` for the active/paused locale list, via
a relative path — see each script's header), but that's a read of one config file, not shared
ownership. Keeping this as its own action means someone looking at `actions/fleet-monitor/`
(the other observability tool in this repo, built independently) can find this and understand
what it does without first untangling it from template provisioning.

## Layout

```
weekly-scraper-audit.py          the production checks (this README documents both)
daily-scraper-error-digest.py
output/
  audit_tracking.json            live state the weekly audit commits back each run --
                                  separate from the code so a scheduled run's output diff
                                  never looks like a code change in git history
internal/                        manual investigation scratch work from building this
                                  (one-off scripts, raw per-state audit output, planning
                                  notes) -- kept for reference, not part of the production
                                  path; internal/archive/ holds superseded drafts
```

## Why this exists

A scrape workflow can show **green** while real data collection is actually broken, in two
distinct ways:

1. **Silent, sustained drift** — a scraper keeps "succeeding" every day but has stopped
   actually finding new bills (confirmed on UT: 6 consecutive days of byte-identical output,
   every run reporting success).
2. **A masked per-run failure** — a scrape crashes, falls back to the last good nightly
   snapshot, and the whole job still reports `success` because the fallback kept the pipeline
   moving. Confirmed live on `usa-legislation` (2026-10-02): an unhandled `KeyError` crashed
   the scrape, got misclassified as a rate-limit issue by `scrape.sh`'s failure-type regex (a
   bare `429` false-matched a logged bill number, `HR 429`), fell back to nightly data, and
   nothing surfaced anywhere except the raw Action log.

Neither case trips GitHub's own failure notifications (those only fire on a genuinely red
job), and neither is visible without opening the run and reading the log by hand.

## The two checks

| | **Weekly Scraper Audit** | **Daily Scraper Error Digest** |
|---|---|---|
| Catches | Silent bill-discovery drift (type 1 above) | Per-run failures masked by fallback, plus runs that never complete (type 2 above) |
| Cadence | Sundays, 13:00 UTC | Every day, 13:00 UTC |
| Reads | `new_bills_seen` histogram (`govbot-data/*`), `warning_history.json` (`govbot-openstates-scrapers/*`) | `failure_type`/`error_summary` in `warning_history.json`, plus one live GitHub Actions API check per active state |
| Script | `weekly-scraper-audit.py` | `daily-scraper-error-digest.py` |
| Workflow | `.github/workflows/weekly-scraper-audit.yml` | `.github/workflows/daily-scraper-error-digest.yml` |
| Output | "Weekly Scraper Audit" tracking issue | "Daily Scraper Error Digest" tracking issue |

Both fetch everything **live**, with no local clone and no `GITHUB_TOKEN` needed for the
committed-file reads (`raw.githubusercontent.com` is unauthenticated) — a stale local clone
once produced false flags on five states that had actually committed hours earlier, so this
is a deliberate design choice, not an oversight.

### Weekly Scraper Audit — bill-discovery flatline

Flags any **in-session** state with **7+ consecutive days of zero new distinct bills**. Zero
is the trigger, not "low" — a low-but-nonzero trickle late in a session is normal and
confirmed empirically not to need flagging. Three states (`gu`, `or`, `nv`) are hard-coded
exceptions because their session *structure* front-loads bills early, confirmed via a
bill-introduction-date concentration scan, not guessed.

A separate, **not auto-flagged** warning-count trend rides along for human review — raw
warning volume isn't severity (NY's 22,000 warnings were almost entirely one benign fallback
message; DE's 459 were real vote-fetch failures), so this script deliberately doesn't try to
score it.

A small tracking file (`output/audit_tracking.json`) remembers what's
already been flagged, so a known, still-unresolved issue shows as "STILL OPEN" rather than
re-alarming as "NEW" every week.

### Daily Scraper Error Digest — per-run failures

Two checks, run for every **currently active** (non-paused) state only — paused states have
no fresh runs to check:

1. **Reads each state's most recent committed `failure_type`/`error_summary`** (written by
   `actions/scrape/scrape.sh`) and surfaces anything that isn't already known-benign. "Benign"
   means `failure_type` is `NONE`, `S1_*`, or `S2_*` (already-classified out-of-session codes)
   **and** every sample warning line matches a confirmed-noise pattern. These two conditions
   are checked independently — a `NONE` failure_type does **not** by itself suppress a
   finding, because a run can exit 0 while a scraper's own `self.warning()` is quietly
   dropping bills (this was the entire motivation for govbot PR #187: MA's `"Server Error on
   {}"` dropped ~210 bills/run for over a month while every run reported success).
2. **A live check for a run that never even produces a `scrape-summary.json`** — confirmed on
   `fl`/`ma-legislation` (`"exceeded the maximum execution time while awaiting a runner for
   24h0m0s"`, then cancelled). This needs one GitHub Actions API call per active state, since
   there's no committed file to read when the job never ran.

**Noise filtering is empirical, not guessed.** The current patterns
(`no session provided, using active sessions`, `Duplicate entry in 'documents'`) came from
pulling real data across a 12-state sample (TX, FL, CA, MA, GA, OK, USA, NY, DE, UT, AZ, GU)
and confirming they were 100% of the noise in USA's and GU's real warning volumes. Add new
patterns to `NOISE_PATTERNS` in the script the same way — after confirming a pattern is
actually noise in a real run, not ahead of time.

**Known limitation:** `failure_type`/`error_summary` are new fields in `warning_history.json`
(added alongside this digest). A state's digest stays quiet until its *next* scrape run
writes them — there's no backfill.

## Where the signal comes from

`actions/scrape/scrape.sh` already computes a `FAILURE_TYPE` (a best-effort regex bucket —
see that file's own comments for the full list) and now also an `ERROR_SUMMARY` (the actual
exception/error text, independent of the bucket guess). Both get written to:

- `scrape-summary.json` — a GitHub Actions artifact, ~90-day retention
- `GITHUB_ENV` — so `actions/scrape/action.yml`'s fail step can append the real error text to
  the `::warning::`/`::error::` annotation (so a human reading one run's log directly also
  sees the truth, not just the bucket)
- `.windycivi/warning_history.json` — **committed**, permanent, one entry per calendar day —
  this is what both audits actually read

The bucket (`FAILURE_TYPE`) stays useful as a coarse, fast filter for dashboards and for the
audits' noise rules. But it's a regex guess over free-text scraper logs across 56+
jurisdictions, and a loose regex *will* occasionally guess wrong (the `H3_RATE_LIMITED`/`HR
429` incident above is the concrete example). The fix wasn't to chase a perfect regex —
that's an unwinnable game against free-text logs — it was to always surface the real error
text **alongside** the bucket, so a wrong guess can never hide the truth again.

## Extending either check

- **New flatline exception** (a state whose session structure legitimately front-loads
  bills): add it to `EXCEPTIONS` in `weekly-scraper-audit.py`, with the empirical evidence
  (a date-concentration scan) in the commit message — don't add one on a guess.
- **New confirmed-noise warning pattern**: add it to `NOISE_PATTERNS` in
  `daily-scraper-error-digest.py`, only after confirming via a real `warning_history.json`
  entry that the pattern is actually benign.
- **A failure type that should alert louder** (like the existing active-block codes in
  `scrape.sh`/`action.yml`): that's a change to `scrape.sh`'s classification order and
  `action.yml`'s `IS_ACTIVE_BLOCK` handling in `actions/scrape/`, not to either script here.

## What this deliberately does not cover

Both checks are scoped to **bill-discovery health** — is a scraper finding new bills, and is
each run's failure signal visible. Neither covers text extraction completeness, field
completeness (sponsors, abstracts), or orphan-bill tracking — those are separate problems
with their own tools and cadence (see `actions/pipeline-manager/docs/staleness-audit-spec.md`
for the related staleness-by-timestamp question, which these two checks now partially
supersede for the bill-discovery case specifically).
