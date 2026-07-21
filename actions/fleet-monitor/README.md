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
`template`, `paused`, `runner`, `expected_workflows`.
A locale is paused when its `template` ends in `-paused`. `expected_workflows` lists the
template's workflow files as they exist in rendered repos (`.j2` stripped), minus the
locale's `disabled_jobs`. A config that references an unknown template, or a template
with no workflow files on disk, fails loudly with a nonzero exit — never an empty record.

## Metrics: poller + shipper

`collect --metrics-only` turns jurisdiction records into Grafana Cloud metrics in three
steps, each its own module:

- **[fleet_poller.py](fleet_poller.py)** — all GitHub REST knowledge. For every repo:
  latest run conclusion and hours since the last successful run per expected workflow,
  plus hours since the last commit touching the repo's data path (`_data/<locale>/` in
  scraper repos, `country:us/` in data repos). Per-repo failures are recorded on the
  output record's `errors` list and skipped — one bad repo never aborts the sweep.
- **[metrics_shipper.py](metrics_shipper.py)** — pure encoder from poller records to the
  Influx line-protocol payload Grafana Cloud ingests. Series produced:
  `fleet_workflow_run_status` (1 = latest run succeeded),
  `fleet_workflow_run_hours_since_success`, and `fleet_repo_data_commit_age_hours`.
  Labels are capped at `state`/`org`/`workflow`/`paused`.
- **[metrics_push.py](metrics_push.py)** + **[http_util.py](http_util.py)** — POST with
  retry/backoff (429 honors Retry-After, 5xx backs off, other 4xx fails fast).

### Budgets

- **GitHub API**: only `per_page=1` queries — 2 per workflow (latest run, latest success)
  + 1 per repo for the data-path commit. Current fleet: 112 repos × 1 workflow → **336
  requests per sweep**, well inside the default `GITHUB_TOKEN` limit of 1000/hour;
  `render-snapshots.sh` asserts the real-fleet count stays under 400.
- **Series cardinality**: 2 series per repo/workflow + 1 per repo → **~336 series** for
  the current fleet, against the Grafana Cloud free-tier budget of ~10k active series
  (50 GB logs/mo, 14-day retention — re-verify at signup). 10× fleet growth still fits.

### Credentials (environment variables)

| Variable | Meaning |
| --- | --- |
| `GITHUB_TOKEN` | optional for the poller (public reads); raises the rate limit |
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
```

`--config-dir` points at any directory holding fleet config YAMLs and their `templates/`
folder, so the CLI runs against fixtures or the real config. Options can also be set via
`FLEET_MONITOR_*` environment variables (click's `auto_envvar_prefix`, matching sibling
actions), e.g. `FLEET_MONITOR_LIST_FLEET_CONFIG_DIR`.

### As a GitHub Action

See [action.yml](action.yml). Optional `config-dir` input, default `actions/pipeline-manager`.

## Testing

Snapshot tests: fixture configs in [fixtures/](fixtures/) go in, jurisdiction records in
[__snapshots__/](__snapshots__/) come out. Each subdirectory of
[fixtures-invalid/](fixtures-invalid/) is a broken config whose error message is
snapshotted; the render fails if any of them exits 0. The render also validates every
record against the schema and smoke-tests the real `../pipeline-manager` config.

The metrics payload is snapshot-tested the same way: fixed poller records in
[fixtures/poller-records.jsonl](fixtures/poller-records.jsonl) (success, failure, a
still-running workflow, an unreachable repo) render byte-identically to
[__snapshots__/metrics-payload.txt](__snapshots__/metrics-payload.txt) via
`collect --dry-run` with a pinned `--timestamp`. The render also asserts the poller's
never-fatal contract offline (fake fetcher, one repo down), the real-fleet API budget,
and that `live-check` self-skips without credentials. The poller's happy path is
deliberately untested beyond that — it is a pass-through against a live API.

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
