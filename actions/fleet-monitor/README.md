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

### Budgets

- **GitHub API**: only single-page queries (`per_page` ≤ 3) — 2 per workflow (recent
  runs, latest success) + 1 per repo for the data-path commit. Current fleet: 112 repos × 1 workflow → **336
  requests per sweep**, well inside the default `GITHUB_TOKEN` limit of 1000/hour;
  `render-snapshots.sh` asserts the real-fleet count stays under 400.
- **Series cardinality**: 2 series per repo/workflow + 1 per repo, plus the single global
  `fleet_collector_heartbeat` pair the orchestrator emits per sweep → **~336 series (+2 heartbeat)**
  for the current fleet, against the Grafana Cloud free-tier budget of ~10k active series
  (50 GB logs/mo, 14-day retention — re-verify at signup). 10× fleet growth still fits.

### Credentials (environment variables)

| Variable | Meaning |
| --- | --- |
| `GITHUB_TOKEN` | **required for live polls**: one sweep ≈ 336 requests, the unauthenticated limit is 60/hour (the CLI refuses to start without it) |
| `GRAFANA_PUSH_URL` | Influx write endpoint, `https://influx-…/api/v1/push/influx/write` |
| `GRAFANA_PUSH_USER` / `GRAFANA_PUSH_KEY` | metrics instance ID / access-policy token (`metrics:write`) |
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

# End-to-end proof: poll, push, then query the series back (needs all six
# GRAFANA_* vars; exits 0 with a notice when they're absent):
pipenv run python main.py live-check --config-dir ../pipeline-manager

# The unattended sweep the hourly workflow runs: poll, push metrics + a
# collector heartbeat. Exits nonzero only on an outright collector failure
# (config/poll error, or a failed push) — per-repo poll errors stay green:
pipenv run python main.py run --config-dir ../pipeline-manager
```

`run` is the orchestrator: it wires config reader → poller → shipper and appends
a `fleet_collector_heartbeat` series (`repos`, `errors`) that ships on **every**
sweep. Its exit contract differs from `collect`'s by design — a red workflow run
must mean the *collector* is down, so per-repo poll errors are logged but keep
the run green (a degraded fleet surfaces through the metrics and Grafana alerts),
and only a config/poll error or a failed push exits nonzero. Because the
heartbeat always ships, an all-null sweep still proves the collector ran.

`--config-dir` points at any directory holding fleet config YAMLs and their `templates/`
folder, so the CLI runs against fixtures or the real config. Options can also be set via
`FLEET_MONITOR_*` environment variables (click's `auto_envvar_prefix`, matching sibling
actions), e.g. `FLEET_MONITOR_LIST_FLEET_CONFIG_DIR`.

### Running the hourly workflow

[`.github/workflows/fleet-monitor.yml`](../../.github/workflows/fleet-monitor.yml) runs the
orchestrator (`run`) once an hour against the real `actions/pipeline-manager` config and pushes
metrics + the collector heartbeat to Grafana Cloud. It's read-only on GitHub (the default
`GITHUB_TOKEN` covers all reads), bounded by a 20-minute job timeout, and serialized by a
`fleet-monitor` concurrency group so a manual dispatch never overlaps a scheduled sweep.

To bring it up in a fork against your own Grafana Cloud account, set **one secret** and **two
variables** on the repo (Settings → Secrets and variables → Actions):

| Kind | Name | Value |
| --- | --- | --- |
| **Secret** | `GRAFANA_PUSH_KEY` | Grafana Cloud access-policy token with `metrics:write` |
| Variable | `GRAFANA_PUSH_URL` | Influx write endpoint, `https://influx-…/api/v1/push/influx/write` |
| Variable | `GRAFANA_PUSH_USER` | Metrics instance ID |

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

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
