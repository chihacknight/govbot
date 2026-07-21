# Task 0002: Fleet poller + metrics shipper

**Branch**: `feature/fleet-poller-metrics`
**Depends on**: 0001
**Source**: plans/fleet-monitor-prd.md · **User stories**: 1, 13, 17, 21, 25, 26

## What to build

The metrics tracer bullet: take the jurisdiction records from the config reader, poll the GitHub
API for each repo's latest run status per expected workflow and hours since the last data-path
commit, encode those into Grafana Cloud metric-push payloads (every series carrying the paused
label), and push them over an HTTP helper with retry. A `--dry-run` flag prints the encoded
payload instead of pushing.

Demo: one local CLI invocation against the real orgs' public data lands fleet metrics queryable
in Grafana Explore.

## AFK tasks

- [ ] Fleet poller: given jurisdiction records and a GitHub API client (workflow/default token,
      public reads only), return plain records of latest run conclusion + hours since last
      successful run per expected workflow, and hours since last commit touching data paths per
      repo (raw scrape output in scraper repos, formatted tree in data repos)
- [ ] Per-repo failures are recorded on the output record and skipped, never fatal to the run
- [ ] Keep API usage conservative: one-page/latest-run queries only; document the per-run request
      count and assert it stays in the low hundreds for the current fleet
- [ ] Metrics shipper: encoder from poller records to the Grafana Cloud metric-push payload, with
      labels limited to state/org/workflow/paused; series-count estimate documented against the
      10k free-tier budget
- [ ] Shared HTTP helper with retry/backoff used by the push
- [ ] CLI subcommand (e.g. `collect --metrics-only`) with `--dry-run`; credentials via env vars
- [ ] Snapshot tests: fixed poller records in, exact metric payloads out
- [ ] Automated live check: after a real push, query the Grafana metrics API for the shipped
      series and assert presence (skipped when credentials are absent)

## Human-in-the-loop tasks

- [ ] [verify] Grafana Cloud free-tier account exists and write/query keys are provided as env
      vars — account signup and key issuance require human credentials; also re-verify the
      free-tier limits (10k series / 50 GB / 14-day) noted in the PRD

## Acceptance criteria

- [ ] A local run against the real orgs emits one status series and one freshness series per
      repo/workflow, each with a correct paused label
- [ ] A deliberately unreachable repo in a fixture fleet yields an error record and does not
      abort collection
- [ ] Shipper payload snapshots pass in CI; `--dry-run` produces byte-identical payloads to the
      snapshots for fixture input
- [ ] Metrics are queryable in Grafana Explore after a push
