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
`template`, `base_template` (the `-paused` suffix stripped — the locale's durable
identity, which downstream keys per-template facts off), `paused`, `runner`,
`expected_workflows`.
A locale is paused when its `template` ends in `-paused`. `expected_workflows` lists the
template's workflow files as they exist in rendered repos (`.j2` stripped), minus the
locale's `disabled_jobs`. A config that references an unknown template, or a template
with no workflow files on disk, fails loudly with a nonzero exit — never an empty record.

## Metrics: poller + shipper

`collect --metrics-only` turns jurisdiction records into Grafana Cloud metrics in three
steps, each its own module:

- **[fleet_poller.py](fleet_poller.py)** — all GitHub REST knowledge. For every repo:
  the latest *completed* run's conclusion (an in-progress run never masks the last
  finished one) and hours since the last successful run per expected workflow, plus
  hours since the last commit touching the repo's data path (`_data/<locale>/` in
  scraper repos, `country:us/` in data repos). The record shape is locked by
  [schemas/fleet-poller-record.schema.json](../../schemas/fleet-poller-record.schema.json)
  and carries `config`/`polled_at` lineage. Per-repo failures are recorded on the
  output record's `errors` list and skipped — one bad repo never aborts the sweep —
  but `collect` exits 1 when any repo erred, after shipping what it has: a degraded
  sweep must never look like a clean one. An unknown template is a config gap and
  fails the sweep before any polling.
- **[metrics_shipper.py](metrics_shipper.py)** — pure encoder from poller records to the
  Influx line-protocol payload Grafana Cloud ingests. Series produced:
  `fleet_workflow_run_status` (1 = latest run succeeded),
  `fleet_workflow_run_hours_since_success`, and `fleet_repo_data_commit_age_hours`.
  Labels are capped at `state`/`org`/`workflow`/`paused`. (The orchestrator adds one more,
  untagged, series each sweep — `fleet_collector_heartbeat` — via `encode_heartbeat`; see below.)
- **[metrics_push.py](metrics_push.py)** + **[http_util.py](http_util.py)** — POST with
  retry/backoff (429 honors Retry-After — as does a 403 that is really GitHub rate
  limiting — 5xx backs off, other 4xx fails fast; an exhausted quota with no
  Retry-After also fails fast, since its reset is up to an hour out and the next
  scheduled sweep will retry anyway). Repos are polled concurrently, bounded at 8
  workers to stay inside GitHub's secondary-rate-limit etiquette.

## Logs: harvester + Loki shipper + watermark

`collect --logs-only` (and the logs leg of `run`) ships each hourly sweep's *new*
run logs to Grafana Cloud Loki — never the same run twice — in three modules:

- **[log_harvester.py](log_harvester.py)** — all GitHub-logs REST knowledge, the
  logs counterpart to the poller. For each repo it lists recent runs, ships only
  those newer than the per-(repo, workflow) watermark, and for every new *completed*
  run downloads the log archive, unpacks the top-level per-job logs, parses the
  RFC 3339 timestamp GitHub prefixes on every line, drops known-noise lines
  (`##[group]`/`##[endgroup]`, blanks), and applies the **volume policy**: full logs
  for a failed/cancelled/timed-out run (the ones you debug) — bounded to the last
  ~256 KB, the tail where the error and traceback land, since a real Florida run
  shipped a 9 MB dump that timed out the push and tripped Loki's rate limit — and
  the last ~100 lines for a success (proof it ran, not a transcript). An over-cap
  failure gets a marker line naming how many lines were dropped. Per-repo failures
  are recorded and skipped — one bad repo never aborts the sweep.
- **[watermark.py](watermark.py)** — the incremental boundary: a JSON map of
  `"<org>/<repo>/<workflow>"` → the last shipped run id, so re-running an unchanged
  window ships nothing. Persisted between hourly sweeps by the Actions cache; a lost
  cache reads as empty and the harvester falls back to a bounded **one-day
  look-back**, recovering the last day rather than re-shipping a repo's whole
  history. The look-back bounds *every* sweep (not just a cold start), and the run
  listing pages just far enough to cover it, so selection never wants a run the
  listing didn't fetch. The flip side, by policy: a run created more than a day
  before the sweep is outside the shipping contract even with a healthy watermark —
  a collector outage longer than a day loses the overflow, the same budget trade as
  the cold-start rule. The watermark advances only across contiguous shipped runs —
  an in-progress run, one whose archive fetch failed, or a label the shipper would
  reject halts advancement so it is retried next sweep, never stepped over.
