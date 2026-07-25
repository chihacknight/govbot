"""Build the fleet-overview Grafana dashboard as data, not by hand.

The committed artifact is ``dashboards/fleet-overview.json``; this module is
what produces it (``main.py dashboard``), so the dashboard is reviewable as
code and regenerating it is a diff, not a re-export from somebody's browser.
"""

import json

METRICS = {"type": "prometheus", "uid": "${metrics}"}
LOGS = {"type": "loki", "uid": "${logs}"}

# Stable across every stack this is imported into, so links to it (and the
# alert rules in the next task) keep working after a re-import.
DASHBOARD_UID = "fleet-monitor-overview"

# The committed artifact: what a maintainer imports, and what the render script
# re-renders and diffs to prove it still matches this module.
DASHBOARD_PATH = "dashboards/fleet-overview.json"

# The workflow's cron says hourly. GitHub does not honour it: scheduled runs are
# best-effort and queue behind everything else, and on a fork's non-default
# branch they drift badly. Measured over 25 consecutive sweeps (2026-07-22..25):
# median gap 2.0h, MAX 3.6h, with 4 of 24 gaps past three hours.
#
# Size the look-back against that, never against the cron expression — a 3h
# window read "No data" for the ~30 minutes after each long gap, which is
# exactly how the board went blank the second time.
OBSERVED_MAX_SWEEP_GAP_HOURS = 3.6

# ~1.7x the worst observed gap. The cost of a wider window is that a displayed
# value can be up to this old: a data-commit age can under-report by one window,
# so a repo at 43h reads green when it has really crossed the 48h line. Against
# a 48h threshold that is tolerable; a much wider window would not be.
#
# An instant query resolves against Prometheus's 5-minute staleness lookback, so
# a bare selector finds nothing between sweeps whatever the schedule — hence
# last_over_time, which stays an instant vector, leaving the table
# transformations and the stat reducer unaffected. main.py's live-check
# documents the same 5-minute trap from the other side.
#
# The other cost of the window: `paused` is a label, so flipping a jurisdiction
# in or out of session starts a new series and abandons the old one, and the
# abandoned twin stays resolvable for the look-back. For up to one window after a
# transition a jurisdiction appears twice in a grid — including, briefly, red for
# something now out of session. The same lag applies to a workflow dropped from
# expected_workflows. It settles on its own; it is the price of a board that
# renders at all between sweeps.
LOOKBACK = "6h"

# This fleet's own stack, so an import renders immediately instead of making
# someone hunt through pickers. The import screen never asks (that prompt needs
# an `__inputs` block, which parameterizing by variable deliberately avoids), and
# Grafana's own fallback is the first datasource of the type in name order —
# which on Grafana Cloud is as likely to be `grafanacloud-usage` as the stack's
# own. These are defaults, not hardcoded uids: the pickers still work, so another
# stack overrides them by hand and nothing else about the JSON changes.
DEFAULT_METRICS_DATASOURCE = "grafanacloud-govbot-prom"
DEFAULT_LOGS_DATASOURCE = "grafanacloud-govbot-logs"

# The scrape is the fleet's entry point — every other workflow consumes what it
# produces — so it gets a pinned grid at the top of the board. It is the ONLY
# workflow named in this file: the rest are discovered from the metric's labels
# (see the `other_workflow` variable), because a hardcoded list is exactly how
# `extract-text.yml` shipped upstream and went unmonitored.
SCRAPE_WORKFLOW = "openstates-scrape.yml"


def _latest(selector: str) -> str:
    """The last sample of a selector within the look-back, as an instant vector."""
    return f"last_over_time({selector}[{LOOKBACK}])"


def _datasource_variable(name: str, plugin: str, label: str, default: str) -> dict:
    """A datasource picker, so the JSON carries no stack-specific UID."""
    return {
        "current": {"text": default, "value": default},
        "hide": 0,
        "includeAll": False,
        "label": label,
        "multi": False,
        "name": name,
        "options": [],
        "query": plugin,
        "refresh": 1,
        "regex": "",
        "skipUrlSync": False,
        "type": "datasource",
    }


