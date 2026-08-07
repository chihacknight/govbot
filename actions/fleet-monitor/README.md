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
**Non-production fleets are skipped by default.** Discovery finds every fleet config, but
`--exclude-fleet` (default: `chn-openstates-test`) keeps some out of the sweep.
`chn-openstates-test` mirrors the files fleet against the `govbot-test` org to validate
changes before cutting the real repos over, and its own header says some locales "will fail
fast … expected, not alarming" — monitoring it would put permanent expected-red on the
board and page someone once alerting lands, the same reason paused jurisdictions are never
coloured red. It is also 56 repos × 2 workflows of API budget: including it takes an hourly
sweep to **~1,008 requests against the 1,000/hour `GITHUB_TOKEN` limit**, before any log
archive downloads. This is a default, not a law — `--exclude-fleet=` (empty) monitors
everything discovery finds — so the pipeline-manager configs stay the authority on what
*exists*, and this is only a visible, reversible statement about what is worth alerting on.

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
  runs, latest success) + 1 per repo for the data-path commit, plus the logs leg's
  1 run-listing request per workflow (paging up to 4 only when a page is full and still
  inside the 24 h window — page 1 suffices on a normal hourly sweep) and 1 archive download
  per *new* run, bounded by how many runs actually finished in the hour, typically a
  handful, since the watermark skips everything already shipped.

  Against the `GITHUB_TOKEN` limit of **1000 requests/hour**, and the sweep runs hourly, so
  one sweep must fit in one hour's budget. The monitored fleet — 56 scraper repos × 1
  workflow plus 56 data repos × 2 — costs **448 metrics + 168 log listings = 616/hour, 62%
  of the limit**. `render-snapshots.sh` asserts the whole sweep stays under 80%, leaving
  ~200 for archive downloads, and prints a notice past 60% so the next fleet or workflow
  doesn't arrive as a surprise. That check counts **both legs**: budgeting the metrics leg
  alone against a flat number understated a sweep and let the real cost cross the ceiling
  before anything complained. Including `chn-openstates-test` would put the sweep at
  ~1,008/hour — over the limit — which is the arithmetic behind excluding it above.
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
| `GRAFANA_DASHBOARD_URL` | stack base URL, `https://<stack>.grafana.net` (`check-dashboard`; also the optional deep-link base for `provision-alerts`, which defaults to `GRAFANA_ALERTS_URL`) |
| `GRAFANA_DASHBOARD_KEY` | service-account token with dashboard write (`check-dashboard` only; **bearer**-authed, unlike the Basic-auth push endpoints) |
| `GRAFANA_ALERTS_URL` | stack base URL, `https://<stack>.grafana.net` (`provision-alerts` only) |
| `GRAFANA_ALERTS_KEY` | service-account token with **alerting write** and datasource read (`provision-alerts` only; bearer-authed) |
| `SLACK_WEBHOOK_URL` | Slack incoming-webhook URL for the contact point (`provision-alerts` only; never committed) |
| `ALERT_EMAIL` | address the email integration delivers to (`provision-alerts` only; never committed) |
| `GRAFANA_METRICS_DATASOURCE_UID` | *optional*: pins the datasource the rules query. Discovered from the stack when unset; **required** when a stack has more than one Prometheus datasource |

## Dashboard: the fleet view, as code

One dashboard answers the whole question — anything red, anything stale, and what did it
say — and it is committed rather than hand-built, so the Grafana side is reproducible:

- **[dashboard.py](dashboard.py)** builds it as data; **[dashboards/fleet-overview.json](dashboards/fleet-overview.json)**
  is that build, rendered and committed. The JSON is what you import; the module is what
  you review. The render script re-renders the dashboard and fails if the committed copy
  has drifted — it does not rewrite the file, so regenerate it yourself with
  `main.py dashboard --out dashboards/fleet-overview.json` after editing the builder. The
  file in the repo can never quietly stop matching the code that explains it.
- **Scrapers, freshness, logs — then a grid per remaining workflow.** The scrape is the
  fleet's entry point and everything downstream depends on it, so its status grid is pinned
  to the top. Below it, one full-width freshness table on
  `fleet_repo_data_commit_age_hours` and a logs panel on the Loki streams; below those, one
  status grid per *other* workflow. The table turns red above 48 h — the same number the
  staleness alert fires on, kept in one place so the dashboard and the alert cannot
  disagree.
