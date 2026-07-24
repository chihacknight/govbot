# Fleet Monitor

Observability for the govbot fleets. This module is the only place that knows the
pipeline-manager config format or the paused-template convention; everything downstream
consumes its jurisdiction records.

## What It Does

Reads the pipeline-manager fleet configs and emits one JSON Lines record per locale per
fleet. **Discovery convention**: any top-level `*.yml`/`*.yaml` in `--config-dir` with a
`locales` mapping is a fleet, named by the file's stem — today that means
`chn-openstates-scrape.yml` and `chn-openstates-files.yml`; a new fleet config is picked
up without code changes.

The record shape is the module's contract, declared in
[schemas/fleet-record.schema.json](../../schemas/fleet-record.schema.json) and validated on
every snapshot render: `fleet`,
`config` (lineage: the source config file name), `state`, `name`, `org`, `repo`,
`template`, `base_template` (the `-paused` suffix stripped — the locale's durable
identity, which downstream keys per-template facts off), `paused`, `runner`,
`expected_workflows`.
A locale is paused when its `template` ends in `-paused`. `expected_workflows` lists the
template's workflow files as they exist in rendered repos (`.j2` stripped), minus the
locale's `disabled_jobs`. A config that references an unknown template, or a template
with no workflow files on disk, fails loudly with a nonzero exit — never an empty record.

## Metrics: poller + shipper

`collect --metrics-only` turns jurisdiction records into Grafana Cloud metrics in three
steps, each its own module:

- **[fleet_poller.py](fleet_poller.py)** — all GitHub REST knowledge. For every repo:
  the latest *completed* run's conclusion (an in-progress run never masks the last
  finished one) and hours since the last successful run per expected workflow, plus
  hours since the last commit touching the repo's data path (`_data/<locale>/` in
  scraper repos, `country:us/` in data repos). The record shape is locked by
  [schemas/fleet-poller-record.schema.json](../../schemas/fleet-poller-record.schema.json)
  and carries `config`/`polled_at` lineage. Per-repo failures are recorded on the
  output record's `errors` list and skipped — one bad repo never aborts the sweep —
  but `collect` exits 1 when any repo erred, after shipping what it has: a degraded
  sweep must never look like a clean one. An unknown template is a config gap and
  fails the sweep before any polling.
- **[metrics_shipper.py](metrics_shipper.py)** — pure encoder from poller records to the
  Influx line-protocol payload Grafana Cloud ingests. Series produced:
  `fleet_workflow_run_status` (1 = latest run succeeded),
  `fleet_workflow_run_hours_since_success`, and `fleet_repo_data_commit_age_hours`.
  Labels are capped at `state`/`org`/`workflow`/`paused`. (The orchestrator adds one more,
  untagged, series each sweep — `fleet_collector_heartbeat` — via `encode_heartbeat`; see below.)
- **[metrics_push.py](metrics_push.py)** + **[http_util.py](http_util.py)** — POST with
  retry/backoff (429 honors Retry-After — as does a 403 that is really GitHub rate
  limiting — 5xx backs off, other 4xx fails fast; an exhausted quota with no
  Retry-After also fails fast, since its reset is up to an hour out and the next
  scheduled sweep will retry anyway). Repos are polled concurrently, bounded at 8
  workers to stay inside GitHub's secondary-rate-limit etiquette.

## Logs: harvester + Loki shipper + watermark

`collect --logs-only` (and the logs leg of `run`) ships each hourly sweep's *new*
run logs to Grafana Cloud Loki — never the same run twice — in three modules:

- **[log_harvester.py](log_harvester.py)** — all GitHub-logs REST knowledge, the
  logs counterpart to the poller. For each repo it lists recent runs, ships only
  those newer than the per-(repo, workflow) watermark, and for every new *completed*
  run downloads the log archive, unpacks the top-level per-job logs, parses the
  RFC 3339 timestamp GitHub prefixes on every line, drops known-noise lines
  (`##[group]`/`##[endgroup]`, blanks), and applies the **volume policy**: full logs
  for a failed/cancelled/timed-out run (the ones you debug), the last ~100 lines for
  a success (proof it ran, not a transcript). Per-repo failures are recorded and
  skipped — one bad repo never aborts the sweep.
- **[watermark.py](watermark.py)** — the incremental boundary: a JSON map of
  `"<org>/<repo>/<workflow>"` → the last shipped run id, so re-running an unchanged
  window ships nothing. Persisted between hourly sweeps by the Actions cache; a lost
  cache reads as empty and the harvester falls back to a bounded **one-day
  look-back**, recovering the last day rather than re-shipping a repo's whole
  history. The look-back bounds *every* sweep (not just a cold start), and the run
  listing pages just far enough to cover it, so selection never wants a run the
  listing didn't fetch. The watermark advances only across contiguous shipped runs —
  an in-progress run, one whose archive fetch failed, or a label the shipper would
  reject halts advancement so it is retried next sweep, never stepped over.
