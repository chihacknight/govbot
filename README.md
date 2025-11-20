[![Tests](https://github.com/windy-civi/toolkit/actions/workflows/test-runner.yml/badge.svg)](https://github.com/windy-civi/toolkit/actions/workflows/test-runner.yml)

# 🏛️ Windy Civi Toolkit - Tools To Watch & Analyze Governemnt Actions

- Nearly all state governments
- Federal

WIP: Ideally, these scripts should be accessible via the following ways.

- CLI / Unix pipe friendliness where possible. CLI is the most portable of solutions.
- GitHub Actionable if possible

## Folder Structure

This repo is a monorepo, with `actions` being self contained. `actions` as a name is because it's what Github expects.

## Contribute - Each Action Must

- Be a runnable as basic scripts in python, bash, rust, or typescript which can run as shell scripts with args.
- Have an `action.yml` file to run as a runner, most likely in GitHub Actions.
- Have snapshots of real outputs. This allows people to see what expected outputs are, and for downstream actions to directly use your snapshot output for input. Each action is responsible for how to render those snapshots (See `render_snapshots.sh` in each action). 
- Have a `schemas` folder that uses JSON schema to define types. This allow other actions to import your schema for validation.
