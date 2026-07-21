# Task 0006: Alert rules + contact points

**Branch**: `feature/grafana-alerts`
**Depends on**: 0003, 0005
**Source**: plans/fleet-monitor-prd.md · **User stories**: 2, 3, 4, 5, 6, 10, 12, 18, 24

## What to build

The notification slice, committed as code: three alert rules — an active state's latest run
failed; an active state's data-commit age exceeds 48 hours (tolerating one missed daily cycle);
the collector heartbeat absent for 3 hours (the dead-man switch) — delivered to a Slack channel
and email. Rules filter on the paused label so out-of-session states never page anyone. Each
alert links to the affected state's view in the 0005 dashboard so triage is one click away.
Delivery stays extendable to GitHub issue creation later (webhook contact point), without
building it now.

Demo: force a condition (or fire a test notification) and the alert lands in Slack and email with
a working link into the dashboard.

## AFK tasks

- [ ] Alert rules as committed provisioning files under the module's Grafana assets: run-failed
      (active only), staleness > 48 h (active only), heartbeat absent 3 h
- [ ] Contact points + notification policy as committed provisioning files: Slack webhook and
      email, webhook URL/address supplied at provision time, never committed
- [ ] Alert annotations carry a deep link to the dashboard filtered to the affected state
- [ ] Automated provisioning check: apply rules via the Grafana API and assert they load and
      evaluate without error (skipped when credentials are absent)
- [ ] Rule-logic tests where assertable offline: the paused-label filter and threshold values
      locked by snapshot/fixture (e.g. rendered rule JSON snapshots)
- [ ] README section: provisioning the rules and contact points into a fresh stack

## Human-in-the-loop tasks

- [ ] [decision] Which Slack workspace/channel gets the webhook, and which email address receives
      alerts (talk-it-through)
- [ ] [verify] A test notification arrives in the chosen Slack channel and inbox, and its
      dashboard link opens the right state's view — delivery lands in external human channels an
      automated check can't read

## Acceptance criteria

- [ ] All three rules provision from committed files into a fresh stack
- [ ] A paused state failing or going stale fires nothing; the same condition on an active state
      fires within the evaluation window
- [ ] Killing the collector (disable the workflow) fires the dead-man alert within ~3 h
- [ ] Alerts arrive in both Slack and email, each with a one-click link to the affected state's
      dashboard view
