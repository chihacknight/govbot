"""Build the fleet's alert rules, contact point, and notification route as data.

The committed artifacts live under ``alerting/``; this module is what produces
them (``main.py alerts``), so the rules are reviewable as code and regenerating
them is a diff rather than an export from somebody's browser — the same bargain
``dashboard.py`` makes for the board.

Thresholds are imported from ``dashboard`` rather than restated here. The
dashboard's freshness table turns red on the same number the staleness rule
fires on, and the only way to keep that true is to have one number.
"""

import re

import yaml

from dashboard import DASHBOARD_UID, LOOKBACK, STALE_HOURS

# Stable across every stack these are provisioned into: re-applying updates the
# same rules instead of littering duplicates, which is the whole reason the
# provisioning API takes a uid at all.
RUN_FAILED_UID = "fleet-run-failed"
STALE_UID = "fleet-data-stale"
HEARTBEAT_UID = "fleet-collector-dead"
COVERAGE_UID = "fleet-coverage-gap"

# Evaluated far more often than the data changes (the collector ships hourly at
# best), so a condition that clears is seen to clear quickly. The cost of a short
# interval is only query load, and these are four instant queries.
EVAL_INTERVAL = "5m"

# What absorbs evaluation-boundary flap. Deliberately short: the facts these
# rules read change hourly at most, and a failed nightly run stays failed until
# tomorrow's run — waiting longer delays every real alert to suppress noise that
# a longer wait wouldn't catch anyway.
PENDING_PERIOD = "10m"

# A jurisdiction's series simply not being there means the collector didn't ship
# it, and that is the heartbeat rule's job to report — once — rather than 47
# per-state pages all saying the same thing in a worse way.
NO_DATA_STATE = "OK"

# How many repos may stop reporting a data-commit age before the coverage rule
# fires. Zero needs no assumption about the fleet: the rule compares the fleet
# against *itself* a day ago, so a repo that has never reported is absent from
# both sides and a repo that stopped is present in only one.
#
# An earlier version compared against the collector's heartbeat count instead.
# That needed every polled repo to have a data-path commit in steady state — an
# assumption, not a measurement — and it paged on a paused repo, breaking the
# rule that out-of-session jurisdictions never alert.
COVERAGE_TOLERANCE = 0

# The comparison window for that regression. A day is long enough that a repo
# reporting normally is in both windows, and short enough that a repo removed
# from the config stops being mourned within one.
COVERAGE_BASELINE = "24h"

# The one label every fleet alert carries, and the only thing the fleet's
# notification route matches on. That is what lets the route be grafted under a
# stack's existing root policy instead of replacing it — see build_route().
ROUTE_LABEL = ("service", "fleet-monitor")

# The single destination every fleet alert routes to; its integrations are what
# fan out to Slack and email.
CONTACT_POINT = "fleet-monitor"

# Where the rules live in the stack's own folder tree. Its own folder, so a
# maintainer can see at a glance which rules came from here and delete them all
# by deleting one thing.
FOLDER = "Fleet Monitor"
FOLDER_UID = "fleet-monitor"

# The committed artifacts: what a maintainer reviews, and what `provision-alerts`
# reads back and applies.
ALERTING_DIR = "alerting"
RULES_FILE = "fleet-alert-rules.yaml"
CONTACT_POINTS_FILE = "fleet-contact-points.yaml"
POLICY_FILE = "fleet-notification-policy.yaml"

# The base URL of the stack whose UI serves the dashboard, resolved at provision
# time. A notification is read in Slack or an inbox, outside the stack entirely,
# so the link in it has to be absolute — the relative `/d/...` path the board's
# own row links use resolves against slack.com there.
DASHBOARD_BASE = "$GRAFANA_DASHBOARD_URL"

# Pinned, not inherited. `${__url_time_range}` is a dashboard macro with nothing
# to expand it in an annotation, and a link into "the last 24 hours from whenever
# you happen to click" shows a different window to each reader.
LINK_RANGE = "from=now-24h&to=now"


