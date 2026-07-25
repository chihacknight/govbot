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
# regenerates to prove it still matches this module.
DASHBOARD_PATH = "dashboards/fleet-overview.json"


def _datasource_variable(name: str, plugin: str, label: str) -> dict:
    """A datasource picker, so the JSON carries no stack-specific UID."""
    return {
        "current": {},
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


def _label_variable(name: str, datasource: dict, query: str, label: str) -> dict:
    """A multi-select picker fed by the datasource's own label values.

    Label-driven rather than a hardcoded list: a jurisdiction or workflow added
    to the pipeline-manager config shows up in the picker on its next sweep,
    with no dashboard edit. Left URL-synced (the Grafana default) so a filtered
    view — one state's freshness, one workflow's failures — is a link you can
    paste to someone.
    """
    return {
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        "datasource": datasource,
        "definition": query,
        "hide": 0,
        "includeAll": True,
        "label": label,
        "multi": True,
        "name": name,
        "options": [],
        "query": {"query": query, "refId": f"{name}-variable"},
        "refresh": 2,
        "regex": "",
        "sort": 1,
        "type": "query",
    }


def _templating() -> dict:
    return {
        "list": [
            _datasource_variable("metrics", "prometheus", "Metrics datasource"),
            _datasource_variable("logs", "loki", "Logs datasource"),
            _label_variable(
                "state", METRICS, "label_values(fleet_workflow_run_status, state)", "Jurisdiction"
            ),
            _label_variable("org", METRICS, "label_values(fleet_workflow_run_status, org)", "Org"),
            _label_variable(
                "workflow", METRICS, "label_values(fleet_workflow_run_status, workflow)", "Workflow"
            ),
            # Outcome exists only on the Loki streams — metrics carry a status
            # number, logs carry the run conclusion that produced them.
            _label_variable("outcome", LOGS, "label_values(outcome)", "Log outcome"),
        ]
    }


def _status_grid(panel_id: int, title: str, paused: str, mappings: dict, y: int,
                 height: int, description: str) -> dict:
    """One tile per jurisdiction+workflow, coloured by the latest completed run.

    A stat panel rather than a table because the question it answers is
    "anything red?", read in one glance across the whole fleet, and stat lays
    many series out as a grid on its own.
    """
    return {
        "datasource": METRICS,
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "text"},
                "mappings": [{"options": mappings, "type": "value"}],
                "noValue": "no data",
            },
            "overrides": [],
        },
        "gridPos": {"h": height, "w": 24, "x": 0, "y": y},
        "id": panel_id,
        "options": {
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "value_and_name",
            "wideLayout": False,
        },
        "targets": [
            {
                "datasource": METRICS,
                "editorMode": "code",
                "expr": (
                    f'fleet_workflow_run_status{{paused="{paused}", state=~"$state", '
                    'org=~"$org", workflow=~"$workflow"}'
                ),
                "instant": True,
                "legendFormat": "{{state}} {{workflow}}",
                "range": False,
                "refId": "A",
            }
        ],
        "title": title,
        "type": "stat",
    }


# Paused jurisdictions are out of session, so a failing run is expected rather
# than actionable: they keep their own grid, are never coloured red, and their
# text still says whether the last run failed — dimmed, not hidden.
ACTIVE_MAPPINGS = {
    "0": {"color": "red", "index": 0, "text": "FAILING"},
    "1": {"color": "green", "index": 1, "text": "OK"},
}
PAUSED_MAPPINGS = {
    "0": {"color": "text", "index": 0, "text": "paused · last run failed"},
    "1": {"color": "text", "index": 1, "text": "paused · last run ok"},
}


# The data-commit-age alert fires above 48 hours (README "Alerting"); the table
# turns red at the same number so the dashboard and the alert can never disagree.
STALE_HOURS = 48

AGE_FIELD = "Value"


def _freshness_table(panel_id: int, title: str, paused: str, thresholds: dict, y: int,
                     height: int, description: str, links: list) -> dict:
    """Hours since each repo's last data commit, worst first."""
    return {
        "datasource": METRICS,
        "description": description,
        "fieldConfig": {
            "defaults": {
                "custom": {"align": "auto", "cellOptions": {"type": "color-text"}},
                "links": links,
                "thresholds": thresholds,
                "unit": "h",
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": AGE_FIELD},
                    "properties": [{"id": "displayName", "value": "Hours since data commit"}],
                }
            ],
        },
        "gridPos": {"h": height, "w": 12, "x": 0 if paused == "false" else 12, "y": y},
        "id": panel_id,
        "options": {"showHeader": True},
        "targets": [
            {
                "datasource": METRICS,
                "editorMode": "code",
                "expr": (
                    f'fleet_repo_data_commit_age_hours{{paused="{paused}", state=~"$state", '
                    'org=~"$org"}'
                ),
                "format": "table",
                "instant": True,
                "range": False,
                "refId": "A",
            }
        ],
        "title": title,
        "transformations": [
            # The instant query returns one row per series with the labels as
            # columns; drop the bookkeeping ones and put the worst staleness on top.
            {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True,
                                                             "paused": True}}},
            {"id": "sortBy", "options": {"fields": {},
                                         "sort": [{"desc": True, "field": AGE_FIELD}]}},
        ],
        "type": "table",
    }


# A relative link, so it works in whatever stack the JSON was imported into:
# Grafana resolves it against the current dashboard and just swaps the filter.
STATE_LINK = [
    {
        "title": "Filter this dashboard to ${__data.fields.state}",
        "url": "?var-state=${__data.fields.state}&var-org=${__data.fields.org}",
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


def _panels() -> list:
    return [
        _status_grid(
            1,
            "Active jurisdictions",
            "false",
            ACTIVE_MAPPINGS,
            y=0,
            height=10,
            description=(
                "Latest completed run per expected workflow, in-session jurisdictions only. "
                "Red is actionable."
            ),
        ),
        _status_grid(
            2,
            "Paused jurisdictions",
            "true",
            PAUSED_MAPPINGS,
            y=10,
            height=6,
            description=(
                "Out-of-session jurisdictions. Shown for completeness and never coloured "
                "red — a stale or failing run here is expected, not a problem."
            ),
        ),
        _freshness_table(
            3,
            "Data freshness",
            "false",
            {
                "mode": "absolute",
                "steps": [
                    {"color": "green", "value": None},
                    {"color": "red", "value": STALE_HOURS},
                ],
            },
            y=16,
            height=12,
            description=(
                "Hours since the last commit touching each in-session repo's data path. "
                f"Red above {STALE_HOURS}h — the same line the staleness alert fires on."
            ),
            links=STATE_LINK,
        ),
        _freshness_table(
            4,
            "Data freshness · paused",
            "true",
            {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
            y=16,
            height=12,
            description=(
                "Out-of-session repos. Staleness here is the session calendar, not a fault, "
                "so nothing in this table turns red."
            ),
            links=STATE_LINK,
        ),
        _logs_panel(5, y=28),
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