- **[logs_shipper.py](logs_shipper.py)** + **[logs_push.py](logs_push.py)** — a pure
  encoder from labeled batches to the Loki push payload (reusing http_util's
  retry/backoff POST). Stream labels are capped at `org`/`state`/`workflow`/`outcome`;
  run id, job, and the original `event_time` are high-cardinality, so they ride in
  each entry's Loki **structured metadata**, never as labels. Pushes go **per workflow** — one payload
  per watermark entry, each watermark advancing only after its own payload lands —
  so one un-pushable payload (an oversized recovery sweep, say) fails only its own
  workflow's logs and holds only its own watermark, never the whole fleet's.

### Ingest window (the retired risk)

An hourly collector ships logs from runs that finished up to an hour — or, on a lost
cache, a day — earlier, older than Loki's ingest window. The PRD's first risk to
retire, so it was probed, not assumed. `probe-loki` pushes one line per age (1–24 h
old) and — crucially — **queries each back**, because the HTTP status alone lies:
Grafana Cloud answers the push `204` and then *silently discards* a sample older than
its window, so a status-only probe reports a false "accepted."

**Probed result**: on the validated Grafana Cloud stack (`logs-prod-036`), only the
last ~2 h of ages were actually queryable; everything older was accepted-then-dropped.
The default 168 h reject window did **not** apply. So the event-time strategy would
lose every log from a run that finished more than ~2 h before the sweep — the whole
recovery window and any slow run.

**Decision (fallback, adopted)**: stamp every entry at **collection time** — this
sweep's `now`, plus a per-stream nanosecond offset for ordering — which always lands
inside the window. The run's real event time is preserved as `event_time` structured
metadata, so logs stay correlatable to when they happened (display it as a column in
Grafana) without depending on the index timestamp. Event-time ordering is preserved:
the offsets are assigned in event-time order within each stream.

### Budgets

- **GitHub API**: only single-page queries (`per_page` ≤ 3) — 2 per workflow (recent
  runs, latest success) + 1 per repo for the data-path commit. Current fleet: 112 repos × 1 workflow → **336
  requests per sweep**, well inside the default `GITHUB_TOKEN` limit of 1000/hour;
  `render-snapshots.sh` asserts the real-fleet count stays under 400. The logs leg
  adds 1 run-listing request per workflow (paging up to 4 only when a page is full
  and still inside the 24 h window — page 1 suffices on a normal hourly sweep) plus
  1 archive download per *new* run — bounded by how many runs actually finished in
  the hour, typically a handful, since the watermark skips everything already shipped.
- **Series cardinality**: 2 series per repo/workflow + 1 per repo, plus the single global
  `fleet_collector_heartbeat` pair the orchestrator emits per sweep → **~336 series (+2 heartbeat)**
  for the current fleet, against the Grafana Cloud free-tier budget of ~10k active series.
  10× fleet growth still fits.
- **Log volume**: the success tail and the **256 KB failure cap** are what keep logs
  in budget — and inside Loki's ingestion rate limit. Worst case — one new run per
  repo per hour (scrapers mostly run less often), ~100-line success tails at ~200 B/line
  ≈ 20 KB/run → 112 runs × 24 h × 30 d ≈ **1.6 GB/month**, plus capped failure logs
  (say 5% at the 256 KB ceiling) ≈ another ~1 GB → **≈ 3 GB/month**, well inside the
  Grafana Cloud free-tier budget of **50 GB/month, 14-day retention** (re-verify at
  signup). Even every failure hitting the cap every hour (112 × 256 KB × 720) is ~20 GB,
  still under budget. Pushes are **gzipped** (log text compresses ~10×), which cuts
  egress and upload time; an uncapped 9 MB failure (measured) both timed out the push
  and tripped Loki's per-tenant ingestion rate limit (HTTP 429), which the cap fixes at
  the source by keeping each push small.

### Credentials (environment variables)

