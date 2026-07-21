# Fleet Monitor

Observability for the govbot fleets. This module is the only place that knows the
pipeline-manager config format or the paused-template convention; everything downstream
consumes its jurisdiction records.

## What It Does

Reads the pipeline-manager config files (`chn-openstates-scrape.yml`,
`chn-openstates-files.yml`) and emits one JSON Lines record per locale per fleet:
state code, name, org, repo name, template, paused flag, runner, and the workflows the
locale's template is expected to run (honoring `disabled_jobs`). A locale is paused when
its `template` ends in `-paused`.

## Usage

### As a Standalone Script

```bash
cd actions/fleet-monitor
pipenv install
pipenv run python main.py list-fleet --config-dir ../pipeline-manager
```

`--config-dir` points at any directory holding fleet config YAMLs and their `templates/`
folder, so the CLI runs against fixtures or the real config.

### As a GitHub Action

See [action.yml](action.yml). Optional `config-dir` input, default `actions/pipeline-manager`.

## Testing

Snapshot tests: fixture configs in [fixtures/](fixtures/) go in, jurisdiction records in
[__snapshots__/](__snapshots__/) come out.

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