- **Only the scrape workflow is named in the JSON.** The rest of the grids are Grafana
  panel repeats over a variable fed by the metric's own `workflow` label, so a workflow
  added to the pipeline-manager config gets a grid on its next sweep with no dashboard
  edit. This is not hypothetical: `extract-text.yml` was added to the production files
  fleet upstream, and the earlier hardcoded Scrapers/Formatters pair would have left it
  silently unmonitored — no tile, no alert, and no offline check that could have caught it.
- **A tile says only its state.** 112 tiles in a single panel shrank the text past reading;
  56 apiece with the workflow carried by the panel title leaves the two-letter jurisdiction
  code rendered as large as the OK/FAILING beside it. (The code renders as the metric label
  stores it, lower-case — Grafana has no way to upper-case a series name without hardcoding
  all 56 jurisdictions into the JSON, which would cost the property that a new jurisdiction
  appears on its own.)
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
  would false-fire on a routine 3.6h gap, which is why the dead-man rule below waits six
  hours instead. Thresholds here come from this measurement, never from the cron
  expression.
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

## Alerting: rules and contact points, as code

Four rules, committed the same way the dashboard is — built as data by
[alerting.py](alerting.py), rendered into [alerting/](alerting/), applied by
`provision-alerts`:

- **An active jurisdiction's latest run failed** (`fleet_workflow_run_status < 1`), **an
  active jurisdiction's data is stale** (`fleet_repo_data_commit_age_hours > 48`), and
  **the collector itself has gone quiet** (`absent_over_time(fleet_collector_heartbeat_repos[6h])`).
  The first two carry the jurisdiction; the third is the dead-man switch that stops the
  other two from being quietly meaningless when nothing is being measured at all.
- **A fourth rule covers the gap the other three leave**: repos that reported freshness
  yesterday and have gone quiet. `noDataState: OK` is right for a sweep that didn't happen
  and wrong for a repo that silently stopped reporting, and per-series the two are
  indistinguishable — so the rule counts instead, comparing the fleet against **itself a
  day ago**. This is not hypothetical: a repo with **zero commits on its data path** is the
  most stale a repo can be, and it emits nothing at all (`fleet_poller` returns None on
  GitHub's 409 "Git Repository is empty", and the shipper only emits an age when there is
  one). Without this rule that repo is permanently green while its 46 neighbours report
  normally.

  Three details in that expression are each load-bearing. It counts **repos, not series** —
  `paused` is a label, so a jurisdiction going out of session starts a second series for
  the same repo, and counting series would read the legislative calendar turning over as
  coverage appearing and vanishing in batches. It floors the subtraction with **`or
  vector(0)`** — a count over no series is an *empty* vector, not zero, and an empty
  operand makes the whole expression empty, which `noDataState` resolves to OK; without the
  floor the rule would be silent in exactly its worst case, every repo gone at once. And it
  compares against the fleet's own past rather than the collector's heartbeat count (which
  is what this replaced): the heartbeat counts paused repos too, so a paused repo reporting
  nothing would have paged, breaking the rule the whole design turns on.

  A repo deliberately removed from the pipeline-manager config also lands here, and clears
  on its own within a day. **So does a total outage, and that resolution is not recovery**:
  once nothing has reported for a full day, both sides of the comparison are empty and the
  alert goes quiet with the fleet still dark. The heartbeat rule covers a dead collector;
  this one cannot also cover a live collector that has seen nothing for a day. Read a
  resolution of this rule against the board, not on its own — the rule description says so
  too, since that is where someone reads it at 3am.
- **Paused jurisdictions never page for a failed run or stale data.** Both jurisdiction rules filter `paused="false"` in
  the query, so an out-of-session state whose scrape fails doesn't reach the notification
  policy, let alone a phone. This is the same rule the dashboard renders as a dimmed tile,
  and the reason the metric carries the label at all.
- **The dead-man waits six hours, not the three the PRD asked for.** Three is below the
  *measured* worst sweep gap of 3.6 h (see the dashboard section above), so a 3 h rule
  pages on an ordinary late run — the fastest way to teach everyone to ignore it. Six is
  ~1.7× the observed worst case and reuses the dashboard's look-back, so board and alert
  can't drift apart. The cost is real and worth stating: a collector that dies right after
  a sweep goes unreported for up to six hours. Against a 48 h staleness rule, that is
  affordable.