| Variable | Meaning |
| --- | --- |
| `GITHUB_TOKEN` | **required for live polls**: one sweep ≈ 336 requests, the unauthenticated limit is 60/hour (the CLI refuses to start without it) |
| `GRAFANA_PUSH_URL` | Influx write endpoint, `https://influx-…/api/v1/push/influx/write` |
| `GRAFANA_PUSH_USER` / `GRAFANA_PUSH_KEY` | metrics instance ID / access-policy token (`metrics:write`) |
| `GRAFANA_LOGS_URL` | Loki push endpoint, `https://logs-…/loki/api/v1/push` (logs leg + `probe-loki`) |
| `GRAFANA_LOGS_USER` / `GRAFANA_LOGS_KEY` | logs instance ID / access-policy token (`logs:write`; also `logs:read` if you run `probe-loki`, whose query-back reads the entries back) |
| `GRAFANA_QUERY_URL` | Prometheus API base, `https://prometheus-…/api/prom` (live-check only) |
| `GRAFANA_QUERY_USER` / `GRAFANA_QUERY_KEY` | Prometheus instance ID / token (`metrics:read`, live-check only) |
| `GRAFANA_DASHBOARD_URL` | stack base URL, `https://<stack>.grafana.net` (`check-dashboard` only) |
| `GRAFANA_DASHBOARD_KEY` | service-account token with dashboard write (`check-dashboard` only; **bearer**-authed, unlike the Basic-auth push endpoints) |

## Dashboard: the fleet view, as code

One dashboard answers the whole question — anything red, anything stale, and what did it
say — and it is committed rather than hand-built, so the Grafana side is reproducible:

- **[dashboard.py](dashboard.py)** builds it as data; **[dashboards/fleet-overview.json](dashboards/fleet-overview.json)**
  is that build, rendered and committed. The JSON is what you import; the module is what
  you review. The render script re-renders the dashboard and fails if the committed copy
  has drifted — it does not rewrite the file, so regenerate it yourself with
  `main.py dashboard --out dashboards/fleet-overview.json` after editing the builder. The
  file in the repo can never quietly stop matching the code that explains it.
- **Four panels.** Two status grids on `fleet_workflow_run_status` — **Scrapers** then
  **Formatters**, the order the actions actually run — each one tile per jurisdiction,
  coloured by that jurisdiction's latest completed run. Then one full-width freshness table
  on `fleet_repo_data_commit_age_hours`, and a logs panel on the Loki streams. The table
  turns red above 48 h — the same number the staleness alert fires on, kept in one place so
  the dashboard and the alert cannot disagree.
- **One grid per workflow, and a tile says only its state.** 112 tiles in a single panel
  shrank the text past reading; 56 apiece with the workflow carried by the panel title
  leaves the two-letter jurisdiction code rendered as large as the OK/FAILING beside it.
  (The code renders as the metric label stores it, lower-case — Grafana has no way to
  upper-case a series name without hardcoding all 56 jurisdictions into the JSON, which
  would cost the property that a new jurisdiction appears on its own.)
- **Paused jurisdictions are dimmed in place, not split out.** Out of session, a failing run
  and a month-old data commit are the legislative calendar, not an incident. In the grids
  they come from a second query overridden to a flat colour — never red — whose text still
  says whether the last run failed. In the freshness table they are a column. A separate
  panel for them, which is what this replaced, was an empty box whenever the whole fleet
  was in session, which is most of the time.
- **One place the never-red rule cannot hold**: a table colours a column by threshold, not
  a row by another row's value, so a paused repo stale past 48 h does turn red in the
  freshness table. Sorting keeps it out of the way — in-session repos first, worst
  staleness at the top of them — so rows needing action outrank rows waiting for a session.
- **Nothing in the JSON belongs to one account.** Datasources are pickers (`${metrics}`,
  `${logs}`), never UIDs, and the dashboard carries `id: null` with a stable uid, so the
  same file imports into any stack instead of colliding with whatever holds that id there.
  The pickers do *default* to this fleet's stack (`grafanacloud-govbot-prom` /
  `grafanacloud-govbot-logs`) so an import renders immediately — a default, not a hardcode:
  another stack changes them in the picker and nothing else about the JSON differs.
- **Clicking a freshness row narrows the whole board to that jurisdiction** — grids, table,
  and logs — through the single `Jurisdiction` picker, so the filter shown at the top is
  always the filter applied. The link is an absolute dashboard path carrying the current
  time range; the bare `?var=…` relative URL it replaced rewrote the address bar and re-ran
  nothing, so it looked live and did nothing. It sets the jurisdiction only: adding the org
  narrowed to one of that jurisdiction's two repos and hid its sibling.
