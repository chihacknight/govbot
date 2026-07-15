# Fleet Monitor PRD: Observability for the GovBot Pipeline

## Problem Statement

GovBot's pipeline runs as scheduled GitHub Actions jobs spread across roughly 114 public repos in two GitHub orgs. When one breaks, nothing tells anyone. A state's scraper can fail outright, or keep running green while committing no new data, for weeks before a human notices; the project's recent history includes scraper outages and a data-loss bug that were discovered late for this reason.

The signals that would reveal a problem already exist, but they're scattered: run results sit in each repo's Actions tab, freshness is a commit timestamp in each repo, and error details are files committed inside the data repos. Checking all of it means visiting over a hundred pages, so in practice nobody checks any of it. The maintainers are volunteers. The system has to tell them when something needs attention, and when it does, the evidence needs to be in one place.

## Solution

A single hourly GitHub Actions workflow in the monorepo (the fleet monitor) polls the GitHub API for every repo in the fleet, computes health signals, and pushes them to a free-tier Grafana Cloud stack: metrics to its Prometheus endpoint, run logs to Loki.

One Grafana dashboard shows the whole fleet: a per-jurisdiction status grid, a staleness table, and the logs of any run, searchable by state, workflow, and outcome. Alert rules notify a Slack channel and email when an active state's run fails, when an active state's data goes stale, or when the monitor itself stops reporting.

Everything the monitor reads is public, so it needs no credentials beyond the workflow's built-in token; the only secret in the design is the Grafana write key. Maintainers learn about failures within an hour or two instead of weeks, and triage happens in one browser tab.

## User Stories

1. As a project maintainer, I want a single dashboard showing the health of every jurisdiction's pipeline, so that I can check the whole fleet without visiting 114 repos.
2. As a project maintainer, I want a Slack message when an active state's scrape or format workflow fails, so that failures surface within hours instead of weeks.
3. As a project maintainer, I want the same alerts by email, so that people who don't watch Slack still find out.
4. As a project maintainer, I want an alert when an active state's data commits go stale even though its runs are green, so that silent no-data failures are caught.
5. As a project maintainer, I want paused (out-of-session) states excluded from alerting, so that expected dormancy never pages anyone.
6. As a project maintainer, I want staleness thresholds that tolerate one missed daily cycle, so that a single hiccup doesn't generate noise.
7. As a volunteer triaging a failure, I want the failed run's full logs available in Grafana, so that I can read the error without navigating GitHub.
8. As a volunteer triaging a failure, I want to filter logs by state, workflow, and outcome, so that I can isolate the evidence quickly.
9. As a volunteer triaging a failure, I want the tail of recent successful runs available, so that I can compare a failure against healthy output.
10. As a volunteer triaging a failure, I want to get from an alert to the affected state's dashboard view in one click, so that context is immediate.
11. As the observability engineer, I want the collector to run as an hourly workflow in the existing monorepo, so that no new servers or accounts have to be maintained.
12. As the observability engineer, I want a dead-man alert when the collector stops reporting, so that the monitoring system can't die silently the way the pipelines do.
13. As the observability engineer, I want the collector to read only public data using the workflow's built-in token, so that it needs no org-level permissions.
14. As the observability engineer, I want the Grafana write key to be the only secret, so that the ask to maintainers is a single repo secret.
15. As the observability engineer, I want to validate the whole stack from a fork against the real orgs' public data, so that maintainers only ever see a finished, working proposal.
16. As the observability engineer, I want a watermark so each run ships only data it hasn't shipped before, so that Loki isn't filled with duplicates and restarts recover cleanly.
17. As the observability engineer, I want metric cardinality and log volume budgeted against Grafana Cloud free-tier limits, so that the system stays at zero cost.
18. As a contributor, I want dashboards and alert rules committed to the repo, so that the Grafana setup is reproducible rather than hand-built.
19. As a contributor, I want the fleet-config reader covered by snapshot tests, so that the paused-state logic guarding against false alarms is locked down.
20. As a contributor, I want the log harvester testable offline from sample log archives, so that its filtering and timestamp handling can change safely.
21. As a contributor, I want shipper payloads covered by snapshot tests, so that a breaking change against the Grafana or Loki API shapes shows up in review.
22. As a contributor, I want the module to follow the repo's action conventions (runnable as a plain script, action metadata, committed snapshots), so that it reads like the rest of the codebase.
23. As a data consumer, I want a shareable freshness view per jurisdiction, so that I can check whether a state's data is current before building on it.
24. As a project maintainer, I want alert delivery extendable to GitHub issue creation later, so that alerts can become trackable work items without a redesign.
25. As a project maintainer, I want the monitor to be conservative in its GitHub API usage, so that it stays well inside rate limits and GitHub's acceptable-use terms.
26. As the observability engineer, I want collection to continue when an individual repo errors, so that one bad repo doesn't blank the metrics for the whole fleet.

## Implementation Decisions

