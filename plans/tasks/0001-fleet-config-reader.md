# Task 0001: Fleet config reader + module scaffold

**Branch**: `feature/fleet-config-reader`
**Depends on**: none
**Source**: plans/fleet-monitor-prd.md · **User stories**: 5, 13, 19, 22

## What to build

The first end-to-end slice of `actions/fleet-monitor`: a new self-contained Python module,
following the repo's action conventions, whose CLI reads the pipeline-manager config files and
emits the fleet as jurisdiction records. This module is the only place that knows the config
format or the paused-template convention; everything downstream consumes its records.

Demo: run the CLI against the real config in this repo and get a JSON list of jurisdictions —
state, org, repo name, expected workflows, paused/active — for both the scraper and data-repo
fleets.

## AFK tasks

- [ ] Scaffold `actions/fleet-monitor` per repo conventions: `main.py` with a `click` CLI,
      Pipfile, `action.yml`, README stub
- [ ] Config reader: parse `actions/pipeline-manager/chn-openstates-scrape.yml` and
      `chn-openstates-files.yml` into jurisdiction records (state code, name, org, repo name,
      expected workflows, paused flag)
- [ ] Derive `paused` from the locale's `template` value (`*-paused` = out-of-session); honor
      `disabled_jobs` when listing expected workflows
- [ ] CLI subcommand (e.g. `list-fleet`) printing records as JSON Lines, with a `--config-dir`
      argument so it runs against fixtures or the real config
- [ ] Snapshot tests: fixture configs in, jurisdiction records out — covering active, paused,
      disabled-jobs, and self-hosted-runner locales — via a `render-snapshots.sh` matching the
      pipeline-manager pattern
- [ ] Add `fleet-monitor` to `validate-snapshots.yml`'s module matrix

## Acceptance criteria

- [ ] `pipenv run python main.py list-fleet --config-dir ../pipeline-manager` emits one record per
      locale per fleet, with correct paused flags for currently-paused states
- [ ] A paused-template locale is marked paused; an active one is not; the distinction is locked by
      a snapshot test
- [ ] Snapshot tests pass in CI via `validate-snapshots.yml`
- [ ] Module runs from a fresh clone with no state beyond pipenv install
