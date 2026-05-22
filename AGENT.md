# AGENT.md — build a government-news bot with govbot

You are a Claude Code session helping a user stand up, operate, or evolve a
**govbot newsbot** — a project that pulls government legislation, classifies
the bills relevant to an issue the user cares about, and publishes the matches
(today, to a Bluesky account).

This file is the **end-user playbook**. A fresh session loads it by URL:

> Read github.com/chihacknight/govbot/AGENT.md and follow it to set up a
> govbot project here.

There is no plugin, no marketplace, no slash command to install for govbot
itself — this document *is* the bootstrap. (You will, near the end, add the
**fastclass** plugin to the new project so its classifier can be tuned.)

> This is NOT `CLAUDE.md`. `CLAUDE.md` in the govbot repo is a contributor
> guide for engineers working *on* govbot. `AGENT.md` (this file) is for
> *end users* building a bot *with* govbot. Do not conflate them.

govbot is **issue-agnostic**. Climate legislation is the first use case, not
the only one — transportation, housing, AI/data-center policy, education, and
any other topic work the same way. Interview the user for their issue; never
assume climate.

---

## The three jobs

A user comes to you for one of three things. Identify which, then jump to that
section.

| Job | The user says… | Section |
|---|---|---|
| **make** | "set up a govbot project / newsbot here" | [§1](#1-make--scaffold-a-new-newsbot) |
| **manage** | "set up / run the Bluesky bot", "schedule it" | [§2](#2-manage--operate-the-bluesky-bot) |
| **update** | "add a dataset", "the classifier misses bills" | [§3](#3-update--evolve-an-existing-project) |

---

## The model — read this before doing anything

govbot is a **CLI** plus two companion concepts. Keep them straight:

- **`govbot`** — the gov-data tool. Pulls datasets (git repos of legislation),
  runs transforms over them, and runs publishers. Its config is `govbot.yml`,
  a **manifest** (`datasets` / `transforms` / `publish` / `pipelines`).
- **`fastclass`** — a separate text-classifier CLI. govbot streams bills into
  it; it scores each against a **classifier bundle** (a directory:
  `classifier.yml` + `fusion.yml` + `eval/`). govbot only passes the bundle's
  *path* — it never reads the taxonomy itself.
- **The userland project** (what you scaffold) — a directory holding
  `govbot.yml`, the `classifier/` bundle, and a few support files. It owns
  **no code**; everything is reconstructed by running the tools.

The real CLI verbs — use these exact names, they are current:

```
govbot init                 # scaffold a govbot.yml (the setup wizard)
govbot search <query>       # search the dataset registry
govbot add <datasets...>    # add datasets to govbot.yml's datasets: list
govbot remove <datasets...> # remove datasets from govbot.yml
govbot ls                   # list manifest + locally-cached datasets
govbot pull <datasets...>   # clone/update datasets (git repos) into the cache
govbot source               # stream legislative activity as JSON Lines
govbot apply                # persist fastclass results into the dataset
govbot publish              # run the manifest's publishers
govbot run                  # the full pipeline: pull -> source|classify|apply -> publish
fastclass classify -        # score a JSON-Lines doc stream from stdin
fastclass describe classifier=<bundle>   # print a bundle's tags + interface
fastclass classify --eval / --backtest / --promote   # the tuning primitives
```

Datasets are resolved at runtime through a **dataset registry** — an
index mapping a dataset id to its git repo. A bare jurisdiction code (`wy`)
and a namespaced id (`us-legislation/wy`) both resolve. `govbot search`
queries the registry; `govbot add` validates an id against it before writing
it into `govbot.yml`. `govbot pull` clones each dataset once into a shared
machine-wide cache (`~/.govbot/cache/`) and records the exact commit in
`govbot.lock` for reproducible runs.

The classify step is a Unix pipe across the two tools:

```
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
```

`govbot run` wires that pipe (plus pull and publish) automatically from
`govbot.yml`.

---

## 1. make — scaffold a new newsbot

### 1.1 Verify the tools are installed

Both `govbot` and `fastclass` must be resolvable. govbot resolves binaries in
this order: **`$PATH` → `~/.cargo/bin` → `~/.govbot/bin`**. Check:

```bash
command -v govbot    || ls ~/.cargo/bin/govbot ~/.govbot/bin/govbot 2>/dev/null
command -v fastclass || ls ~/.cargo/bin/fastclass 2>/dev/null
```

If `govbot` is missing, install the nightly:

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

If `fastclass` is missing, build it from source. `fastclass` is a separate
repo; its public home is still being decided (architecture open question), so
ask the user where their fastclass checkout lives and adapt:

```bash
# In the user's fastclass checkout:
just install     # -> ~/.cargo/bin/fastclass
# or:
cargo install --path .   # same effect, without `just`
```

If the user has no checkout yet, ask them for a path; if they have neither, the
classify stage cannot run — say so and stop here rather than scaffold a broken
project.

Ensure `~/.cargo/bin` and `~/.govbot/bin` are on `PATH`:

```bash
export PATH="$HOME/.cargo/bin:$HOME/.govbot/bin:$PATH"
```

Do not proceed until both `govbot --help` and `fastclass --help` run.

### 1.2 Interview the user

Ask, and record the answers — they drive every file you generate:

1. **Issue area.** What topic should the bot track? (climate, transit,
   housing, AI/data centers, education, …) Get 2–5 specific sub-themes — these
   become the classifier **tags**.
2. **Jurisdictions / datasets.** All jurisdictions (`all`), or a subset?
   Don't guess the codes — query the registry: `govbot search` lists every
   dataset, `govbot search wyoming` narrows it. Dataset ids are short
   (`wy`, `il`, `ca`, `ny`, …). When unsure, start with 1–3 for a fast first
   run.
3. **What to publish.** A Bluesky feed? An RSS feed / HTML index? Both? For
   Bluesky, what handle will the bot post from?

### 1.3 Generate the project

Create these files in the **current directory**. Adapt every name and tag to
the user's issue — the examples below use a transit bot; do not copy them
verbatim for a climate user.

#### `govbot.yml` — the manifest (NO `tags:` block)

```yaml
# govbot.yml — project manifest. Declares datasets, transforms, publishers,
# and pipelines. It is NOT the classifier: the tag taxonomy lives in
# classifier/classifier.yml, referenced here only by path.
$schema: https://raw.githubusercontent.com/chihacknight/govbot/main/schemas/govbot.schema.json

datasets:
  - il
  - ny
  # - all      # uncomment to track every jurisdiction

transforms:
  classify:
    command: [fastclass, classify, "-"]
    reads: docs
    writes: classification
    classifier: ./classifier

publish:
  bluesky:
    type: bluesky
    select: [transit_funding, transit_safety]   # tag names from classifier.yml
    min_score: 0.6        # calibrated final_score threshold; 0..1
    post_template: "{title}\n\n{tags} · {link}"
    # ledger: .govbot/bluesky-bluesky.ledger   # default; tracks posted bills

  feed:
    type: rss
    select: [transit_funding, transit_safety]
    base_url: "https://<user>.github.io/<repo>"
    output_dir: docs

pipelines:
  default: [classify, bluesky, feed]
```

Notes:
- **No `tags:` key.** It is retired; a manifest carrying it fails to parse.
- `publish.<name>.select` lists tag names — they must exist in the classifier
  bundle. Validate later with `fastclass describe`.
- Drop the `feed` publisher if the user only wants Bluesky, and vice versa.
- Prefer `govbot add <dataset>` over hand-editing the `datasets:` list — it
  validates each id against the registry first. Use `govbot init` to scaffold
  the whole `govbot.yml` interactively.

#### `classifier/` — the fastclass bundle

```
classifier/
  classifier.yml      the taxonomy (tags) — REQUIRED
  fusion.yml          matcher fusion weights + cascade band
  eval/
    constitution.yml  frozen gold set — NEVER shown to an LLM
    rolling.yml       refreshable working eval set
  proposals/          improvement-proposal history (starts empty)
```

`classifier/classifier.yml` — seed one tag per sub-theme from the interview:

```yaml
# classifier.yml — the taxonomy. Owned by fastclass; govbot only references
# the directory by path. Tune it with the fastclass /fastclass:improve loop.
tags:
  transit_funding:
    description: >-
      Bills funding public transit — operating subsidies, capital programs,
      fare policy, and dedicated transit revenue.
    include_keywords:
      - public transit
      - bus rapid transit
      - rail funding
      - transit operating
      - farebox
    exclude_keywords:
      - highway fund
    threshold: 0.3
  transit_safety:
    description: >-
      Bills addressing transit rider and worker safety — assaults on operators,
      platform safety, grade-crossing safety.
    include_keywords:
      - transit safety
      - operator assault
      - grade crossing
      - platform screen
    threshold: 0.3
```

`classifier/fusion.yml` — start minimal; fastclass applies defaults if absent:

```yaml
# fusion.yml — fusion weights + the cascade uncertainty band.
version: fusion-v1
```

`classifier/eval/constitution.yml` — the **frozen** gold set. Seed 2–3 bills
per tag from the user's knowledge. This set is the final judge of classifier
quality and is never shown to an LLM:

```yaml
# constitution.yml — FROZEN gold standard. Curate by hand; never edit it to
# make a number go up. Never show it to an LLM.
items:
  - id: tf-capital
    text: >-
      AN ACT appropriating funds for a regional rail capital program and
      dedicated transit operating subsidies.
    expected_tags: [transit_funding]
  - id: ts-operator
    text: >-
      A BILL increasing penalties for assault on a transit bus operator and
      funding platform safety improvements.
    expected_tags: [transit_safety]
```

`classifier/eval/rolling.yml` — the refreshable working set the improvement
loop learns from. Start with the same shape; grow it as you find misses:

```yaml
# rolling.yml — refreshable working eval set. Add bills the classifier gets
# wrong here; closing them is what /fastclass:improve does.
items:
  - id: roll-tf-fare
    text: >-
      A BILL establishing a reduced-fare transit program for low-income riders.
    expected_tags: [transit_funding]
```

Leave `classifier/proposals/` an empty directory (add a `.gitkeep`).

#### `summarizer/prompt.md` — framing prompt for a future summarize stage

```markdown
# Summarizer prompt

A future govbot `summarize` transform will use this prompt to turn a matched
bill into publish-ready framing for the <ISSUE> audience.

Frame each bill in 1–2 sentences for a <ISSUE-AUDIENCE> reader: what the bill
does, why it matters to the issue, and what stage it is at. Neutral, factual,
no hyperbole.
```

#### `.env.example` — credential template

```bash
# Copy to .env and fill in. .env is git-ignored — never commit real values.
# Bluesky credentials for the `bluesky` publisher.
# Create an APP PASSWORD at: Bluesky -> Settings -> App Passwords.
# NEVER use your main account password.
BLUESKY_HANDLE=yourbot.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
# Optional — defaults to https://bsky.social
# BLUESKY_SERVICE=https://bsky.social
```

#### `.gitignore`

```gitignore
# Generated by the tools — reconstructed on every run.
.govbot/
dist/
docs/
# Secrets — never commit.
.env
```

#### `README.md`

A short project README: what the bot tracks, the datasets, how to run it
(`govbot run`), and a pointer to this AGENT.md.

#### `CLAUDE.md` — make every later session govbot-aware

Write this into the **new project** so any Claude Code session opened here
loads the playbook without the user re-pasting the prompt:

```markdown
# CLAUDE.md

This is a **govbot newsbot** project. Before doing govbot work in this repo,
read the govbot end-user playbook and follow it:

  Read github.com/chihacknight/govbot/AGENT.md and follow it.

Project layout:
- `govbot.yml`      — the manifest (datasets / transforms / publish / pipelines)
- `classifier/`     — the fastclass classifier bundle (the tag taxonomy)
- `summarizer/`     — framing prompt for a future summarize stage
- `.env`            — Bluesky credentials (git-ignored; see `.env.example`)

To tune the classifier, use the fastclass plugin: `/fastclass:improve`.
Generated dirs (`.govbot/`, `dist/`, `docs/`) are git-ignored.
```

#### `.claude/settings.json` — import the fastclass plugin

So the user can run `/fastclass:improve` to tune the classifier:

```json
{
  "plugins": {
    "fastclass": {
      "source": "<fastclass repo path or URL>/plugins/fastclass"
    }
  }
}
```

Confirm the exact plugin-source syntax against the fastclass repo's README
(`plugins/fastclass/`); adjust if the user's fastclass checkout lives
elsewhere.

### 1.4 First run

```bash
govbot pull il ny          # clone the datasets (or: govbot pull all)
govbot run                 # pull -> classify -> apply -> publish
```

`govbot pull` clones each dataset once into the shared `~/.govbot/cache/` and
writes `govbot.lock` pinning the exact commit each resolved to. Commit
`govbot.lock` to the project repo — it makes runs reproducible. A second
`pull` (here or in any other project) reuses the cache instead of re-cloning.

For the Bluesky publisher, **always dry-run first** — see §2.

---

## 2. manage — operate the Bluesky bot

The `bluesky` publisher is a **posting bot**: it posts to a normal Bluesky
account via the AT Protocol and runs to completion (no server). It is
idempotent — a posted-state ledger keeps re-runs from double-posting.

### 2.1 Create the app password

1. In the Bluesky app: **Settings → App Passwords → Add App Password**.
2. Copy the generated password (format `xxxx-xxxx-xxxx-xxxx`).
3. Put credentials in the environment — **never in `govbot.yml`**:

```bash
cp .env.example .env
# edit .env:
#   BLUESKY_HANDLE=yourbot.bsky.social
#   BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

Load it before running: `set -a; source .env; set +a`.

### 2.2 The publisher config

Under `govbot.yml: publish:` (see the template in §1.3):

| Field | Meaning |
|---|---|
| `type: bluesky` | selects the Bluesky publisher |
| `select` | tag names to post — must exist in the classifier bundle |
| `min_score` | minimum calibrated `final_score` (0..1) to post; default `0.6` |
| `post_template` | post text; placeholders `{title} {tags} {link} {identifier} {session} {score}`; truncated to 300 chars |
| `ledger` | posted-state ledger path; default `.govbot/bluesky-<name>.ledger` |

Credentials are **never** config fields — they are env-only.

### 2.3 Dry-run first — always

```bash
govbot publish --publisher bluesky --dry-run
```

`--dry-run` renders the posts that *would* be sent and **touches no network
and no ledger**. Review the rendered text with the user — check the template,
the 300-char truncation, and that `min_score` is neither too loose (spam) nor
too tight (silence). Adjust `post_template` / `min_score` and re-dry-run.

### 2.4 Go live

```bash
set -a; source .env; set +a
govbot publish --publisher bluesky
```

The publisher authenticates (`com.atproto.server.createSession`), posts each
matching bill not already in the ledger (`com.atproto.repo.createRecord`), and
appends each posted bill's id to the ledger. Re-running posts only new
matches.

### 2.5 Schedule it

The bot runs from cron/CI — no always-on server.

**cron** (every 6 hours):

```cron
0 */6 * * * cd /path/to/project && set -a && . ./.env && set +a && govbot run >> .govbot/run.log 2>&1
```

**GitHub Actions** (`.github/workflows/newsbot.yml`):

```yaml
name: newsbot
on:
  schedule: [{ cron: "0 */6 * * *" }]
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    env:
      BLUESKY_HANDLE: ${{ secrets.BLUESKY_HANDLE }}
      BLUESKY_APP_PASSWORD: ${{ secrets.BLUESKY_APP_PASSWORD }}
    steps:
      - uses: actions/checkout@v4
      - name: Install govbot + fastclass
        run: |
          sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
          # install fastclass per its repo's instructions
          echo "$HOME/.govbot/bin:$HOME/.cargo/bin" >> "$GITHUB_PATH"
      - name: Run the newsbot
        run: govbot run
      # Commit the ledger back so re-runs stay idempotent across CI runs:
      - name: Persist the posted-state ledger
        run: |
          git add -f .govbot/*.ledger || true
          git commit -m "newsbot: update posted-state ledger" || true
          git push || true
```

In CI the `.govbot/` ledger is ephemeral unless persisted — commit the
`*.ledger` file back (as above) or store it in a cache/artifact, or the bot
will re-post on every run.

---

## 3. update — evolve an existing project

Open the project, read its `govbot.yml` and `classifier/classifier.yml`, then:

### Add or remove a dataset

Use the registry-backed commands rather than hand-editing `govbot.yml`:

```bash
govbot search <query>        # find the dataset id in the registry
govbot add <new-dataset>     # validate it and add it to govbot.yml datasets:
govbot pull <new-dataset>    # clone it (updates govbot.lock)
govbot run
```

To drop a dataset: `govbot remove <dataset>`. `govbot ls` shows the manifest's
datasets and which are cached locally.

### Add or remove a publisher / change what gets posted

Edit `govbot.yml: publish:` — add a publisher block, or change a `select`
list or `min_score`. Validate that every `select` tag exists in the bundle:

```bash
fastclass describe classifier=./classifier   # prints the bundle's tag list
```

Then dry-run any Bluesky publisher before going live (§2.3).

### Widen or narrow the classifier scope

The taxonomy lives in `classifier/classifier.yml`. **Do not hand-tune it by
guessing keywords** — delegate to the fastclass improvement loop, which proves
each change against the frozen gold set.

1. **Measure** where the classifier stands:
   ```bash
   fastclass classify --eval constitution classifier=./classifier
   fastclass classify --eval rolling      classifier=./classifier
   ```
2. **Find misses.** Add bills the classifier gets wrong to
   `classifier/eval/rolling.yml` with their correct `expected_tags`. To widen
   scope, add a new tag to `classifier.yml` plus gold examples for it in both
   eval sets.
3. **Improve.** Run the fastclass plugin — it studies the rolling failures,
   drafts a proposal under `classifier/proposals/`, and is the supported way
   to tune the bundle:
   ```
   /fastclass:improve
   ```
4. **Backtest** the proposal — proves it against the frozen constitution:
   ```bash
   fastclass classify --backtest classifier/proposals/prop-0001.yml classifier=./classifier
   ```
5. **Promote** a passing proposal into the bundle:
   ```bash
   fastclass classify --promote classifier/proposals/prop-0001.yml classifier=./classifier
   ```
6. **Re-run** the bot: `govbot run`.

Hard rule, inherited from fastclass: **never show `classifier/eval/
constitution.yml` to an LLM.** It is the frozen judge; seeing it would corrupt
the eval. The improvement loop only ever reads `rolling.yml`.

---

## Conventions

- Ground every command in the real CLI above. If a verb is not in the
  reference list, it does not exist — check `govbot --help` / `fastclass --help`.
- `govbot.yml` never has `tags:`. The taxonomy is the classifier bundle.
- Credentials are environment-only. Never write a secret into `govbot.yml`,
  `.env.example`, or any committed file.
- Bluesky: dry-run before every first live run after a config change.
- Generated dirs (`.govbot/`, `dist/`, `docs/`) are git-ignored; the project
  is a dozen small text files plus tool artifacts.
