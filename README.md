[![Validate Snapshots](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml/badge.svg)](https://github.com/chihacknight/govbot/actions/workflows/validate-snapshots.yml)

**Project overview and demo**  
[![Govbot presentation video](https://img.youtube.com/vi/IFnE1oeUIXo/maxresdefault.jpg)](https://youtu.be/IFnE1oeUIXo)

# 🏛️ govbot

**govbot is a 4-tool stack for civic-data publishing** — pull real legislative
data, filter by what you care about, publish with receipts, all from a
coding-agent-native dev experience. The whole stack is designed to run on
free GitHub Actions and a local laptop with local models, so a small
volunteer crew can stand up a credible bot and **keep it running for
~nothing**.

The first user is **climate-activist**, a userland repo that turns the
country's legislative activity into a Bluesky feed worth reading at
nearly-free cost. Everything in this README is in service of that bar: if
climate-activist cannot ship a "worth reading, nearly free to run" post,
govbot has not earned the framing.

### The 4 tools

1. **Select real gov data** — pull the legislative activity of all 50
   states, DC, the territories, and federal Congress from a registry of git
   repos (`govbot pull`, scrapers thanks to [OpenStates](https://openstates.org)).
   Repos are content-addressed; a second pull (here or in another project)
   is a cache hit, not a re-clone. `govbot doctor` validates the cache.
   *Today:* bill text + subjects ship via `govbot source --select docs`.
   *Honest gap:* sponsors and voting records exist in the underlying
   metadata but are not yet in the `--select docs` projection; the "under
   1 minute" headline is the warm-cache case (a cold clone of all 55
   datasets is closer to 3 minutes).

2. **Filter / transform** (map / filter / reduce — *find the relevant
   bills*) — any transform over the stream. The shipped transform today is
   **fastclass tagging**: a low-token, high-quality text classifier that
   tags bills against an issue taxonomy the user owns, then filters to
   what crosses a confidence threshold. *Honest gap:* the planned
   **`summarize` transform** — a local-LLM digest of 1–n grouped bills
   that emits the summary alongside its data-source trace and model
   identity — is not yet built. Userland holds a `summarizer/prompt.md`
   stub; the code does not exist.

3. **Publish with receipts** — many surfaces (RSS, HTML, JSON, DuckDB,
   Bluesky today; X planned). The defining idea: every AI-generated
   digest links back to **deterministic provenance** — the model used,
   the source data, the fastclass reasoning chain, and the recipe to
   regenerate it — published as a GitHub Pages "receipt" page next to the
   short Bluesky post. *Honest gap:* the AI digest publisher and the
   receipt artifact are not yet built. Today's publishers carry
   classification evidence chains internally but do not yet package them
   into a public, auditable receipt page.

4. **Coding-agent-native dev experience** — `AGENT.md` is a self-contained
   playbook a fresh Claude Code session can follow to **make, manage, and
   update** a govbot project. The fastclass plugin
   (`/fastclass:from-intent`, `/fastclass:improve`, `/fastclass:ratify`,
   `/fastclass:install-model`) handles the classifier loop end-to-end.
   `govbot doctor` validates an installation. The "build your own
   high-quality, low-cost govbot" path is the one tool that is already
   working today.

### Roadmap (honest gap map)

Things named in the vision that **do not exist yet**, in priority order:

- **Sponsors + voting records in `--select docs`.** The underlying scrapers
  capture them; the source projection does not yet expose them to
  classifiers and digesters. Closes a known recall gap on
  sponsor-pattern signals.
- **The `summarize` transform.** A local-LLM digest of grouped bills that
  emits the summary plus a structured trace (model id, source bill ids,
  prompt revision) so the digest is reproducible.
- **Receipts.** A GitHub Pages artifact published alongside every AI
  digest post: human-readable on top, full deterministic provenance
  (source bills, model, fastclass scores + reasoning, regen command)
  underneath. The short post links to the receipt; the receipt is the
  source of trust.
- **X publisher.** Same idempotent posting pattern as the Bluesky
  publisher.
- **The "under 1 minute" cold-pull headline.** Today's cold pull of all 55
  datasets is ~3 min. Caching and partial-clone improvements get it
  closer to the headline.

These are tracked as gaps so the rest of the document can be specific
about what *does* work today.

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
govbot run --dry-run   # render-only: every publisher previews its output
govbot run             # or just `govbot` — runs the pipeline when a govbot.yml is present
```

With a `govbot.yml` in your directory, `govbot run` executes the full pipeline:
1. Pulls/updates the declared dataset repositories.
2. Classifies bills against your fastclass bundle (`source --select docs | fastclass classify - | apply`).
3. Runs every publisher in `govbot.yml: publish:` — RSS / HTML / JSON / DuckDB / Bluesky.

`govbot run --dry-run` propagates `--dry-run` to every publisher — the
`bluesky` publisher renders posts to stderr/stdout and touches no network or
ledger. Without `--dry-run`, a `bluesky` publisher whose `BLUESKY_HANDLE` /
`BLUESKY_APP_PASSWORD` env vars are not set is **skipped with a `WARN`**
rather than failing the pipeline — first-time runs without creds still emit
the RSS / HTML feeds.

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
govbot apply               # persist a fastclass result stream under <project>/tags/
govbot publish             # run every configured publisher (RSS / HTML / JSON / DuckDB / Bluesky)
govbot publish --publisher bluesky --dry-run   # ALWAYS dry-run Bluesky first
govbot run --dry-run       # full pipeline, every publisher dry-run (recommended first run)
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

### Project layout

A govbot project has three tool-managed directories, each with a distinct
role; all are git-ignored by default:

| Dir | Owner | Contents |
|---|---|---|
| `.govbot/` | the tool's **cache** (`node_modules/` equivalent) | cloned datasets, ledgers, sync state. Fully regenerable. Never edit. |
| `tags/` | `govbot apply` (**classification output**) | `tags/<dataset>/country:.../sessions/<id>/<tag>.tag.json` |
| `dist/` (or `docs/`) | `govbot publish` (**publisher output**) | RSS / HTML / JSON feeds |

Remove `tags/` from `.gitignore` to commit classification provenance.

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
