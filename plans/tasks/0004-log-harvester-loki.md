# Task 0004: Log harvester + Loki shipper + watermark

**Branch**: `feature/log-harvester-loki`
**Depends on**: 0003
**Source**: plans/fleet-monitor-prd.md · **User stories**: 7, 8, 9, 16, 17, 20, 21

## What to build

The logs tracer bullet: each hourly run ships run logs it hasn't shipped before to Loki. A
watermark store (Actions cache, one-day look-back fallback when the cache is missing) tracks the
last run seen per repo; the harvester downloads and unpacks log archives for runs newer than the
watermark and returns labeled batches of timestamped lines under the volume policy (full logs for
failed/cancelled runs, ~last 100 lines for successful ones, known-noise lines dropped); a Loki
shipper pushes them with labels limited to org, state, workflow, outcome — run/job ids in the
line or structured metadata, never labels.

The PRD flags Loki's ingest window as the risk to retire first: an hourly collector ships logs
from runs that finished hours earlier, and Loki rejects entries older than its window. Probe that
before building on top.

Demo: a real failed run's full logs are searchable in Grafana by state, workflow, and outcome.

## AFK tasks

- [ ] Ingest-window probe first: push log entries with timestamps 1–24 h old to the Loki endpoint
      and record which ages are accepted; if old timestamps are rejected, adopt the fallback
      (ship at collection time, carry the original timestamp in the line/metadata) and document
      the decision in the module README
- [ ] Watermark store: read/write last-collection/last-run-seen per repo, backed by the Actions
      cache, with a bounded one-day look-back when the cache is missing; local file backend for
      dev
- [ ] Log harvester: download/unpack archives for runs newer than the watermark; parse the
      timestamp prefix GitHub puts on every line; apply the volume policy and noise filter;
      return labeled batches
- [ ] Loki shipper: encoder from labeled batches to Loki push payloads (labels: org, state,
      workflow, outcome only), reusing the 0002 HTTP helper
- [ ] Wire into the orchestrator behind the existing hourly workflow; re-running with an
      unchanged watermark ships nothing (idempotency)
- [ ] Snapshot tests: sample log archives committed as fixtures → labeled batches (harvester),
      and fixed batches → exact Loki payloads (shipper); all runnable offline
- [ ] Log-volume estimate documented against the 50 GB/month free-tier budget

## Acceptance criteria

- [ ] A failed run's full logs and a successful run's ~100-line tail are queryable in Grafana,
      filterable by state, workflow, and outcome
- [ ] Two consecutive collections of the same window ship no duplicate entries; a deleted
      watermark recovers via the one-day look-back without re-shipping the full history
- [ ] Harvester and shipper snapshot tests pass offline in CI
- [ ] Ingest-window behavior is probed and the chosen timestamp strategy is documented