- **The 48 h number exists once.** `alerting.py` imports `STALE_HOURS` from `dashboard.py`
  rather than restating it, so the table's red line and the alert's threshold are the same
  number by construction, not by anyone remembering to change both.
- **Rules evaluate every 5 minutes with a 10-minute pending period, and no-data resolves to
  OK.** The facts underneath change hourly at most, so a long pending period would only
  delay real alerts. A missing series means the collector didn't ship — which the heartbeat
  rule reports once, rather than 47 per-state pages saying the same thing worse. An
  execution error is *not* treated as no-data: a datasource that has gone away shows up as
  a broken rule.
- **One contact point, two integrations: Slack and email.** Adding the PRD's GitHub-issue
  delivery later is a third integration on the same point, not a second route to keep in
  step. Resolved notifications are on, because a channel that only ever fills with red and
  never visibly clears is a channel people mute.
- **Grouped by rule, not by jurisdiction.** 47 jurisdictions share the same scrapers, so
  one upstream break trips the run-failed rule for dozens at once. Grouped by `alertname`
  that is one message listing every affected state; grouped by state it is forty messages
  in a minute. `group_wait` 30 s, `group_interval` 5 m, `repeat_interval` 24 h — still
  broken tomorrow is worth saying again, still broken in an hour is not.
- **Every alert links into the board, filtered to the jurisdiction that fired it.** The
  link is absolute and carries a pinned time range: a notification is read in Slack or an
  inbox, where the dashboard's own relative `/d/…` row links resolve against the wrong
  host, and `${__url_time_range}` has nothing to expand it. The two fleet-wide alerts — heartbeat and coverage — link to
  the unfiltered board: their series carry no labels, so a `var-state=` there would filter
  to nothing on exactly the alerts that fire when everything else has gone quiet.
- **Nothing stack-specific and no credential is committed.** The datasource uid, the stack
  URL, the webhook, and the address are `$PLACEHOLDERS` resolved at provision time. A
  placeholder nobody supplies is a hard failure, never an empty string — Grafana accepts a
  contact point with a blank webhook URL, then accepts alerts routed to it and drops them,
  which looks exactly like a working alerting setup that nothing ever trips.

### Provisioning it into a fresh stack

```bash
export GRAFANA_ALERTS_URL=https://<stack>.grafana.net
export GRAFANA_ALERTS_KEY=<service-account token with alerting write>
export SLACK_WEBHOOK_URL=<Slack incoming webhook>
export ALERT_EMAIL=<address to notify>
pipenv run python main.py provision-alerts
```

It reads the committed files (not a fresh render — what you reviewed is what gets applied),
resolves their placeholders, creates the `Fleet Monitor` folder, applies the contact point,
replaces the notification policy, applies the whole rule group, and then **waits for the
stack to evaluate the rules**. That last step is the point: Grafana will accept a rule whose
datasource uid points at nothing, store it, and serve it back intact — the failure only
appears as `health: error` once evaluation runs, so a check that stops at the 200 is a
check that passes while nothing works. Missing credentials exit 0 with a skip notice.

What to know before you run it:

- **The stack is assumed dedicated, and the notification policy is replaced whole.** The
  committed [fleet-notification-policy.yaml](alerting/fleet-notification-policy.yaml) is a
  real Grafana `policies:` document carrying the *entire* tree: the fleet's contact point is
  the root receiver, so every alert the stack produces — including a stray one — lands in
  Slack and email as a visible surprise rather than vanishing down a default receiver
  nobody reads. There are no matchers and no child routes, which is what deletes the whole
  category of tree-merging bugs a shared stack would invite. All three files are ordinary
  provisioning documents and can be dropped into a self-hosted provisioning directory
  as-is — on a stack dedicated to the fleet monitor, which is the standing assumption.
- **That assumption is checked on every run, not trusted.** Before writing anything,
  provisioning reads the stack's policy tree and only proceeds over a tree it recognises:
  its own (root receiver `fleet-monitor`), or a fresh stack's untouched default
  (`grafana-default-email` with no child routes). Anything else — a renamed root, routes
  somebody added under the default — is a hard stop that names what it found, with no
  `--force` to pave over it: if the stack really is dedicated, reset its notification
  policy to the default in the UI and re-run; if it isn't, this command is pointed at the
  wrong stack.