- **Every metric panel looks back six hours, and that number is measured.** An instant
  query resolves against Prometheus's 5-minute staleness window, so a bare selector finds
  nothing between sweeps — the board reads "No data", which it did on a real import.
  `last_over_time(…[6h])` keeps the queries instant vectors, leaving the table
  transformations and the stat reducer untouched.

  Six hours, not one, because **the hourly cron is aspirational**. GitHub runs scheduled
  workflows best-effort, and on a fork's non-default branch they drift hard: 25 consecutive
  sweeps (2026-07-22..25) showed a median gap of **2.0h and a maximum of 3.6h**, with 4 of
  24 gaps past three hours. A window sized off `cron: "0 * * * *"` blanked the board a
  second time. Size it off the observed gap, with headroom.

  The cost, worth knowing before you trust a number: a displayed value can be one window
  old, so a repo whose data commit has just crossed 48 h can still read green for up to six
  hours. **The same drift applies to alerting** — a "collector heartbeat absent 3h" rule
  would false-fire on a routine 3.6h gap, so task 0006 needs to pick its thresholds from
  this measurement, not from the cron expression.
- **Filters are label-driven and URL-synced.** The state, org, and workflow pickers read
  their options from the metrics labels and the outcome picker from Loki's, so a
  jurisdiction added to the pipeline-manager config appears on its next sweep with no
  dashboard edit. Each picker speaks its own datasource's variable-query dialect —
  a Prometheus-shaped query on the Loki picker leaves it empty — and every one sets
  `allValue: ".*"` explicitly, because a blank all-value makes Grafana expand "All" to
  the options it resolved, or to the empty string when it resolved none, which quietly
  turns each `=~` matcher into one that matches nothing. Every filter round-trips
  through the URL — "here is Wyoming's freshness" is a link you can paste to someone,
  and each freshness row links to its own jurisdiction's filtered view. The all-value is
  `.+` rather than `.*` because LogQL rejects a stream selector whose every matcher is
  empty-compatible: with all four pickers on All, `.*` would make the logs panel a parse
  error instead of a query.
- **Run id and run URL surface by expanding a log line**, not as labels: they travel as
  structured metadata (see Budgets above), which is why log details stay on.

### Importing it into a fresh stack

Grafana → Dashboards → New → Import → upload
[dashboards/fleet-overview.json](dashboards/fleet-overview.json). It asks for a name,
folder, and uid, and nothing else. No edits, no find-and-replace.

**Then check the two datasource pickers at the top of the dashboard.** The import screen
never asks about datasources — that prompt only appears for dashboards carrying an
`__inputs` block, and this one parameterizes through template variables instead — so
Grafana auto-selects the first datasource of each type it finds. A Grafana Cloud stack has
more than one Prometheus-type datasource (`grafanacloud-<stack>-prom` sits alongside
`grafanacloud-usage`), and landing on the wrong one renders "No data" on every metric
panel while looking perfectly healthy. If the board is empty, look here first.

To do the same unattended — and to prove the file still imports — point
`check-dashboard` at the stack:

```bash
export GRAFANA_DASHBOARD_URL=https://<stack>.grafana.net
export GRAFANA_DASHBOARD_KEY=<service-account token with dashboard write>
pipenv run python main.py check-dashboard
```

It POSTs the dashboard to the stack's API keyed by uid (so re-running updates rather than
littering copies) and then **reads it back by uid**, checking both the panels and the
template variables. A 200 on the push is not proof it renders — Grafana will store a
payload it then shows as an empty dashboard — and panels alone are not proof either:
every panel filters on `=~"$state"` and points at `${metrics}`/`${logs}`, so a variable
Grafana declined to migrate leaves all five panels present and all five rendering nothing.
Missing credentials exit 0 with a skip notice, so an offline run passes without an account.

## Usage

### As a Standalone Script