- **[logs_shipper.py](logs_shipper.py)** + **[logs_push.py](logs_push.py)** — a pure
  encoder from labeled batches to the Loki push payload (reusing http_util's
  retry/backoff POST). Stream labels are capped at `org`/`state`/`workflow`/`outcome`;
  run and job ids are high-cardinality, so they ride in each entry's Loki
  **structured metadata**, never as labels.

### Ingest window (the retired risk)

An hourly collector ships logs from runs that finished up to an hour — or, on a lost
cache, a day — earlier, and Loki rejects samples older than its ingest window. That
is the PRD's first risk to retire, so it is probed, not assumed: `probe-loki` pushes
one line per age (1–24 h old) and reports which the real endpoint accepts.

**Decision**: ship each entry stamped with its **original event time** (so logs are
queryable by when the event happened, and correlate with the metrics), because the
maximum age of any shipped entry is bounded — hourly cadence plus the 24 h look-back
cap it at ~25 h — and Grafana Cloud Loki's default reject-old-samples window is 168 h
(7 days), comfortably beyond that. `probe-loki` confirms this against the actual stack
before launch. **Fallback** (only if a probe ever shows entries < 24 h old rejected):
ship at collection time and carry the original event time in structured metadata
alongside the run id — the harvester already threads event time through every entry,
so the change is localized to the shipper's timestamp choice.

### Budgets

- **GitHub API**: only single-page queries (`per_page` ≤ 3) — 2 per workflow (recent
  runs, latest success) + 1 per repo for the data-path commit. Current fleet: 112 repos × 1 workflow → **336
  requests per sweep**, well inside the default `GITHUB_TOKEN` limit of 1000/hour;
  `render-snapshots.sh` asserts the real-fleet count stays under 400. The logs leg
  adds 1 run-listing request per workflow (paging up to 4 only when a page is full
  and still inside the 24 h window — page 1 suffices on a normal hourly sweep) plus
  1 archive download per *new* run — bounded by how many runs actually finished in
  the hour, typically a handful, since the watermark skips everything already shipped.
- **Series cardinality**: 2 series per repo/workflow + 1 per repo, plus the single global
  `fleet_collector_heartbeat` pair the orchestrator emits per sweep → **~336 series (+2 heartbeat)**
  for the current fleet, against the Grafana Cloud free-tier budget of ~10k active series.
  10× fleet growth still fits.
- **Log volume**: the tail policy is what keeps logs in budget. Worst case — one new
  run per repo per hour (scrapers mostly run less often), ~100-line success tails at
  ~200 B/line ≈ 20 KB/run → 112 runs × 24 h × 30 d ≈ **1.6 GB/month**, plus full logs
  for the failures (say 5%, ~2k lines ≈ 400 KB each) ≈ another ~1.7 GB → **≈ 3 GB/month**,
  well inside the Grafana Cloud free-tier budget of **50 GB/month, 14-day retention**
  (re-verify at signup). Even 10× fleet growth (~33 GB) fits; shipping full success
  logs instead of the tail would not.

### Credentials (environment variables)

| Variable | Meaning |
| --- | --- |
| `GITHUB_TOKEN` | **required for live polls**: one sweep ≈ 336 requests, the unauthenticated limit is 60/hour (the CLI refuses to start without it) |
| `GRAFANA_PUSH_URL` | Influx write endpoint, `https://influx-…/api/v1/push/influx/write` |
| `GRAFANA_PUSH_USER` / `GRAFANA_PUSH_KEY` | metrics instance ID / access-policy token (`metrics:write`) |
| `GRAFANA_LOGS_URL` | Loki push endpoint, `https://logs-…/loki/api/v1/push` (logs leg + `probe-loki`) |
| `GRAFANA_LOGS_USER` / `GRAFANA_LOGS_KEY` | logs instance ID / access-policy token (`logs:write`) |
| `GRAFANA_QUERY_URL` | Prometheus API base, `https://prometheus-…/api/prom` (live-check only) |
| `GRAFANA_QUERY_USER` / `GRAFANA_QUERY_KEY` | Prometheus instance ID / token (`metrics:read`, live-check only) |

## Usage

### As a Standalone Script

