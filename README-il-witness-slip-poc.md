# IL Urbanist Witness Slip Notifier — Branch Notes

> **Branch:** `il-witness-slip-poc`  
> **Based on:** [`chihacknight/govbot`](https://github.com/chihacknight/govbot) `main`  
> **Purpose:** Automatically notify urbanist activists when Illinois bills they care about reach committee hearings where witness slips can be filed.

This document supplements the [main govbot README](./README.md). It explains what this branch adds, how it differs from the standard govbot pipeline, and what would be needed to merge it upstream.

---

## What This Branch Does

When an Illinois bill tagged as relevant to urbanist causes (Housing, Biking, Safe Streets, Transit, Transportation) is scheduled for a committee hearing where witness slips are available, this tool:

1. Pulls fresh IL legislation data from [`govbot-openstates-scrapers/il-legislation`](https://github.com/govbot-openstates-scrapers/il-legislation) daily
2. Scans all 8,600+ bills for urbanist keyword matches using topic definitions in `govbot.yml`
3. Builds a digest email grouped by category, with direct ILGA BillStatus links for each bill
4. Sends the digest to configured recipients via SMTP

The goal is to give activist organizers a single, ready-to-forward email with everything they need to mobilize people to file witness slips — without having to manually monitor the ILGA website.

### What Are Witness Slips?

In Illinois, anyone can file a "witness slip" to register support or opposition for a bill before a committee hearing — no travel to Springfield required. Organizations like [Strong Towns Chicago](https://www.strongtownschicago.org/witness-slips) regularly mobilize supporters to file slips for urbanist bills. This tool automates the discovery and aggregation step.

---

## Files Added or Changed

| File | What changed |
|---|---|
| `.github/workflows/witness-slip-notifications.yml` | New workflow: clones IL data daily, runs notifier, sends digest email |
| `scripts/witness_slip_notifier.py` | New script: parses IL bill data, tags by urbanist topic, builds email digest |
| `govbot.yml` | Updated with urbanist tag definitions: Housing, Transit, Biking, Safe Streets, Transportation |
| `README-il-witness-slip-poc.md` | This file |

---

## How It Differs from the Standard govbot Pipeline

The standard govbot workflow is:
```
govbot clone → govbot logs | govbot tag → govbot build → RSS feed
```

This branch **uses `govbot clone` (via direct `git clone`) but skips `govbot logs | govbot tag | govbot build`**, instead running the notifier's own parser directly against the cloned data.

### Why the Standard Pipeline Doesn't Work for IL

govbot's pipeline is built around a `logs/` subdirectory pattern: each bill action is expected to be stored as a separate JSON file at `bills/<ID>/logs/<timestamp>_<action>.json`. The `govbot logs` command walks these subdirectory files to emit a stream of legislative events.

In practice, **Illinois bills in the OpenStates dataset do not follow this pattern for standard HB/SB legislation.** Only `AM`-type (amendment/appointment) bills have a `logs/` subdir. Real House and Senate bills store their entire legislative history — all actions, sponsorships, subjects, committee assignments — inside a single `metadata.json` file, with no `logs/` directory at all.

The result: `govbot logs` finds roughly **12 items** out of **8,648 bills** in the IL dataset. All 12 are appointment confirmations (`AM103...`), not legislation.

### The Intended Fix (Upstream)

This is a structural mismatch between how OpenStates formats IL data and what govbot's pipeline currently expects. The right long-term fix is a **PR to govbot core** to make `govbot logs` also walk `metadata.json` action arrays when no `logs/` subdir is present. This would benefit all states that follow the same OpenStates data pattern, not just Illinois.

Until that PR exists, this branch reads `metadata.json` directly via the notifier's `--data-dir` mode — same underlying data source, one layer down. The govbot infrastructure (the scrapers repo, the daily data updates, the `govbot.yml` config format) is still central to how this works.

---

## GitHub Actions Workflow

**File:** `.github/workflows/witness-slip-notifications.yml`

### Triggers

| Trigger | When |
|---|---|
| `schedule` | Weekdays at 9am CT (runs on default branch only — must merge to main) |
| `workflow_dispatch` | Manual "Run workflow" button in the Actions tab |
| `push` to this branch | Temporary, for testing — remove before merging to main |
| `repository_dispatch: il-data-updated` | Can be triggered by the upstream scraper repo when new IL data lands |

### Steps

1. **Clone or update IL legislation repo** — `git clone --depth=1` on first run, `git pull` on cached runs. Cache key includes today's date so data refreshes once per calendar day.
2. **Inspect IL legislation repo** *(diagnostic, remove after confirming)* — prints bill count and logs subdir count to verify data shape.
3. **Set data dir path** — resolves the path to `country:us/state:il/sessions/104th/bills/` inside the cloned repo.
4. **Generate witness slip notifications** — runs `witness_slip_notifier.py --data-dir` to scan bills, apply tags, build digest.
5. **Send email notifications** — uses `dawidd6/action-send-mail` if `MAIL_SERVER` secret is set.
6. **Post summary** — writes a bill count + list to the GitHub Actions job summary tab.
7. **Upload artifacts** — saves `witness_slip_notifications.json`, `notifications_output.txt`, and `notifications_output.html` for 30 days.

### Required Secrets

| Secret | Purpose |
|---|---|
| `MAIL_SERVER` | SMTP host (e.g. `smtp.gmail.com`) |
| `MAIL_PORT` | SMTP port (e.g. `587`) |
| `MAIL_USERNAME` | SMTP login |
| `MAIL_PASSWORD` | SMTP password or app password |
| `MAIL_FROM` | From address |
| `RECIPIENTS_ALL` | Comma-separated list — always receives the full digest |
| `RECIPIENTS_HOUSING` | Housing-topic recipients (optional) |
| `RECIPIENTS_BIKING` | Biking-topic recipients (optional) |
| `RECIPIENTS_TRANSIT` | Transit-topic recipients (optional) |
| `RECIPIENTS_SAFE_STREETS` | Safe Streets recipients (optional) |
| `RECIPIENTS_TRANSPORTATION` | Transportation recipients (optional) |
| `WITNESS_SLIP_USER_NAME` | Filer name for pre-filled slip forms (optional) |
| `WITNESS_SLIP_USER_EMAIL` | Filer email for pre-filled slip forms (optional) |
| `WITNESS_SLIP_ORG` | Filer organization for pre-filled slip forms (optional) |

---

## The Notifier Script

**File:** `scripts/witness_slip_notifier.py`

### Input Modes

| Flag | What it does |
|---|---|
| `--data-dir <path>` | Reads `metadata.json` for every bill under `<path>`, applies keyword matching from internal topic lists, builds digest. **Used in CI.** |
| `--feed <path>` | Reads the RSS feed produced by `govbot build`. Intended for when the upstream `govbot logs` pipeline is fixed. |
| `--sample` | Downloads a small sample from GitHub for local testing without cloning the full repo. |

### Topic Matching

Bills are matched against urbanist topic keywords from `govbot.yml`:

- **Housing** — zoning, ADUs, missing middle, parking reform, adaptive reuse, YIGBY, tenant protections, homelessness
- **Transit** — CTA, Metra, Pace, RTA, BRT, transit signal priority, fare policy
- **Biking** — bicycle, bike lane, Idaho stop, e-bike, bikeshare, micromobility
- **Safe Streets** — pedestrian safety, Vision Zero, speed cameras, traffic calming, crosswalk, DUI
- **Transportation** — IDOT, road diet, complete streets, infrastructure (broader catch-all)

### Strong Towns Chicago Tracked Bills

The script includes a hardcoded list of 21 bills from [Strong Towns Chicago's witness slip page](https://www.strongtownschicago.org/witness-slips) as a fallback. These appear in every digest regardless of keyword matching — useful when OpenStates data is stale or a bill's title doesn't contain the expected keywords. Each entry includes the bill number, category, plain-English description, and stance (Proponent/Opponent).

This list should be reviewed and updated at the start of each legislative session, or moved to a `tracked_bills.yml` config file for easier maintenance.

### Witness Slip URLs

The script constructs ILGA BillStatus URLs in the format:
```
https://www.ilga.gov/legislation/BillStatus.asp?DocTypeID=HB&DocNum=2934&GAID=18&SessionID=114
```
with a `#tab=witnessSlips` anchor appended. The Witness Slips tab becomes active when a committee hearing is scheduled — the link is correct at all times and will deeplink to the right tab once a hearing is posted.

---

## What's Still Missing / Next Steps

### Before this is production-ready

- [ ] **Set repo secrets** — no emails will be sent without `MAIL_SERVER` and at least one `RECIPIENTS_*` secret configured
- [ ] **Merge to main** — `schedule:` cron triggers only fire on the default branch; manual dispatch works on this branch for testing
- [ ] **Remove diagnostic step** — the "Inspect IL legislation repo" step in the workflow is for debugging and should be removed once confirmed working
- [ ] **Remove push trigger** — the `push: branches: [il-witness-slip-poc]` trigger is temporary for testing

### Improvements for future sessions

- [ ] **Hearing date detection** — OpenStates includes committee hearing events; filter to only bills with hearings in the next N days to reduce digest noise
- [ ] **Move STC tracked bills to config** — `tracked_bills.yml` would let organizers update the list without touching Python
- [ ] **Port `govbot.yml` thresholds to `--data-dir` mode** — the keyword thresholds (0.72–0.78) in `govbot.yml` are not applied in `--data-dir` mode; adding them would reduce false positives
- [ ] **Open upstream PR to govbot** — make `govbot logs` walk `metadata.json` action arrays when no `logs/` subdir exists, so this branch can use the standard pipeline
- [ ] **Remove STC hardcoded list** — once govbot's IL coverage is working end-to-end, the fallback list can be retired or made optional