def _dashboard_link(state_filtered: bool) -> str:
    """A link into the board, filtered to the jurisdiction that alerted.

    ``state_filtered`` is False for the heartbeat rule: its series carries no
    labels, so `{{ $labels.state }}` would interpolate to nothing and produce
    `var-state=`, a filter matching zero jurisdictions — on the single alert that
    fires precisely when everything else has gone quiet.
    """
    url = f"{DASHBOARD_BASE}/d/{DASHBOARD_UID}?"
    if state_filtered:
        url += "var-state={{ $labels.state }}&"
    return url + LINK_RANGE


def _query(expr: str) -> dict:
    """The PromQL half of a rule: an instant query over the look-back window."""
    return {
        "refId": "A",
        "relativeTimeRange": {"from": 0, "to": 0},
        "datasourceUid": "$GRAFANA_METRICS_DATASOURCE_UID",
        "model": {
            "editorMode": "code",
            "expr": expr,
            "instant": True,
            "intervalMs": 1000,
            "maxDataPoints": 43200,
            "range": False,
            "refId": "A",
        },
    }


def _reduce() -> dict:
    """Collapse the query's frame to one value per series.

    Redundant on paper — every query here is instant, so it already returns one
    value per series — but it is the shape Grafana's own editor writes, and a
    threshold fed a raw query frame is the classic way a provisioned rule loads
    fine and then evaluates to an error.
    """
    return {
        "refId": "B",
        "relativeTimeRange": {"from": 0, "to": 0},
        "datasourceUid": "__expr__",
        "model": {
            "type": "reduce",
            "reducer": "last",
            "expression": "A",
            "refId": "B",
            "settings": {"mode": "dropNN"},
        },
    }


def _threshold(evaluator: dict) -> dict:
    """The comparison that decides firing, as its own node.

    Separate from the query on purpose: the number a rule fires on is the thing
    a reviewer most wants to see, and burying it inside a PromQL string (`… >
    48`) hides it from both the reader and the assertions.
    """
    return {
        "refId": "C",
        "relativeTimeRange": {"from": 0, "to": 0},
        "datasourceUid": "__expr__",
        "model": {
            "type": "threshold",
            "conditions": [{"evaluator": evaluator}],
            "expression": "B",
            "refId": "C",
        },
    }


def _rule(uid: str, title: str, expr: str, evaluator: dict, summary: str,
          description: str, state_filtered: bool = True) -> dict:
    return {
        "uid": uid,
        "title": title,
        "condition": "C",
        "data": [_query(expr), _reduce(), _threshold(evaluator)],
        "labels": dict([ROUTE_LABEL]),
        "annotations": {
            "summary": summary,
            "description": description,
            # A plain annotation rather than Grafana's `__dashboardUid__`: that
            # one is validated against the stack at provision time, so a rule
            # carrying it cannot be applied to a stack where the dashboard has
            # not been imported yet — which is every fresh stack, in the order
            # people actually do things.
            "dashboard": _dashboard_link(state_filtered),
        },
        "for": PENDING_PERIOD,
        "noDataState": NO_DATA_STATE,
        # Not NoData: a datasource that has gone away, or a query the stack can no
        # longer parse, must be visible as a broken rule rather than a healthy one.
        "execErrState": "Error",
        "isPaused": False,
    }