```bash
cd actions/fleet-monitor
pipenv install
pipenv run python main.py list-fleet --config-dir ../pipeline-manager

# Poll the real fleet and print the metric payload without pushing:
GITHUB_TOKEN=$(gh auth token) pipenv run python main.py collect --metrics-only \
  --config-dir ../pipeline-manager --dry-run

# Same, but push to Grafana Cloud (needs GRAFANA_PUSH_* env vars):
pipenv run python main.py collect --metrics-only --config-dir ../pipeline-manager

# Harvest new run logs and print the Loki payload without pushing (idempotent:
# --watermark-file tracks what has shipped, so a re-run of the same window is empty):
GITHUB_TOKEN=$(gh auth token) pipenv run python main.py collect --logs-only \
  --config-dir ../pipeline-manager --watermark-file .watermarks/logs.json --dry-run

# Retire the Loki ingest-window risk before launch: push one line per age
# (1–24 h old) and see which the endpoint accepts (needs GRAFANA_LOGS_* vars):
pipenv run python main.py probe-loki

# End-to-end proof: poll, push, then query the series back (needs all six
# GRAFANA_* vars; exits 0 with a notice when they're absent):
pipenv run python main.py live-check --config-dir ../pipeline-manager

# The unattended sweep the hourly workflow runs: poll, push metrics + a collector
# heartbeat, then harvest + ship new run logs. Exits nonzero only on an outright
# collector failure (config/poll error, or a failed push) — per-repo errors stay green:
pipenv run python main.py run --config-dir ../pipeline-manager \
  --watermark-file .watermarks/logs.json
```

`run` is the orchestrator: it wires config reader → poller → shipper, appends
a `fleet_collector_heartbeat` series (`repos`, `errors`) that ships on **every**
sweep, then harvests each repo's new run logs and ships them to Loki. Its exit
contract differs from `collect`'s by design — a red workflow run
must mean the *collector* is down, so per-repo poll and log-harvest errors are
logged but keep the run green (a degraded fleet surfaces through the telemetry and
Grafana alerts), and only a config/poll error or a failed push exits nonzero. Because the
heartbeat always ships, an all-null sweep still proves the collector ran. The logs
leg is idempotent through the `--watermark-file`: without it, every run re-ships the
last day of logs, so production passes a file backed by a persistent store.

`--config-dir` points at any directory holding fleet config YAMLs and their `templates/`
folder, so the CLI runs against fixtures or the real config. Options can also be set via
`FLEET_MONITOR_*` environment variables (click's `auto_envvar_prefix`, matching sibling
actions), e.g. `FLEET_MONITOR_LIST_FLEET_CONFIG_DIR`.

### Running the hourly workflow

[`.github/workflows/fleet-monitor.yml`](../../.github/workflows/fleet-monitor.yml) runs the
orchestrator (`run`) once an hour against the real `actions/pipeline-manager` config and pushes
metrics + the collector heartbeat to Grafana Cloud and new run logs to Loki. It's read-only on
GitHub (the default `GITHUB_TOKEN` covers all reads), bounded by a 20-minute job timeout, and
serialized by a `fleet-monitor` concurrency group so a manual dispatch never overlaps a
scheduled sweep. The log watermark is carried between sweeps by the Actions cache (restore by
prefix before the sweep, save a fresh `run_id` key after), so the logs leg stays incremental; a
cold cache is safe — the harvester falls back to a bounded 24 h look-back.

To bring it up in a fork against your own Grafana Cloud account, set **two secrets** and **four
variables** on the repo (Settings → Secrets and variables → Actions):

| Kind | Name | Value |
| --- | --- | --- |
| **Secret** | `GRAFANA_PUSH_KEY` | Grafana Cloud access-policy token with `metrics:write` |
| **Secret** | `GRAFANA_LOGS_KEY` | Grafana Cloud access-policy token with `logs:write` |
| Variable | `GRAFANA_PUSH_URL` | Influx write endpoint, `https://influx-…/api/v1/push/influx/write` |
| Variable | `GRAFANA_PUSH_USER` | Metrics instance ID |
| Variable | `GRAFANA_LOGS_URL` | Loki push endpoint, `https://logs-…/loki/api/v1/push` |
| Variable | `GRAFANA_LOGS_USER` | Logs instance ID |

The endpoint and instance ID aren't secret, so they're repo **variables** (`vars`), keeping the
Grafana write key the single secret. Then enable Actions on the fork (the Actions tab, if a fresh
fork has workflows disabled) and trigger a first sweep by hand — **Actions → Fleet Monitor → Run
workflow** (`workflow_dispatch`) — to confirm it goes green and the metrics land before the hourly
schedule takes over. A forced failure (e.g. a bad `GRAFANA_PUSH_KEY`) exits nonzero and the run
shows red, which is what the `heartbeat absent` alert keys off.