# Scopes the Loki picker to this fleet's own streams: every stream the harvester
# ships carries a state label, so another producer's `outcome` values in the same
# logs instance can't leak into the picker.
FLEET_STREAMS = '{state=~".+"}'


def _label_variable(name: str, datasource: dict, query: dict, definition: str, label: str) -> dict:
    """A multi-select picker fed by the datasource's own label values.

    Label-driven rather than a hardcoded list: a jurisdiction or workflow added
    to the pipeline-manager config shows up in the picker on its next sweep,
    with no dashboard edit. Left URL-synced (the Grafana default) so a filtered
    view — one state's freshness, one workflow's failures — is a link you can
    paste to someone.

    ``allValue`` is explicit and not optional. Left blank, Grafana expands "All"
    to an alternation of the options it resolved — and to the empty string when
    it resolved none, which turns every ``=~`` matcher into one that matches
    nothing. A picker that hasn't populated yet would silently blank every panel
    that uses it, and it would look identical to having no data at all.

    It is ``.+`` rather than ``.*`` because LogQL rejects a stream selector
    whose every matcher is empty-compatible: with all four pickers on All,
    ``{state=~".*", …}`` is a parse error, not an empty result. Every fleet
    stream and every fleet series carries all four labels, so ``.+`` selects
    exactly the same thing and is legal in both LogQL and PromQL.

    ``query`` is the datasource's own query object, not one shape for both:
    Prometheus wants the label-values discriminator its editor writes, Loki
    wants a different object entirely, and feeding either the other's shape
    leaves the picker empty.
    """
    return {
        "allValue": ".+",
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        "datasource": datasource,
        "definition": definition,
        "hide": 0,
        "includeAll": True,
        "label": label,
        "multi": True,
        "name": name,
        "options": [],
        "query": query,
        "refresh": 2,
        "regex": "",
        "sort": 1,
        "type": "query",
    }


def _prometheus_label_values(name: str) -> dict:
    """A Prometheus label-values variable query.

    The query string is the operative field — it is what Prometheus's
    ``metricFindQuery`` parses — and this is the shape Grafana persists for a
    label-values variable. Editor-state fields are deliberately absent: a
    partial set of them opens the variable editor half-populated, and saving
    from there writes back an empty ``label_values()`` that resolves to nothing.
    """
    return {
        "query": f"label_values(fleet_workflow_run_status, {name})",
        "refId": "PrometheusVariableQueryEditor-VariableQuery",
    }


def _metrics_picker(name: str, label: str) -> dict:
    return _label_variable(
        name,
        METRICS,
        _prometheus_label_values(name),
        f"label_values(fleet_workflow_run_status, {name})",
        label,
    )


def _templating() -> dict:
    return {
        "list": [
            _datasource_variable(
                "metrics", "prometheus", "Metrics datasource", DEFAULT_METRICS_DATASOURCE
            ),
            _datasource_variable("logs", "loki", "Logs datasource", DEFAULT_LOGS_DATASOURCE),
            _metrics_picker("state", "Jurisdiction"),
            _metrics_picker("org", "Org"),
            _metrics_picker("workflow", "Workflow"),
            # Outcome exists only on the Loki streams — metrics carry a status
            # number, logs carry the run conclusion that produced them — so this
            # one picker speaks Loki's variable-query dialect (type 1 = label
            # values), not Prometheus's.
            _label_variable(
                "outcome",
                LOGS,
                {
                    "label": "outcome",
                    "refId": "LokiVariableQueryEditor-VariableQuery",
                    "stream": FLEET_STREAMS,
                    "type": 1,
                },
                f"label_values({FLEET_STREAMS}, outcome)",
                "Log outcome",
            ),
            # Drives the repeated status grids: every workflow except the pinned
            # scrape one, which has its own grid at the top. Excluded in the
            # query rather than by a regex over the results, so the rule is one
            # readable matcher. Hidden from the toolbar (hide: 2) — it is panel
            # plumbing, not a filter anyone should be setting by hand.
            {
                **_label_variable(
                    "other_workflow",
                    METRICS,
                    {
                        "query": (
                            f'label_values(fleet_workflow_run_status{{workflow!="{SCRAPE_WORKFLOW}"}}'
                            ", workflow)"
                        ),
                        "refId": "PrometheusVariableQueryEditor-VariableQuery",
                    },
                    f'label_values(fleet_workflow_run_status{{workflow!="{SCRAPE_WORKFLOW}"}}'
                    ", workflow)",
                    "Other workflows",
                ),
                "hide": 2,
            },
        ]
    }


