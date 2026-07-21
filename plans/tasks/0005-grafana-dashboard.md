# Task 0005: Grafana dashboard as code

**Branch**: `feature/grafana-dashboard`
**Depends on**: 0004
**Source**: plans/fleet-monitor-prd.md · **User stories**: 1, 8, 9, 18, 23

## What to build

The single fleet view, committed to the repo so the Grafana side is reproducible rather than
hand-built: one dashboard with a per-jurisdiction status grid, a staleness/freshness table
(shareable, per user story 23), and a logs panel over the Loki data filterable by state,
workflow, and outcome. Paused states are visually distinct, not hidden.

Demo: import the committed JSON into a fresh Grafana Cloud stack and the whole fleet renders from
live data with no hand edits.

## AFK tasks

- [ ] Dashboard JSON under `actions/fleet-monitor` (Grafana assets area): status grid keyed on the
      latest-run metric, staleness table on the data-commit-age metric, logs panel on Loki with
      state/workflow/outcome variables
- [ ] Datasource references parameterized (UID variables/inputs) so the JSON imports into any
      stack, not just the dev account
- [ ] Paused label surfaced in the grid and table (dimmed/grouped, excluded from red states)
- [ ] Automated import check: push the dashboard via the Grafana HTTP API and assert it loads
      without error (skipped when credentials are absent)
- [ ] README section: how to import/provision the dashboard into a fresh stack

## Human-in-the-loop tasks

- [ ] [verify] The rendered dashboard reads well — grid legible at 56 jurisdictions, staleness
      table sorted usefully, one-glance triage works — layout judgment is visual and can't be
      asserted by API checks

## Acceptance criteria

- [ ] Committed JSON imports into a fresh Grafana Cloud stack without manual edits
- [ ] Status grid and staleness table show every fleet repo; paused states visibly distinct
- [ ] Logs panel filters by state, workflow, and outcome; a failure's logs and a recent success's
      tail are both reachable from it
- [ ] Freshness view is linkable per jurisdiction
