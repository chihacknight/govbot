# AGENT.md — build a government-news bot with govbot

You are a Claude Code session helping an activist stand up, operate, or
evolve a **govbot newsbot** — a project that pulls real legislative data,
filters it down to the issue the activist cares about, and publishes the
matches (today, to a Bluesky account) at **nearly-free** running cost.

govbot is a **4-tool stack** and the playbook below follows that shape:

1. **Select real gov data** — `govbot pull` clones the legislation of all
   50 states, DC, the territories, and federal Congress from a content-
   addressed registry of git repos. Scrapers thanks to OpenStates.
2. **Filter / transform** — fastclass tags each bill against an issue
   taxonomy the activist owns; the publishers filter on those tags. The
   planned `summarize` transform (local-LLM digests of grouped bills with
   a trace of model + source data) is not yet built — userland keeps a
   `summarizer/prompt.md` stub for when it lands.
3. **Publish with receipts** — RSS, HTML, JSON, DuckDB, and a Bluesky
   posting bot today; X and a "receipts" GitHub Pages artifact (the
   deterministic provenance behind every AI digest: model id, source
   bills, fastclass reasoning, regen recipe) are roadmap.
4. **Coding-agent-native dev experience** — *this file is tool #4*. A
   fresh Claude Code session reads it and can make / manage / update a
   project end-to-end with no other onboarding.

The cost bar is climate-activist's: **nearly free to run, worth reading**.
If a choice in the playbook would push the activist toward a paid API
when a local model would do, push back; if a choice would make a post less
trustworthy, prefer the choice that ships the receipt.

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

A user comes to you for one of three things. Identify which, then jump to
that section. Each job exercises the 4-tool stack from a different angle:
**make** scaffolds the pull+filter+publish chain (today's MVP — does NOT
yet scaffold a summarize transform or a receipts page, neither of which
exists); **manage** keeps the loop running and introduces
`/fastclass:improve autonomous` after first ratification (the
activist-default for hands-off improvement); **update** evolves the stack.

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
govbot apply                # persist fastclass results under <project>/tags/
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
    # `{link}` defaults to the companion `html` publisher's base_url (the
    # human landing page), so the cleanest setup is to declare an `html`
    # publisher in this manifest. `base_url` here is only the fallback when
    # no `html` publisher is configured.
    base_url: "https://<user>.github.io/<repo>"
    post_template: "{title}\n\n{tags} · {link}"
    # ledger: state/bluesky-bluesky.ledger   # default; tracks posted bills

  feed:
    type: rss             # writes <output_dir>/feed.xml (only)
    select: [transit_funding, transit_safety]
    base_url: "https://<user>.github.io/<repo>"
    output_dir: docs

  site:
    type: html            # writes <output_dir>/index.html (only)
    select: [transit_funding, transit_safety]
    base_url: "https://<user>.github.io/<repo>"
    output_dir: docs

pipelines:
  default: [classify, bluesky, feed, site]