# Paused jurisdictions are out of session, so a failing run is the legislative
# calendar rather than something to act on. They sit in the same grid as
# everything else — hiding them loses the fleet, and giving them their own panel
# left a permanently empty box whenever the whole fleet is in session — but they
# are dimmed to a flat colour and never red, and their text still says whether
# the last run failed.
ACTIVE_MAPPINGS = {
    "0": {"color": "red", "index": 0, "text": "FAILING"},
    "1": {"color": "green", "index": 1, "text": "OK"},
}
PAUSED_MAPPINGS = {
    "0": {"color": "text", "index": 0, "text": "paused · last run failed"},
    "1": {"color": "text", "index": 1, "text": "paused · last run ok"},
}

# The tile text, as large as the OK/FAILING beside it. A jurisdiction is its
# two-letter code and nothing else: the workflow is the panel it sits in now,
# so repeating it per tile only shrank the part that identifies the tile.
TILE_TEXT_SIZE = 18


def _status_grid(panel_id: int, title: str, workflow: str, y: int, height: int,
                 description: str, repeat: str = None) -> dict:
    """One tile per jurisdiction, coloured by its latest completed run.

    A stat panel rather than a table because the question it answers is
    "anything red?", read in one glance, and stat lays many series out as a grid
    on its own. One grid per workflow keeps that glance readable: 112 tiles in a
    single panel shrank the text past legibility.

    ``repeat`` names a variable to generate one grid per value of, instead of
    pinning a single workflow. That is how every workflow but the scrape gets a
    grid without being named here — `extract-text.yml` was added upstream and
    went unmonitored precisely because the workflows were a hardcoded pair.

    Paused jurisdictions come from a second query rather than a second panel, so
    the grid holds the whole fleet; an override keyed on that query's refId
    flattens their colour and rewords their mapping, which is the only way
    Grafana will colour some tiles by value and others not.
    """
    def target(ref_id: str, paused: str) -> dict:
        return {
            "datasource": METRICS,
            "editorMode": "code",
            # The workflow is fixed by the panel — pinned, or supplied by the
            # repeat — so it carries no `workflow=~"$workflow"` matcher of its
            # own. The workflow picker still scopes the logs panel.
            "expr": _latest(
                f'fleet_workflow_run_status{{workflow="{workflow}", paused="{paused}", '
                'state=~"$state", org=~"$org"}'
            ),
            "instant": True,
            "legendFormat": "{{state}}",
            "range": False,
            "refId": ref_id,
        }

    panel = {
        "datasource": METRICS,
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "text"},
                "mappings": [{"options": ACTIVE_MAPPINGS, "type": "value"}],
                "noValue": "no data",
            },
            "overrides": [
                {
                    "matcher": {"id": "byFrameRefID", "options": "B"},
                    "properties": [
                        {"id": "color", "value": {"fixedColor": "text", "mode": "fixed"}},
                        {"id": "mappings", "value": [
                            {"options": PAUSED_MAPPINGS, "type": "value"}
                        ]},
                    ],
                }
            ],
        },
        "gridPos": {"h": height, "w": 24, "x": 0, "y": y},
        "id": panel_id,
        "options": {
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "text": {"titleSize": TILE_TEXT_SIZE, "valueSize": TILE_TEXT_SIZE},
            "textMode": "value_and_name",
            "wideLayout": False,
        },
        "targets": [target("A", "false"), target("B", "true")],
        "title": title,
        "type": "stat",
    }
    if repeat:
        panel["repeat"] = repeat
        panel["repeatDirection"] = "v"
    return panel