```bash
cd actions/fleet-monitor
pipenv install
pipenv run python main.py list-fleet --config-dir ../pipeline-manager

# Poll the real fleet and print the metric payload without pushing:
GITHUB_TOKEN=$(gh auth token) pipenv run python main.py collect --metrics-only \
  --config-dir ../pipeline-manager --dry-run

# Same, but push to Grafana Cloud (needs GRAFANA_PUSH_* env vars):
pipenv run python main.py collect --metrics-only --config-dir ../pipeline-manager

# Harvest new run logs and print the Loki payload without pushing. The watermark
# tracks what has been *pushed*; --dry-run neither pushes nor advances it, so a
# dry-run repeats — idempotency ("a re-run of the same window ships nothing")
# applies to real, non-dry-run collections:
GITHUB_TOKEN=$(gh auth token) pipenv run python main.py collect --logs-only \
  --config-dir ../pipeline-manager --watermark-file .watermarks/logs.json --dry-run

# Diagnose the Loki ingest window: push one line per age (1–24 h old) and query
# each BACK to see which actually landed — Grafana Cloud 204s a too-old push then
# silently drops it (needs GRAFANA_LOGS_* vars; the token also needs logs:read):
pipenv run python main.py probe-loki

# Print the dashboard JSON, or regenerate the committed copy after editing
# dashboard.py (the render script fails if the two have drifted):
pipenv run python main.py dashboard
pipenv run python main.py dashboard --out dashboards/fleet-overview.json

# Import the dashboard into a real stack and read it back (needs
# GRAFANA_DASHBOARD_URL/KEY; exits 0 with a notice when they're absent):
pipenv run python main.py check-dashboard

# End-to-end proof: poll, push, then query the series back (needs all six
# GRAFANA_* vars; exits 0 with a notice when they're absent):
pipenv run python main.py live-check --config-dir ../pipeline-manager

# The unattended sweep the hourly workflow runs: poll, push metrics + a collector
# heartbeat, then harvest + ship new run logs. Exits nonzero only on an outright
# collector failure (config/poll error, or a failed push) — per-repo errors stay green:
pipenv run python main.py run --config-dir ../pipeline-manager \
  --watermark-file .watermarks/logs.json
```

`run` is the orchestrator: it wires config reader → poller → shipper, appends
a `fleet_collector_heartbeat` series (`repos`, `errors`) that ships on **every**
sweep, then harvests each repo's new run logs and ships them to Loki. Its exit
contract differs from `collect`'s by design — a red workflow run
must mean the *collector* is down, so per-repo poll and log-harvest errors are
logged but keep the run green (a degraded fleet surfaces through the telemetry and
Grafana alerts), and only a config/poll error or a failed push exits nonzero. Because the
heartbeat always ships, an all-null sweep still proves the collector ran. The logs
leg is idempotent through the `--watermark-file`: without it, every run re-ships the
last day of logs, so production passes a file backed by a persistent store.

`--config-dir` points at any directory holding fleet config YAMLs and their `templates/`
folder, so the CLI runs against fixtures or the real config. Options can also be set via
`FLEET_MONITOR_*` environment variables (click's `auto_envvar_prefix`, matching sibling
actions), e.g. `FLEET_MONITOR_LIST_FLEET_CONFIG_DIR`.

### Running the hourly workflow

[`.github/workflows/fleet-monitor.yml`](../../.github/workflows/fleet-monitor.yml) runs the
orchestrator (`run`) once an hour against the real `actions/pipeline-manager` config and pushes
metrics + the collector heartbeat to Grafana Cloud and new run logs to Loki. It's read-only on
GitHub (the default `GITHUB_TOKEN` covers all reads), bounded by a 20-minute job timeout, and
serialized by a `fleet-monitor` concurrency group so a manual dispatch never overlaps a
scheduled sweep. The log watermark is carried between sweeps by the Actions cache (restore by
prefix before the sweep, save a fresh `run_id` key after), so the logs leg stays incremental; a
cold cache is safe — the harvester falls back to a bounded 24 h look-back.

To bring it up in a fork against your own Grafana Cloud account, set **two secrets** and **four
variables** on the repo (Settings → Secrets and variables → Actions):

| Kind | Name | Value |
| --- | --- | --- |
| **Secret** | `GRAFANA_PUSH_KEY` | Grafana Cloud access-policy token with `metrics:write` |
| **Secret** | `GRAFANA_LOGS_KEY` | Grafana Cloud access-policy token with `logs:write` |
| Variable | `GRAFANA_PUSH_URL` | Influx write endpoint, `https://influx-…/api/v1/push/influx/write` |
| Variable | `GRAFANA_PUSH_USER` | Metrics instance ID |
| Variable | `GRAFANA_LOGS_URL` | Loki push endpoint, `https://logs-…/loki/api/v1/push` |
| Variable | `GRAFANA_LOGS_USER` | Logs instance ID |

