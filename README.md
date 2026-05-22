[![Validate Snapshots](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml/badge.svg)](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml)

**Project overview and demo**  
[![Govbot presentation video](https://img.youtube.com/vi/IFnE1oeUIXo/maxresdefault.jpg)](https://youtu.be/IFnE1oeUIXo)

# 🏛️ govbot

- Download the legislation of [50+ states/jurisdictions](https://github.com/govbot-data) in under 1 minute.
- Classify and summarize bills with private/local models — runs on free GitHub Actions.

`govbot` is a CLI for distributed analysis of government data. Git repos function as datasets — the legislation of every US state, DC, the territories, and federal Congress. It composes with [`fastclass`](#classifying-with-fastclass) (the classifier) over a Unix pipe; together they pull, classify, and publish a tagged feed of legislation to RSS, HTML, JSON, DuckDB, or a Bluesky posting bot.

## 🤖 Build a newsbot with Claude Code

The fastest way to stand up a govbot project — a classified, auto-publishing
legislation feed (e.g. a Bluesky bot) — is to let Claude Code drive it.
Open a Claude Code session in an empty directory and paste:

> **Read github.com/chihacknight/govbot/AGENT.md and follow it to set up a govbot project here.**

[`AGENT.md`](AGENT.md) is a self-contained playbook: Claude verifies the
tools, interviews you about the issue you want to track, scaffolds the
`govbot.yml` manifest + a `fastclass` classifier bundle, and walks you through
running and scheduling the bot. No plugin or marketplace install needed.

## Example Projects

- [Transportation Legislation Bluesky Bot](https://bsky.app/profile/govbottransport.bsky.social)
- [Data Center Legislation Bluesky Bot](https://bsky.app/profile/govbotaidatacenter.bsky.social)

## Quick Start

### 1. Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

### 2. Set up your project

```bash
govbot init     # or just `govbot` — the wizard runs when no govbot.yml is present
```

Running `govbot init` (or `govbot` in an empty directory) launches an interactive setup wizard that:
1. Asks which datasets you want — all jurisdictions or a hand-picked subset (browse with `govbot search`).
2. Writes a `govbot.yml` manifest (`datasets` / `transforms` / `publish` / `pipelines`), a `.gitignore`, and a GitHub Actions workflow.

Classification lives in a separate [`fastclass`](#classifying-with-fastclass) bundle — point `transforms.classify.classifier` at it.

### 3. Run the pipeline

```bash
govbot run      # or just `govbot` — runs the pipeline when a govbot.yml is present
```

With a `govbot.yml` in your directory, `govbot run` executes the full pipeline:
1. Pulls/updates the declared dataset repositories.
2. Classifies bills against your fastclass bundle (`source --select docs | fastclass classify - | apply`).
3. Runs every publisher in `govbot.yml: publish:` — RSS / HTML / JSON / DuckDB / Bluesky.

### Other Commands

```bash
govbot search wyoming      # search the dataset registry
govbot add wy il           # add datasets to govbot.yml (validated against the registry)
govbot remove wy           # remove datasets from govbot.yml
govbot ls                  # list the manifest's datasets + what is cached locally
govbot pull all            # clone/update every dataset
govbot pull il ca ny       # clone/update specific datasets
govbot source              # stream dataset records as JSON Lines
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
govbot apply               # persist a fastclass result stream into the dataset
govbot publish             # run every configured publisher (RSS / HTML / JSON / DuckDB / Bluesky)
govbot publish --publisher bluesky --dry-run   # ALWAYS dry-run Bluesky first
govbot run                 # the full pipeline: pull -> classify -> apply -> publish
govbot load                # load bill metadata into DuckDB
govbot delete all          # unlink all locally-linked datasets (the shared cache stays)
govbot update              # update govbot to the latest nightly
govbot --help              # see all commands and options
```

## Classifying with fastclass

govbot does not classify bills itself — it streams them to a separate
[`fastclass`](#) CLI (a token-free, deterministic text classifier) and writes
the result back. The pipe:

```bash
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
```

`govbot run` wires this automatically. The classifier is a **bundle directory**
(`classifier.yml` + `fusion.yml` + `eval/`) owned by fastclass; govbot only
references its path. See [`AGENT.md`](AGENT.md) for the end-to-end newsbot
playbook (make / manage / update) and the [stream protocol](schemas/STREAM_PROTOCOL.md)
for the wire format.

# 🏛️ Govbot Legislation Data Catalogs

govbot pulls data from a registry of git-repo datasets. The bundled default
registry (`actions/govbot/data/registry.json`) ships every US state, DC, the
territories, and federal Congress — see [`actions/govbot/REGISTRY.md`](actions/govbot/REGISTRY.md)
for the format, and the [govbot-data org](https://github.com/govbot-data) for
the dataset repos themselves.

Coverage today:
- Every US state legislature
- US territories (DC, PR, GU, VI, MP)
- US federal (Congress)

Override the registry with `GOVBOT_REGISTRY_URL=<url-or-path>` or a project-local
`.govbot/registry.json`.

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