**Placement and shape.** A new self-contained module in the monorepo's actions folder, tentatively `fleet-monitor`, written in Python (matching the format and extract modules). CLI-first: runnable locally with arguments, with action metadata so the hourly workflow can invoke it. The workflow runs in the monorepo on GitHub-hosted runners.

**Module decomposition.** Seven parts, each with a narrow interface:

- *Fleet config reader*: takes the pipeline-manager config files, returns a list of jurisdiction records (state, org, repo names, expected workflows, paused or active). Only this module knows the config format or the paused-template convention.
- *Fleet poller*: takes the jurisdiction list and a GitHub API client, returns plain records of latest run status per workflow and last-data-commit age per repo. All GitHub REST knowledge lives here. Failures on individual repos are recorded and skipped, not fatal.
- *Log harvester*: takes runs newer than a watermark, downloads and unpacks their log archives, and returns labeled batches of timestamped lines. Applies the volume policy: full logs for failed or cancelled runs, roughly the last hundred lines for successful runs, known-noise lines dropped. Timestamps come from the prefix GitHub puts on every log line.
- *Shippers*: two encoders that turn poller and harvester output into Grafana Cloud metric-push and Loki log-push payloads, plus one HTTP helper with retry. The payload shape is the tested interface.
- *Watermark store*: reads and writes the high-water mark (last collection time / last run seen per repo), backed by the Actions cache, with a bounded look-back fallback of one day when the cache is missing.
- *Orchestrator*: a thin main that wires the above together, emits the heartbeat metric, and exits nonzero when a run fails outright, so the workflow itself shows red. The hourly workflow definition lives beside it.
- *Grafana assets*: the dashboard definition and alert rules, committed to the repo so the Grafana side can be rebuilt from scratch.

**Signals.** Per repo and workflow: whether the latest run succeeded, and hours since the last successful run. Per repo: hours since the last commit touching data paths (raw scrape output in scraper repos, the formatted tree in data repos). Every series carries a paused label derived from the scrape config. One heartbeat metric for the collector itself. Estimated series count is in the high hundreds against a free-tier limit of ten thousand.

**Log labels.** Loki labels are limited to org, state, workflow, and outcome. Run and job identifiers travel in the log line or structured metadata, not labels, to keep cardinality flat.

**Transport.** Direct HTTP from Python to the Grafana Cloud push endpoints. Vector was considered and deferred: in an hourly batch job its buffering and backpressure add little, and a one-shot Vector step can replace the shippers later if parsing and routing rules grow. A continuously running collector chained across VMs was considered and rejected: it inverts the self-healing property of cron and runs against GitHub's acceptable-use expectations for hosted runners.

**Alerting.** Three rules at launch: latest run failed for an active state; data-commit age for an active state exceeds 48 hours; collector heartbeat absent for 3 hours. Contact points are a Slack webhook and email. GitHub issue creation is a later addition via webhook.

**Cadence.** Hourly. The pipelines are daily, so an hour of detection latency is ample, and hourly collection keeps API usage in the low hundreds of requests per run.

**Authentication.** The workflow's default token for all GitHub reads (public data only). One repository secret for the Grafana Cloud write key.

**Testing.** Snapshot tests, matching the repo convention, for the fleet config reader (fixture configs in, jurisdiction list out), the log harvester (sample log archives in, labeled batches out), and the shippers (fixed records in, exact payloads out). The poller is deliberately untested at launch; it is pass-through logic against a live API, and recorded-fixture tests for it can be added if it grows behavior.

**Rollout.** Build and validate in a fork first, running against the real orgs' public data with a personal Grafana Cloud account. The ask to maintainers is one reviewed PR plus one repo secret.

## Out of Scope

- Self-hosted runner health monitoring (planned as the next iteration; the runner's online/offline status is one API call, but it needs its own alert semantics).
- Data-quality metrics from the error files and orphan tracking committed in the data repos.
- Automated GitHub issue creation from alerts.
- Shipping full logs for successful runs.
- History beyond the free tier's retention window; GitHub's own 90-day run-log retention is the archive for now.
- Any change to the existing scrape, format, or extract workflows and templates.
- Monitoring of the consumer side (the govbot CLI, the docs dashboard, downstream bots).
- Fixing the stale org reference in the extract-text template; it was noticed during this design and should be raised with maintainers separately.

## Further Notes

Grafana Cloud free-tier figures assumed here (10,000 metric series, 50 GB/month log ingest, 14-day retention) should be re-verified when the account is created; they change occasionally.

Loki rejects log entries older than its ingest window. An hourly collector shipping logs from runs that finished hours earlier can trip this, so it belongs on the prototype's test list before anything else is built on top.

Out-of-session states are dormant on purpose, and alerting on their staleness would train everyone to ignore the channel. This is why every metric series carries the paused label, why alert rules filter on it rather than on age alone, and why the config reader that derives it gets tests first.

If the project later wants trends beyond the retention window, the collector could additionally commit a small daily status file to the repo, in keeping with the project's git-as-database style.