The endpoint and instance ID aren't secret, so they're repo **variables** (`vars`), keeping the
Grafana write key the single secret. Then enable Actions on the fork (the Actions tab, if a fresh
fork has workflows disabled) and trigger a first sweep by hand — **Actions → Fleet Monitor → Run
workflow** (`workflow_dispatch`) — to confirm it goes green and the metrics land before the hourly
schedule takes over. A forced failure (e.g. a bad `GRAFANA_PUSH_KEY`) exits nonzero and the run
shows red, which is what the `heartbeat absent` alert keys off.

### As a GitHub Action

See [action.yml](action.yml). Optional `config-dir` input, default `actions/pipeline-manager`.
The composite Action exposes `list-fleet` for consumers embedding fleet discovery in their own
workflows; the hourly monitor above invokes the `run` orchestrator directly rather than through
the Action.

## Testing

Snapshot tests: fixture configs in [fixtures/](fixtures/) go in, jurisdiction records in
[__snapshots__/](__snapshots__/) come out. Each subdirectory of
[fixtures-invalid/](fixtures-invalid/) is a broken config whose error message is
snapshotted; the render fails if any of them exits 0. The render also validates every
record against the schema and smoke-tests the real `../pipeline-manager` config.

The metrics payload is snapshot-tested the same way: fixed poller records in
[fixtures/poller-records.jsonl](fixtures/poller-records.jsonl) (success, failure, a
never-completed workflow, a workflow name needing tag escaping, an unreachable repo)
render byte-identically to
[__snapshots__/metrics-payload.txt](__snapshots__/metrics-payload.txt) via
`collect --dry-run`, timestamped from the fixture's pinned `polled_at`. The render also
validates every poller record (fixture and fake-fetcher output) against
`fleet-poller-record.schema.json`, asserts the poller's never-fatal contract and the
fatal unknown-base-template check offline (plus: active runs never mask the last
completed conclusion, flaked `status=success` pages fall back to the unfiltered
listing, workflow names are percent-encoded, an empty repo's 409 is null not error),
asserts `collect`'s exit contract from all sides (1 on any poll error, 0 on a clean
sweep with an identical payload, loud failure on an empty payload in push and
dry-run modes alike, `--timestamp` override), asserts the `run` orchestrator's
distinct contract (a heartbeat-encoder unit check and a shipper-resilience unit
check — an un-encodable record is skipped while the rest of the sweep still ships —
plus: a partial-fail sweep exits 0 shipping metrics + heartbeat, a clean sweep
carries a zero-error heartbeat, an all-errored sweep still exits 0 with the
heartbeat alone, a sweep with one un-encodable repo still exits 0 and ships the
good repos' metrics + heartbeat, and an outright push failure — missing credentials
or a rejected key/HTTP 401 — exits nonzero so the workflow shows red), locks
`live-check`'s expected-series
accounting (its query-back proof requires every series this payload shipped, per
metric, and skips metrics the payload legitimately omits), locks the HTTP retry
policy (4xx fail-fast, rate-limited 403 retries like
429, exhausted-quota fail-fast, integer `Retry-After` honored, HTTP-date form falls
back, 5xx backoff, no final-attempt sleep) and the push wire format (URL, verb,
Basic auth, Content-Type, body) with a fake `urlopen` and injected sleep, checks the
real-fleet API budget and that every real-fleet base template has a `DATA_PATHS`
entry, and locks `live-check`'s credential-free skip path. The real push-and-query
proof is opt-in — `FLEET_MONITOR_LIVE_CHECK=1 ./render-snapshots.sh` on a
credentialed machine — so a bare render stays offline, deterministic, and
side-effect-free. The poller's happy path is deliberately untested beyond that — it
is a pass-through against a live API.