- **Everything is applied with `X-Disable-Provenance`,** so the rules stay editable in the
  UI. Without it Grafana marks API-provisioned resources read-only, and the first
  maintainer who tries to silence a rule meets a greyed-out form with no explanation. The
  trade-off is real: nothing then stops an Editor on the stack from repointing the Slack
  webhook or rewiring the policy, and there is no scheduled re-apply, so that drift
  persists until someone re-runs the command. Re-running is the remedy, and it is cheap:
  the committed tree wins, and any UI edit it resets is named in the output rather than
  silently erased — the lasting place for a change is `alerting.py`, not the browser.
- **The policy tree is read, and the notifications written, before the rules land.** The
  read is the only one that can refuse, and the notification writes (contact point, then
  policy) are the ones that can still fail after every read has passed — Grafana 11 splits
  `alert.rules:write` from `alert.notifications:write`, so a token holding only the first
  passes every check and then 403s at the first of them. Rules-first would leave them
  enabled and delivering to whatever receiver was there, reproduced on every retry.
  Notifications-first fails with a tree routing alerts that do not exist yet, which is
  inert. The contact point goes in ahead of the policy because Grafana refuses a root
  receiver that does not exist.
- **A policy tree without a root receiver is never overwritten** — including an empty one.
  Every Grafana ships a default root receiver, so an empty or unfamiliar 200 body is far
  likelier to be a proxy, a gateway stub, or a build we don't recognise than a stack that
  genuinely has no policy. Adopting it would overwrite a tree nobody ever read.
- **The prune only deletes integrations this module created** (`fleet-monitor-` uids).
  Anything else on the contact point was added through the UI, which is exactly what
  `X-Disable-Provenance` exists to allow; deleting it would make this command undo the
  editing that header is for.
- **`GRAFANA_ALERTS_URL` must be a bare https origin** (plain http is allowed only for a
  loopback host). Every request carries a bearer token, and the contact-point body carries
  the resolved webhook URL, itself a credential for posting to that channel. Credentials in
  the URL are refused too — every failed-request message embeds the URL it failed on, so one
  404 would put the token in a CI log — as are a query, a fragment, and a path prefix, which
  would 404 every GET and make a populated stack read as empty. `SLACK_WEBHOOK_URL` must be
  https too: a plain-http hook has Grafana re-POST the hook path itself in cleartext on every
  alert, from its own egress where nobody is watching. `GRAFANA_DASHBOARD_URL` gets the same
  checks **bar the path prefix**, which a reverse-proxied Grafana needs for its links to
  resolve and which is kept rather than refused; it is never contacted, so a wrong value
  provisions cleanly and misdirects on-call staff indefinitely.

One trust assumption worth stating. The deep link's state is `{{ urlquery $labels.state }}`,
so a value carrying `&` or `#` cannot append or truncate query parameters. The Slack summary
still interpolates `{{ $labels.workflow }}` unescaped, and Grafana renders Slack messages as
mrkdwn — so a workflow name of `<https://evil.example|dashboard>` would become a clickable
link in an alert the on-call trusts. Both labels come from the project's own committed fleet
config today, so this is a boundary rather than a hole; if workflow names ever arrive from
somewhere less controlled, strip mrkdwn punctuation at the shipper.

Re-running is safe and idempotent: the rule group is one PUT keyed by folder and group
name (so a rule deleted from the committed file actually disappears instead of lingering as
an orphan), and the integrations are keyed by stable uids — including removal, so an
integration dropped from the committed file is deleted from the stack rather than left
delivering to an address the repo no longer mentions.

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

# Print the alerting YAML, or regenerate the committed copies after editing
# alerting.py (the render script fails if the two have drifted):
pipenv run python main.py alerts
pipenv run python main.py alerts --out-dir alerting

# Apply the committed rules, contact point, and notification policy to a real
# stack, then wait
# for it to evaluate them (needs GRAFANA_ALERTS_URL/KEY + SLACK_WEBHOOK_URL +
# ALERT_EMAIL; exits 0 with a notice when they're absent):
pipenv run python main.py provision-alerts

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
stack imports rather than collides), panel ids are unique, the Scrapers grid is first and
pins the scrape workflow while every other grid is a panel repeat over a variable that
excludes it (so no workflow list can fall behind the config) and sits after the logs, a
tile is labelled `{{state}}` alone at the same text size as its value, paused tiles come from a second query overridden to a flat
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