```

Notes:
- **No `tags:` key.** It is retired; a manifest carrying it fails to parse.
- **One publisher type, one artifact.** `type: rss` writes only the RSS
  feed; `type: html` writes only the HTML index. Declare both to get both
  (an earlier release wrote both files from each — a silent
  last-writer-wins collision on `index.html`).
- `publish.<name>.select` lists tag names — they must exist in the classifier
  bundle. Validate later with `fastclass describe`.
- Drop the `feed` / `site` publishers if the user only wants Bluesky, and
  vice versa.
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
# Classification output from `govbot apply` — regenerated each run.
# Remove this line to commit classification provenance.
tags/
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

Tool-managed dirs (all git-ignored by default):
- `.govbot/`        — the tool's CACHE (cloned datasets, sync state); the
                      `node_modules/` equivalent. Never edit by hand;
                      `rm -rf .govbot/` is always safe.
- `tags/`           — classification OUTPUT from `govbot apply`
                      (`tags/<dataset>/country:.../sessions/<id>/<tag>.tag.json`).
                      Remove `tags/` from `.gitignore` if you want
                      classification provenance committed.
- `state/`          — publisher STATE from `govbot publish` (e.g. the
                      bluesky publisher's posted-state ledger,
                      `state/bluesky-<name>.ledger`). Regenerable-but-
                      operational: deleting it makes the next run
                      double-post. Remove `state/` from `.gitignore` to
                      commit post history and let cold clones resume.
- `dist/` / `docs/` — publisher output from `govbot publish`.

To tune the classifier, use the fastclass plugin: `/fastclass:improve`.
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

#### Install the semantic Tier-2 model

A scaffolded classifier bundle has the taxonomy and fusion config — but no
embedding model. Without one, the cascade in `fusion.yml`'s
`uncertainty_band` silently degrades to lexical-only matchers, which means
the bot will **miss paraphrases and euphemisms** (real-data audits typically
show this as a 10–15 point recall gap on issue-flavored language: "energy
diversity" never matches `clean_energy`, etc.).

Fix this once, at scaffold time, by running the install-model plugin
command:

```
/fastclass:install-model
```

The command shows the vetted-model list, defaults to the recommended small
encoder (sentence-transformers/all-MiniLM-L6-v2, ~22 MB), downloads it into
the project-shared cache at `~/.govbot/models/<sha-prefix>/`, and links it
into `classifier/model/` so `govbot run` picks up Tier-2 automatically on
the next pipeline pass. Verify with:

```bash
fastclass describe classifier=./classifier
# JSON output should include a `model: {…}` block.
```

If the download fails (offline laptop, HuggingFace rate-limit), the CLI
prints a `curl` recipe the user can run themselves and re-invoke the
plugin command — the install path is idempotent.

### 1.4 First run

```bash
govbot pull il ny          # clone the datasets (or: govbot pull all)
govbot run --dry-run       # pull -> classify -> apply -> publish (render-only)
govbot run                 # same, but actually emits / posts
```

`govbot pull` clones each dataset once into the shared `~/.govbot/cache/` and
writes `govbot.lock` pinning the exact commit each resolved to. Commit
`govbot.lock` to the project repo — it makes runs reproducible. A second
`pull` (here or in any other project) reuses the cache instead of re-cloning.

`govbot run --dry-run` propagates `--dry-run` to every publisher — the
`bluesky` publisher honours this by rendering the posts it *would* send and
touching no network and no ledger. Pair the dry-run with §2.3 before going
live with the Bluesky bot.

When the Bluesky creds (`BLUESKY_HANDLE` / `BLUESKY_APP_PASSWORD`) are not
set, the `bluesky` publisher logs a `WARN` and **skips** rather than failing
the pipeline — so a first-time `govbot run` without creds still emits the
RSS / HTML feeds.

---

## 2. manage — operate the Bluesky bot

The `bluesky` publisher is a **posting bot**: it posts to a normal Bluesky
account via the AT Protocol and runs to completion (no server). It is
idempotent — a posted-state ledger keeps re-runs from double-posting.

**Activist default after first ratification: autonomous mode.** Once the
activist has ratified one classifier proposal end-to-end (so they have
felt the loop once and seen what the constitution gate does) — the
beginner-default ongoing posture is the **autonomous** form of the
improvement loop, invoked as:

```
/fastclass:improve autonomous
```

Under the hood this runs `fastclass classify --promote <prop>.yml
--autonomous`. The constitution stays sovereign: proposals that pass the
frozen constitution gate apply as usual, and proposals where the
constitution is silent (a **coverage gap** — the gate cannot prove the
change good or bad) re-test against the rolling eval set and land only
if rolling proves them safe (flips at least one rolling failure to
passing, regresses no rolling case, no per-tag precision loss). A
bad-fix reject (counts moved on the constitution but F1 did not improve)
or any rolling regression always refuses — the rolling gate is strictly
weaker than the constitution and cannot overrule a precision-regression
reject. The `fastclass.lock` file marks autonomously-applied proposals
with `generated_by: autonomous-coverage-gap`, so the audit trail is
preserved — the receipt story extends into the classifier.

This is the mode that lets the activist crew run the bot **hands-off
between ratifications** without giving up provenance, which is the whole
reason the cost story is "nearly free to operate". Use it as the
ongoing-improvement default; drop back to the reviewed
`/fastclass:improve` path (§3) when you want to see and ratify a
specific proposal — e.g. when widening scope with a new tag, or after a
flurry of autonomous coverage-gap lands you want to read through.

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
| `base_url` | fallback prefix for `{link}` when no companion `html` publisher is configured; same shape as the rss/html publishers' `base_url` |
| `post_template` | post text; placeholders `{title} {tags} {link} {identifier} {session} {score}`; truncated to 300 chars |
| `ledger` | posted-state ledger path; default `state/bluesky-<name>.ledger` (peer to `tags/` and `dist/`; NOT under `.govbot/`, which is the tool's cache). A ledger at the legacy `.govbot/bluesky-<name>.ledger` path is read as a fallback so upgrades don't lose history. |

`{link}` resolves in this order: (1) the manifest's `html` publisher's
`base_url` — the **human-readable landing page** activists actually click
through to; (2) the bluesky publisher's own `base_url` joined to the bill's
dataset path; (3) the bill's first upstream source URL. Configuring an
`html` publisher alongside `bluesky` makes the default useful — without it,
`{link}` resolves to a raw `metadata.json` path under `base_url`.

Credentials are **never** config fields — they are env-only.

### 2.3 Dry-run first — always

```bash
govbot publish --publisher bluesky --dry-run
# or, end-to-end through the whole pipeline:
govbot run --dry-run
```

`--dry-run` renders the posts that *would* be sent and **touches no network
and no ledger**. Review the rendered text with the user — check the template,
the 300-char truncation, and that `min_score` is neither too loose (spam) nor
too tight (silence). Adjust `post_template` / `min_score` and re-dry-run.

`govbot run --dry-run` is the recommended first invocation: it propagates
`--dry-run` to every publisher and exits clean even without Bluesky creds.

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
          git add -f state/*.ledger || true
          git commit -m "newsbot: update posted-state ledger" || true
          git push || true
```

In CI the `state/` ledger is ephemeral unless persisted — commit the
`*.ledger` file back (as above; you'll also want to remove the `state/`
line from `.gitignore` so the commit isn't a force-add forever) or store
it in a cache/artifact, or the bot will re-post on every run.

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
   /fastclass:improve            # reviewed: you ratify each proposal
   /fastclass:improve autonomous # hands-off: constitution-passing applies,
                                 # coverage-gap re-tests against rolling
   ```
   Use the reviewed form for the first pass (so you see what the gate does)
   and when widening scope with a new tag; switch to `autonomous` as the
   ongoing default once you've felt the loop — see §2's autonomous-mode
   callout for the gate semantics.
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
- Three tool-managed dirs, each with a distinct role: `.govbot/` is the
  CACHE (the `node_modules/` equivalent — never edited, fully regenerable),
  `tags/` is `govbot apply`'s classification OUTPUT
  (`tags/<dataset>/country:.../sessions/<id>/<tag>.tag.json`), and
  `dist/` / `docs/` are publisher output. All four are git-ignored by
  default; the project is a dozen small text files plus tool artifacts.
