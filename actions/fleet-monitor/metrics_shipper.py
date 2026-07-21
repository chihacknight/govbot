"""Encode poller records into a Grafana Cloud metric-push payload.

Transport is the Grafana Cloud Influx line-protocol push endpoint
(https://<stack>.grafana.net/api/v1/push/influx/write): plain text, one line per
point, no client library. Grafana converts each line to Prometheus-style series
named ``<measurement>_<field>`` with the tags as labels:

    fleet_workflow_run_status{state, org, workflow, paused}
        1.0 when the latest completed run's conclusion is "success", else 0.0.
    fleet_workflow_run_hours_since_success{state, org, workflow, paused}
        Hours since the last successful run of that workflow.
    fleet_repo_data_commit_age_hours{state, org, paused}
        Hours since the last commit touching the repo's data path.

Labels are capped at state/org/workflow/paused by design; the README's Budgets
section is the single source of the series-count arithmetic (~336 for the
current fleet against the 10k free-tier limit). Repo name is derivable from
state+org, so it is not a label. A missing value (workflow never succeeded or
never completed a run, or a poll error recorded on the record) emits no line:
absence, not a sentinel value, marks the gap.
"""


def _escape_tag(value: str) -> str:
    """Escape a tag value per Influx line protocol (commas, equals, spaces).

    Rejects control characters outright: a newline in a tag value would split
    the payload line and smuggle in a forged series, so it fails loudly
    instead of being escaped away.
    """
    value = str(value)
    if any(c in value for c in "\n\r"):
        raise ValueError(f"control character in metric tag value {value!r}")
    return (
        value.replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")
    )


def _format_value(value) -> str:
    """Render a numeric field value; integers stay bare floats ("1" not "1.0i")."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


def _tags(pairs) -> str:
    return ",".join(f"{key}={_escape_tag(value)}" for key, value in pairs)


def encode_metrics(poller_records, timestamp_seconds: int) -> str:
    """Return the Influx line-protocol payload for a list of poller records.

    Pure function of its inputs: the same records and timestamp always produce
    a byte-identical payload (snapshot-tested). ``timestamp_seconds`` is epoch
    seconds, encoded as nanoseconds — the endpoint's default precision.
    """
    timestamp_ns = int(timestamp_seconds) * 1_000_000_000
    lines = []
    for record in poller_records:
        base = [("state", record["state"]), ("org", record["org"])]
        paused = ("paused", "true" if record["paused"] else "false")
        for wf in record.get("workflows", []):
            tags = _tags(base + [("workflow", wf["workflow"]), paused])
            fields = []
            if wf.get("latest_conclusion") is not None:
                status = 1 if wf["latest_conclusion"] == "success" else 0
                fields.append(f"status={_format_value(status)}")
            if wf.get("hours_since_success") is not None:
                fields.append(f"hours_since_success={_format_value(wf['hours_since_success'])}")
            if fields:
                lines.append(f"fleet_workflow_run,{tags} {','.join(fields)} {timestamp_ns}")
        if record.get("data_commit_age_hours") is not None:
            tags = _tags(base + [paused])
            age = _format_value(record["data_commit_age_hours"])
            lines.append(f"fleet_repo,{tags} data_commit_age_hours={age} {timestamp_ns}")
    return "\n".join(lines) + "\n" if lines else ""
