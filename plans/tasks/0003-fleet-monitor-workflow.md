# Task 0003: Hourly workflow, orchestrator + heartbeat

**Branch**: `feature/fleet-monitor-workflow`
**Depends on**: 0002
**Source**: plans/fleet-monitor-prd.md · **User stories**: 11, 12 (emit side), 14, 15

## What to build

Make collection unattended: a thin orchestrator main that wires config reader → poller → metrics
shipper, emits a collector heartbeat metric each run, and exits nonzero when a run fails outright
so the workflow itself shows red; plus the hourly workflow definition in this monorepo that
invokes it. The Grafana write key is the single repository secret (`github.token` covers all
GitHub reads).

Demo: the workflow runs hourly in a fork with one secret set, and fleet metrics plus the
heartbeat update in Grafana without anyone touching it.

## AFK tasks

- [ ] Orchestrator entry point wiring config reader, poller, and metrics shipper; heartbeat
      metric emitted on every run; nonzero exit on outright failure (partial per-repo failures
      stay zero-exit per 0002)
- [ ] Hourly workflow file (`cron: "0 * * * *"` + `workflow_dispatch`) following the
      `check-sessions.yml` pattern: setup-python, pipenv install, run the CLI; Grafana key from
      `secrets`, GitHub reads from the default token with read-only permissions
- [ ] Workflow-level guard so a hung run can't overlap the next hour (timeout + concurrency group)
- [ ] Snapshot/unit coverage for the orchestrator's exit-code behavior (all-fail vs. partial-fail
      vs. clean)
- [ ] Docs: README section covering fork setup — the one secret to set, how to enable the workflow

## Human-in-the-loop tasks

- [ ] [verify] After enabling in a fork with the secret set, at least two consecutive scheduled
      runs complete and the heartbeat advances in Grafana — depends on GitHub's cron scheduler
      firing over multiple hours, which can't be compressed into an automated check

## Acceptance criteria

- [ ] `workflow_dispatch` run in a fork completes green and pushes metrics + heartbeat
- [ ] Scheduled runs fire hourly without intervention; heartbeat timestamps in Grafana advance
- [ ] A forced total failure (e.g. bad Grafana key) exits nonzero and the workflow run shows red
- [ ] The only secret referenced anywhere is the Grafana write key