def build_rule_group() -> dict:
    """The launch rules, as one evaluation group."""
    return {
        "name": "fleet-monitor",
        "interval": EVAL_INTERVAL,
        "rules": [
            _rule(
                RUN_FAILED_UID,
                "Fleet run failed",
                f'last_over_time(fleet_workflow_run_status{{paused="false"}}[{LOOKBACK}])',
                # Status is 1 for a successful latest run and 0 otherwise, so the
                # rule fires below 1 rather than equal to 0 — an encoding that
                # keeps working if the metric ever gains a third value.
                {"type": "lt", "params": [1]},
                summary="{{ $labels.state }}: {{ $labels.workflow }} failed",
                description=(
                    "The latest completed run of this workflow did not succeed, and the "
                    "jurisdiction is in session. Open the run's log from the dashboard's "
                    "log panel to see why."
                ),
            ),
            _rule(
                STALE_UID,
                "Fleet data stale",
                "last_over_time("
                f'fleet_repo_data_commit_age_hours{{paused="false"}}[{LOOKBACK}])',
                {"type": "gt", "params": [STALE_HOURS]},
                summary=(
                    "{{ $labels.state }}: no data commit in over "
                    f"{STALE_HOURS}h"
                ),
                description=(
                    f"Nothing has landed in this repo's data path for {STALE_HOURS}h, which is "
                    "two missed daily cycles rather than one. The scrape may be succeeding and "
                    "producing nothing — check the run log, not just the run status."
                ),
            ),
            _rule(
                HEARTBEAT_UID,
                "Fleet collector heartbeat absent",
                f"absent_over_time(fleet_collector_heartbeat_repos[{LOOKBACK}])",
                # absent_over_time returns 1 only when the series is missing, and
                # nothing at all while the collector is alive.
                {"type": "gt", "params": [0]},
                summary=f"Fleet monitor has not reported in {LOOKBACK}",
                description=(
                    "The collector itself has stopped shipping, so every other rule here is "
                    "now blind rather than quiet — a green board means nothing until this "
                    "clears. Check the fleet-monitor workflow's recent runs."
                ),
                state_filtered=False,
            ),
            _rule(
                COVERAGE_UID,
                "Fleet coverage gap",
                # Repos reporting a day ago, minus repos reporting now. The fleet
                # is compared against itself, so nothing here has to know how big
                # it is, and a repo that has never reported is absent from both
                # sides rather than permanently accusing.
                #
                # `count by (state, org)` before counting, because the unit is
                # repos and not series: `paused` is a label, so a jurisdiction
                # going out of session starts a *second* series for the same
                # repo, and both are resolvable for a whole look-back. Counting
                # series would read that as coverage appearing and then
                # vanishing, in batches, every time the legislative calendar
                # turns over.
                #
                # `or vector(0)` because a count over no series at all is an
                # EMPTY vector, not zero — and an empty right-hand side makes the
                # whole subtraction empty, which noDataState resolves to OK. That
                # would silence this rule in exactly its worst case: every repo
                # gone at once, which is what a fleet-wide GitHub outage looks
                # like while the heartbeat keeps ticking.
                f"count(count by (state, org) "
                f"(last_over_time(fleet_repo_data_commit_age_hours[{COVERAGE_BASELINE}]))) - "
                f"(count(count by (state, org) "
                f"(last_over_time(fleet_repo_data_commit_age_hours[{LOOKBACK}]))) or vector(0))",
                {"type": "gt", "params": [COVERAGE_TOLERANCE]},
                summary="{{ $values.B }} repos stopped reporting a data-commit age",
                description=(
                    "These repos reported freshness within the last day and have now gone "
                    "quiet, so the staleness rule cannot see them: it resolves NoData to OK, "
                    "which is right for a sweep that didn't happen and wrong for a repo that "
                    "silently stopped reporting. A repo whose data path has no commits at all "
                    "— the most stale a repo can be — emits no series, and this is the only "
                    "rule that notices. Compare the freshness table against yesterday's row "
                    "count to find which. A repo deliberately removed from the "
                    "pipeline-manager config also lands here, and clears on its own within a "
                    "day."
                ),
                state_filtered=False,
            ),
        ],
    }


def build_contact_point() -> dict:
    """Slack and email as two integrations on one contact point.

    One point rather than two is what keeps a later addition — the PRD's GitHub
    issue creation, as a webhook — a third entry here instead of a second route
    that has to be kept in step with this one forever.

    The webhook URL and the address are placeholders resolved at provision time
    (see ``alerts_provision._resolve``): a committed webhook URL is a committed
    credential, and
    a committed address is somebody's inbox in a public repo.
    """
    return {
        "name": CONTACT_POINT,
        "receivers": [
            {
                "uid": "fleet-monitor-slack",
                "type": "slack",
                "settings": {"url": "$SLACK_WEBHOOK_URL"},
                # Resolved notifications matter as much as firing ones: a channel
                # that only ever fills with red and never visibly clears is a
                # channel people mute.
                "disableResolveMessage": False,
            },
            {
                "uid": "fleet-monitor-email",
                "type": "email",
                "settings": {"addresses": "$ALERT_EMAIL"},
                "disableResolveMessage": False,
            },
        ],
    }


