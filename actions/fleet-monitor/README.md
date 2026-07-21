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

## Usage

### As a Standalone Script

```bash
cd actions/fleet-monitor
pipenv install
pipenv run python main.py list-fleet --config-dir ../pipeline-manager
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

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