# The data-commit-age alert fires above 48 hours (README "Alerting"); the table
# turns red at the same number so the dashboard and the alert can never disagree.
STALE_HOURS = 48

AGE_FIELD = "Value"


def _freshness_table(panel_id: int, y: int, height: int) -> dict:
    """Hours since each repo's last data commit — the whole fleet, one table.

    Paused repos are a column here rather than a second panel: a table can say
    "out of session" in a cell, and the separate panel it replaces was an empty
    box whenever the whole fleet was in session, which is most of the time.

    The cost, worth knowing: a table colours a column by threshold, not a row by
    another row's value, so a paused repo stale past 48 h does turn red — the
    one place the never-red-for-paused rule cannot hold. Sorting keeps it out of
    the way: in-session repos first, worst staleness at the top of them, so the
    rows that need action outrank rows that are just waiting for a session.
    """
    return {
        "datasource": METRICS,
        "description": (
            "Hours since the last commit touching each repo's data path, in-session repos "
            f"first. Red above {STALE_HOURS}h — the same line the staleness alert fires on. "
            "A paused repo is stale by the session calendar, not by fault; read the paused "
            "column before reacting to its colour."
        ),
        "fieldConfig": {
            "defaults": {
                "custom": {"align": "auto", "cellOptions": {"type": "color-text"}},
                "links": STATE_LINK,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                        {"color": "red", "value": STALE_HOURS},
                    ],
                },
                "unit": "h",
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": AGE_FIELD},
                    "properties": [{"id": "displayName", "value": "Hours since data commit"}],
                },
                {
                    # The paused column is a label, not a measurement — colouring
                    # it by the staleness thresholds would be meaningless.
                    "matcher": {"id": "byName", "options": "paused"},
                    "properties": [
                        {"id": "displayName", "value": "In session"},
                        {"id": "custom.cellOptions", "value": {"type": "auto"}},
                        {"id": "mappings", "value": [{
                            "options": {
                                "false": {"color": "text", "index": 0, "text": "yes"},
                                "true": {"color": "text", "index": 1, "text": "paused"},
                            },
                            "type": "value",
                        }]},
                    ],
                },
            ],
        },
        "gridPos": {"h": height, "w": 24, "x": 0, "y": y},
        "id": panel_id,
        "options": {"showHeader": True},
        "targets": [
            {
                "datasource": METRICS,
                "editorMode": "code",
                "expr": _latest(
                    'fleet_repo_data_commit_age_hours{state=~"$state", org=~"$org"}'
                ),
                "format": "table",
                "instant": True,
                "range": False,
                "refId": "A",
            }
        ],
        "title": "Data freshness",
        "transformations": [
            # The instant query returns one row per series with the labels as
            # columns; drop the bookkeeping ones. `paused` stays — it is the
            # column that replaced the second table. (No __name__ to drop: a
            # range-vector function strips it.)
            {"id": "organize", "options": {"excludeByName": {"Time": True}}},
            # In-session first ("false" sorts before "true"), worst staleness at
            # the top of each group.
            {"id": "sortBy", "options": {"fields": {}, "sort": [
                {"desc": False, "field": "paused"},
                {"desc": True, "field": AGE_FIELD},
            ]}},
        ],
        "type": "table",
    }


# Clicking a freshness row narrows the whole board — grids, table, and logs — to
# that jurisdiction, through the single `state` picker. One picker means the
# filter you can see at the top is the filter that is applied, everywhere.
#
# The path is absolute on purpose: the bare "?var=..." relative URL this replaced
# was silently inert, rewriting the address bar without re-running a thing, which
# is why the link looked live and did nothing. Carrying the time range through
# means the click doesn't also reset the window someone just chose. It sets the
# jurisdiction only — adding `var-org` narrowed to one of the jurisdiction's two
# repos, hiding its sibling.
STATE_LINK = [
    {
        "title": "Filter to ${__data.fields.state}",
        "url": (
            f"/d/{DASHBOARD_UID}?var-state=${{__data.fields.state}}"
            "&${__url_time_range}"
        ),
    }
]