### As a GitHub Action

See [action.yml](action.yml). Optional `config-dir` input, default `actions/pipeline-manager`.
The composite Action exposes `list-fleet` for consumers embedding fleet discovery in their own
workflows; the hourly monitor above invokes the `run` orchestrator directly rather than through
the Action.

## Testing

Snapshot tests: fixture configs in [fixtures/](fixtures/) go in, jurisdiction records in
[__snapshots__/](__snapshots__/) come out. Each subdirectory of
[fixtures-invalid/](fixtures-invalid/) is a broken config whose error message is
snapshotted; the render fails if any of them exits 0. The render also validates every
record against the schema and smoke-tests the real `../pipeline-manager` config.

The metrics payload is snapshot-tested the same way: fixed poller records in
[fixtures/poller-records.jsonl](fixtures/poller-records.jsonl) (success, failure, a
never-completed workflow, a workflow name needing tag escaping, an unreachable repo)
render byte-identically to
[__snapshots__/metrics-payload.txt](__snapshots__/metrics-payload.txt) via
`collect --dry-run`, timestamped from the fixture's pinned `polled_at`. The render also
validates every poller record (fixture and fake-fetcher output) against
`fleet-poller-record.schema.json`, asserts the poller's never-fatal contract and the
fatal unknown-base-template check offline (plus: active runs never mask the last
completed conclusion, flaked `status=success` pages fall back to the unfiltered
listing, workflow names are percent-encoded, an empty repo's 409 is null not error),
asserts `collect`'s exit contract from all sides (1 on any poll error, 0 on a clean
sweep with an identical payload, loud failure on an empty payload in push and
dry-run modes alike, `--timestamp` override), asserts the `run` orchestrator's
distinct contract (a heartbeat-encoder unit check and a shipper-resilience unit
check — an un-encodable record is skipped while the rest of the sweep still ships —
plus: a partial-fail sweep exits 0 shipping metrics + heartbeat, a clean sweep
carries a zero-error heartbeat, an all-errored sweep still exits 0 with the
heartbeat alone, a sweep with one un-encodable repo still exits 0 and ships the
good repos' metrics + heartbeat, and an outright push failure — missing credentials
or a rejected key/HTTP 401 — exits nonzero so the workflow shows red), locks
`live-check`'s expected-series
accounting (its query-back proof requires every series this payload shipped, per
metric, and skips metrics the payload legitimately omits), locks the HTTP retry
policy (4xx fail-fast, rate-limited 403 retries like
429, exhausted-quota fail-fast, integer `Retry-After` honored, HTTP-date form falls
back, 5xx backoff, no final-attempt sleep) and the push wire format (URL, verb,
Basic auth, Content-Type, body) with a fake `urlopen` and injected sleep, checks the
real-fleet API budget and that every real-fleet base template has a `DATA_PATHS`
entry, and locks `live-check`'s credential-free skip path. The real push-and-query
proof is opt-in — `FLEET_MONITOR_LIVE_CHECK=1 ./render-snapshots.sh` on a
credentialed machine — so a bare render stays offline, deterministic, and
side-effect-free. The poller's happy path is deliberately untested beyond that — it
is a pass-through against a live API.

The logs leg is snapshot-tested the same way. Committed fixture archives under
[fixtures/log-runs/](fixtures/log-runs/) (a failed run and a successful one) render
byte-identically to [__snapshots__/logs-payload.json](__snapshots__/logs-payload.json)
via `collect --logs-only --dry-run`, pinned by `--timestamp`. Around that, offline
unit checks lock: the Loki shipper (labeled batches → deterministic Loki JSON, labels
capped at org/state/workflow/outcome, run id in structured metadata not labels, an
un-encodable batch skipped); the watermark store (missing/empty file reads as `{}`,
writes round-trip); the harvester (archive unpack ignoring step folders, the RFC 3339
line-timestamp parse including a fractional part, `##[group]`/`##[endgroup]` noise
dropped, the volume policy — full logs for a failure, a 100-line tail for a success —
the per-repo/workflow watermark advancing only across contiguous shipped runs so an
in-progress run or a failed archive fetch is retried not skipped, the cold-start 24 h
look-back, and per-repo error isolation); the Loki push wire format (URL, POST, Basic
auth, `application/json`, missing-env guard) with a fake `urlopen`; the CLI's
end-to-end idempotency (a re-run of the same window ships nothing) and recovery (a
deleted watermark ships the recent window, not the full history) driven in-process
with a fake push; that `run` wires the logs leg only when a log source is present; and
`probe-loki`'s credential-free skip path. The real ingest-window probe runs only with
`GRAFANA_LOGS_*` set.

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
