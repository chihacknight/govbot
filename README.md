[![Validate Snapshots](https://github.com/windy-civi/toolkit/actions/workflows/validate-snapshots.yml/badge.svg)](https://github.com/windy-civi/toolkit/actions/workflows/validate-snapshots.yml)

# 🏛️ govbot

`govbot` enables distributed data anaylsis of government updates via a friendly terminal interface. Git repos function as datasets, including the legislation of all 47 states/jurisdictions.

## 1 Line Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/windy-civi/toolkit/main/actions/govbot/scripts/install-nightly.sh)"
```

```bash
govbot # to see help
govbot init # creates govbot.yml file
govbot clone # to show
govbot clone {{repo}} {{repo}} # to download specific items
govbot delete {{repo}} # to delete specific items
govbot delete all # to delete everything
govbot logs | govbot tag # tag things based on what's inside govbot.yml
govbot load # load bill metadata into DuckDB database
govbot update # updates govbot
```

# 🏛️ Govbot Legislation Effort

- Nearly all state governments
- Federal

WIP: Ideally, these scripts should be accessible via the following ways.

- CLI / Unix pipe friendliness where possible. CLI is the most portable of solutions.
- GitHub Actionable if possible

## Contribute

### Folder Structure

This repo is a monorepo, with `actions` being self contained. `actions` as a name is because it's what Github expects.

### Requirements For Each Action

- Be a runnable as basic scripts in python, bash, rust, or typescript which can run as shell scripts with args.
- Have an `action.yml` file to run as a runner, most likely in GitHub Actions.
- Have a `schemas` folder that uses JSON schema to define types.
  - This allow other actions to import your schema for validation.
- Have `__snapshots__` that contain real file/folder outputs. This serves two purposes: (1) they show expected results and (2) they can be directly used as inputs for downstream snapshot tests.
  - Each action manages its own snapshot rendering through a render_snapshots.sh script.
  - Validation occurs via .github/validate-snapshots.yml for each specific module.