def _logs_panel(panel_id: int, y: int) -> dict:
    """The harvested run logs, filtered by the same pickers as the grids.

    Every stream label the harvester ships (org, state, workflow, outcome) is a
    regex matcher against a multi-select variable, so "All" (``.*``) and a
    single pick both work, and with outcome left on All a failure's full log and
    a recent success's tail sit in the same view. Run id and run URL travel as
    structured metadata rather than labels, so they surface by expanding a line
    — hence log details on.
    """
    return {
        "datasource": LOGS,
        "description": (
            "Harvested run logs. Failures ship in full (capped at 256 KB); successes ship "
            "their last ~100 lines. Expand a line for its run id and a link to the run."
        ),
        "gridPos": {"h": 12, "w": 24, "x": 0, "y": y},
        "id": panel_id,
        "options": {
            "dedupStrategy": "none",
            "enableLogDetails": True,
            "prettifyLogMessage": False,
            "showCommonLabels": False,
            "showLabels": True,
            "showTime": True,
            "sortOrder": "Descending",
            "wrapLogMessage": True,
        },
        "targets": [
            {
                "datasource": LOGS,
                "editorMode": "code",
                "expr": (
                    '{state=~"$state", org=~"$org", workflow=~"$workflow", outcome=~"$outcome"}'
                ),
                "queryType": "range",
                "refId": "A",
            }
        ],
        "title": "Run logs",
        "type": "logs",
    }


GRID_HEIGHT = 12
TABLE_HEIGHT = 14
LOGS_HEIGHT = 12


def _panels() -> list:
    """Scrapers, freshness, logs — then a grid per remaining workflow.

    The scrape is the fleet's entry point and everything downstream depends on
    it, so it is pinned to the top where it needs no scrolling. The rest of the
    workflows are generated by Grafana's panel repeat and sit below the logs:
    naming them here is what let `extract-text.yml` ship upstream and go
    unmonitored, so the dashboard no longer holds a list that can fall behind.
    """
    return [
        _status_grid(
            1,
            "Scrapers",
            SCRAPE_WORKFLOW,
            y=0,
            height=GRID_HEIGHT,
            description=(
                "Latest completed scrape per jurisdiction — the fleet's entry point. Red is "
                "actionable; a dimmed tile is out of session, where a failing run is the "
                "calendar, not a fault."
            ),
        ),
        _freshness_table(2, y=GRID_HEIGHT, height=TABLE_HEIGHT),
        _logs_panel(3, y=GRID_HEIGHT + TABLE_HEIGHT),
        _status_grid(
            4,
            "$other_workflow",
            "$other_workflow",
            y=GRID_HEIGHT + TABLE_HEIGHT + LOGS_HEIGHT,
            height=GRID_HEIGHT,
            description=(
                "Latest completed run per jurisdiction for this workflow. One grid per "
                "workflow the fleet runs besides the scrape, generated from the metric's own "
                "labels — a workflow added to the pipeline-manager config appears here on its "
                "next sweep, with no dashboard edit."
            ),
            repeat="other_workflow",
        ),
    ]


def build_dashboard() -> dict:
    """The whole dashboard as a plain dict.

    ``id: None`` is deliberate: a numeric id belongs to one stack's database, so
    carrying one would make the import either collide with or overwrite whatever
    holds that id in the destination. The uid is the stable identity instead.
    """
    return {
        "annotations": {"list": []},
        "editable": True,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "panels": _panels(),
        "refresh": "5m",
        "schemaVersion": 39,
        "tags": ["fleet-monitor"],
        "templating": _templating(),
        # A day covers the hourly sweep with room to see a gap; the logs panel
        # inherits it, so the default view holds roughly a day of run logs.
        "time": {"from": "now-24h", "to": "now"},
        "timezone": "utc",
        "title": "Fleet Monitor",
        "uid": DASHBOARD_UID,
        "version": 0,
    }


def encode_dashboard() -> str:
    """The dashboard as the JSON that gets committed and imported.

    Indented and key-sorted so the committed artifact reviews as a readable
    diff, and byte-identical run to run so regenerating it proves nothing
    drifted.
    """
    return json.dumps(build_dashboard(), indent=2, sort_keys=True) + "\n"