The logs leg is snapshot-tested the same way. Committed fixture archives under
[fixtures/log-runs/](fixtures/log-runs/) (a failed run and a successful one) render
byte-identically to [__snapshots__/logs-payload.json](__snapshots__/logs-payload.json)
via `collect --logs-only --dry-run`, pinned by `--timestamp`. (Dry-run prints the
streams as one combined payload; a real push sends one payload per workflow — same
streams either way, since Loki derives stream identity from labels, not request
boundaries.) Around that, offline
unit checks lock: the Loki shipper (labeled batches → deterministic Loki JSON, labels
capped at org/state/workflow/outcome, run id in structured metadata not labels, an
un-encodable batch skipped); the watermark store (missing/empty file reads as `{}`,
writes round-trip); the harvester (archive unpack ignoring step folders, the RFC 3339
line-timestamp parse including a fractional part, `##[group]`/`##[endgroup]` noise
dropped, the volume policy — full logs for a failure, a 100-line tail for a success —
the per-repo/workflow watermark advancing only across contiguous shipped runs so an
in-progress run or a failed archive fetch is retried not skipped, the cold-start 24 h
look-back, and per-repo error isolation); the Loki push wire format (URL, POST, Basic
auth, `application/json`, missing-env guard) with a fake `urlopen`; the CLI's
end-to-end idempotency (a re-run of the same window ships nothing) and recovery (a
deleted watermark ships the recent window, not the full history) driven in-process
with a fake push; per-workflow push isolation (one workflow's failed push exits
nonzero but holds only its own watermark — the rest ship, save, and only the failed
one re-ships next sweep); `collect --logs-only`'s exit contract (harvest errors exit
1; a malformed config is a clean CLI error); a corrupt watermark file reading as
empty (bounded re-ship, never an hourly-recurring crash); run-listing pagination
(stops at the look-back boundary anchored to the harvest `now`, short pages, the
page cap, and unparseable timestamps never faking oldness); the log-fixture
jurisdictions validating against `fleet-record.schema.json`; job identity and the
original `event_time` pinned in structured metadata while entries carry
collection-time index stamps; that `run` wires the logs leg only when a log source
is present; `probe-loki`'s credential-free skip path, its bad-key exit, and its
query-back detecting a silently-discarded (204-but-dropped) age against a fake
Loki. The real ingest-window probe runs only with `GRAFANA_LOGS_*` set.

The dashboard has no snapshot file because the committed JSON is the snapshot: the render
re-renders it from `dashboard.py` into a temporary file and fails on any drift from the
committed `dashboards/fleet-overview.json` (it never rewrites the committed copy — that is
`main.py dashboard --out …`). Note that this one artifact lives outside `__snapshots__/`,
so it is guarded by that diff rather than by the repo-wide `verify-snapshots.sh` gate.
Around that, offline checks lock what the panels actually promise — every datasource
reference is a variable and never a stack UID, `id` is null and the uid stable (so a fresh
stack imports rather than collides), panel ids are unique, the Scrapers grid precedes the
Formatters grid and each pins its own workflow, a tile is labelled `{{state}}` alone at the
same text size as its value, paused tiles come from a second query overridden to a flat
never-red colour whose text still reports the last run, the freshness table is one
full-width panel whose query carries no paused filter and whose `paused` column survives
the organize step uncoloured by the staleness thresholds, it sorts in-session rows first
then worst staleness and turns red at exactly the 48 h alert
threshold, each freshness row
links to its jurisdiction's filtered view, the logs panel matches on all four stream
labels as regexes with log details on, every metric panel wraps its selector in
`last_over_time` over a window with real headroom on the *measured* worst sweep gap, not on
the cron expression (checked over the metric panels derived from the board rather than a
hand-written list), the datasource pickers default to this stack, the freshness row link is
an absolute path setting the single jurisdiction picker and carrying the time range, the
rendered logs selector keeps at least one matcher
that is not empty-compatible, each picker carries its own
datasource's query dialect and an explicit `allValue: ".+"`, the pickers are label-driven,
multi-select, and URL-synced, and the encoding is
deterministic. `check-dashboard` is locked the same way as the other live paths: its
credential-free skip, and against a fake Grafana its wire shape (dashboards API endpoint,
bearer auth, overwrite-by-uid, read-back by uid), its loud failure on a rejected import,
its refusal to pass a push that returns 200 but reads back hollow, and its refusal to pass
an import that lost a template variable or kept one in name only (stripped of its
all-value, or repointed at the wrong datasource — a picker that resolves to nothing blanks
every panel filtering on it). The real import is
opt-in — `FLEET_MONITOR_DASHBOARD_CHECK=1 ./render-snapshots.sh` — so a bare render never
writes into anyone's stack.

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