The alerting artifacts are guarded the same way, and for the same reason: the committed
`alerting/*.yaml` are the snapshot, re-rendered from `alerting.py` into a temporary
directory and diffed, never rewritten in place. Around that, offline checks lock what the
rules promise — both jurisdiction rules filter `paused="false"` so an out-of-session state
cannot page, the thresholds are explicit expression nodes rather than numbers buried in
PromQL, the staleness number is imported from `dashboard.py` rather than restated, the
dead-man window has real headroom on the *measured* worst sweep gap (asserted against the
measurement, not against the window constant, so it cannot shrink back to the PRD's 3 h and
stay green), rules evaluate on a 5 m interval with a 10 m pending period, no-data resolves
to OK while an execution error does not, every alert carries an absolute state-filtered
dashboard link with a pinned time range and no `var-org` while the label-less heartbeat
rule carries no `var-state` at all, Slack and email are two integrations on one contact
point with resolved notifications on, the policy groups by `alertname` alone, the policy
document is a real Grafana `policies:` document carrying the whole tree of a dedicated
stack — root receiver `fleet-monitor`, no matchers, no child routes — rendering is
deterministic,
the coverage rule stands down while the dead-man is firing (a dead collector empties its
short window at the same instant, and `or vector(0)` would otherwise report the whole fleet
as having stopped reporting — two Slack messages for one outage, the louder one wrong about
the cause), and the four placeholders are exactly the four the provisioner resolves. Two of those
assertions are worth naming because the obvious version of each proves nothing. The
staleness threshold is checked by *parsing `alerting.py`* and requiring that it imports
`STALE_HOURS` and never binds it — comparing the built rule against the constant passes
just as happily when the module restates its own 48, and an identity check doesn't help
either, since CPython interns small ints. And the committed contact point is checked
*positively*, requiring every credential-bearing setting to still match
`^\$[A-Z][A-Z0-9_]*$`; the host-and-TLD blacklist this replaced missed `.gov`, `.io`, any
upper-case address, and every non-Slack webhook, which is how a weak check becomes a reason
not to look.

`provision-alerts` is locked like the other live paths, every scenario driven through the
CLI with `--deadline-seconds 0` so the suite never waits on a clock. Against a fake Grafana
it discovers the datasource uid, prefers an explicit one, refuses to guess between two
Prometheus datasources, applies **the file on disk** rather than a fresh render (proven
with a sentinel only present in a doctored copy), sends one idempotent rule-group PUT with
the interval in seconds, carries bearer auth and `X-Disable-Provenance` on every write,
ships no unresolved placeholder while leaving Grafana's own `{{ $labels.* }}` templating
untouched, creates the integrations once, updates them in place thereafter and deletes the
ones dropped from the file while leaving another contact point's receivers alone, replaces
the notification policy **whole** — adopting a fresh stack's untouched default, overwriting
its own previous tree with any UI drift named in the output, and hard-stopping before a
single write on any tree it does not recognise — and — the assertion the
whole check exists for — waits for an evaluation *newer than the one the stack had before
this run wrote*: a rule the stack has merely stored (`health: unknown`, or `ok` with a
zeroed `lastEvaluation`), a pass inherited from a previous run, and a stale failure from
the configuration this run just replaced are all refused, while the same failure re-recorded
after the write still fails the run. The baseline is read from the stack's own ruler API
rather than compared against this host's clock: a comparison across two machines needs a
skew tolerance, and any tolerance wide enough for a laptop a few minutes fast is also wide
enough to accept the evaluation that ran just *before* the write — the previous rule
definitions, which is the exact false pass the check exists to prevent. It also asserts the
deep link *resolves* to an absolute URL on the stack (an empty `GRAFANA_DASHBOARD_URL`
falls back rather than producing a relative link, and a trailing slash doesn't double). It also refuses before writing anything when the policy tree
can't be read, can't be interpreted, or isn't its to replace, so a refusal never strands
enabled, unrouted rules;
provisions a credential carrying a YAML metacharacter without a parse error; rejects a
non-https stack URL before sending a request; applies every group in the file rather than
the first; and never issues a DELETE for a receiver the API returned without a uid. Its
credential-free skip touches the stack not at all. The real provisioning run is opt-in —
`FLEET_MONITOR_ALERT_CHECK=1 ./render-snapshots.sh` on a credentialed machine — because
idempotent is not side-effect-free: it writes a live contact point and policy, and the next
evaluation can deliver to a real Slack channel.

```bash
../../scripts/before-snapshots.sh __snapshots__
./render-snapshots.sh
../../scripts/verify-snapshots.sh __snapshots__
```