def build_route() -> dict:
    """The fleet's branch of the notification tree — a child, never the root.

    Grafana's provisioning API has no concept of a partial policy: a PUT to
    ``/policies`` replaces the entire tree. Applying a root policy of our own to
    the maintainers' stack would silently redirect every alert they already run
    to this contact point, so ``provision-alerts`` grafts this route under
    whatever root is already there and leaves the rest untouched.

    ``group_by: [alertname]`` is the whole point of the route. 47 jurisdictions
    share the same scrapers, so one upstream break trips the run-failed rule for
    dozens at once; grouped by rule that is one message listing every affected
    state, and grouped by state it is forty messages in a minute.
    """
    return {
        "receiver": CONTACT_POINT,
        "object_matchers": [[ROUTE_LABEL[0], "=", ROUTE_LABEL[1]]],
        "group_by": ["alertname"],
        # Long enough to collect a fleet-wide break into one message, short
        # enough that a single failure isn't sitting in a buffer.
        "group_wait": "30s",
        "group_interval": "5m",
        # Still broken tomorrow is worth saying again; still broken in an hour is
        # not, and that is the difference between a reminder and a nag.
        "repeat_interval": "24h",
    }


RULES_HEADER = """\
# The fleet's launch alert rules, generated by alerting.py — edit that, not
# this, and regenerate with `main.py alerts --out-dir alerting`.
#
# $GRAFANA_METRICS_DATASOURCE_UID is resolved at provision time: a datasource uid
# belongs to one stack, and this file has to apply to any of them. Leave it as a
# placeholder. `{{ $labels.* }}` is Grafana's own templating and stays literal.
#
# Both jurisdiction rules filter paused="false": an out-of-session state whose
# scrape fails is the legislative calendar, not a fault, and it never pages.
"""

CONTACT_POINTS_HEADER = """\
# Where the fleet's alerts go, generated by alerting.py.
#
# $SLACK_WEBHOOK_URL and $ALERT_EMAIL are resolved at provision time and must
# stay placeholders here: a committed webhook URL is a committed credential, and
# a committed address is somebody's inbox in a public repo.
#
# Slack and email are two integrations on ONE contact point, so adding the PRD's
# GitHub-issue delivery later is a third entry here rather than a second route.
"""

POLICY_HEADER = """\
# The fleet's branch of the notification tree, generated by alerting.py.
#
# NOT a Grafana `policies:` document, on purpose. That key replaces the entire
# root notification tree, so dropping such a file into a stack's provisioning
# directory would silently redirect every alert that stack already runs to this
# contact point. `main.py provision-alerts` reads the bare route below and grafts
# it under whatever root policy is already there, matching on the service label
# every fleet rule carries.
"""


class UnresolvedPlaceholder(RuntimeError):
    """A committed placeholder nobody supplied a value for."""


# Upper-case only, which is exactly what separates a placeholder from Grafana's
# own `{{ $labels.state }}` templating living in the same file. The word boundary
# stops `$ALERT` from eating the front of `$ALERT_EMAIL`.
PLACEHOLDER = re.compile(r"\$([A-Z][A-Z0-9_]*)")


def placeholders(text: str) -> set:
    """Every placeholder name a rendered document expects."""
    return set(PLACEHOLDER.findall(text))


def _document(header: str, body: dict) -> str:
    """One committed YAML file: reasoning first, then the data.

    Key order is preserved rather than sorted — a rule reads top-down (what it
    is, what it queries, when it fires, what it says) and alphabetising that
    turns a reviewable document into a lookup table.
    """
    return header + yaml.safe_dump(
        body, sort_keys=False, default_flow_style=False, width=100, allow_unicode=True
    )


def render_documents() -> dict:
    """The committed alerting artifacts, keyed by file name."""
    return {
        RULES_FILE: _document(
            RULES_HEADER,
            {
                "apiVersion": 1,
                "groups": [{"orgId": 1, "folder": FOLDER, **build_rule_group()}],
            },
        ),
        CONTACT_POINTS_FILE: _document(
            CONTACT_POINTS_HEADER,
            {"apiVersion": 1, "contactPoints": [{"orgId": 1, **build_contact_point()}]},
        ),
        POLICY_FILE: _document(POLICY_HEADER, {"apiVersion": 1, "route": build_route()}),
    }
