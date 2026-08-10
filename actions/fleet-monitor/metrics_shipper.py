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

The orchestrator (``run``) also emits, via ``encode_heartbeat`` below, one
untagged global heartbeat series each sweep — ``fleet_collector_heartbeat_repos``
and ``fleet_collector_heartbeat_errors`` (no state/org labels; it is about the
collector, not the fleet).

Labels are capped at state/org/workflow/paused by design; the README's Budgets
section is the single source of the series-count arithmetic (~336 for the
current fleet against the 10k free-tier limit). Repo name is derivable from
state+org, so it is not a label. A missing value (workflow never succeeded or
never completed a run, or a poll error recorded on the record) emits no line, and
a record that cannot be encoded at all (a control character in a tag, a missing
key) is skipped rather than aborting the sweep: absence, not a sentinel value,
marks the gap.
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


def encode_heartbeat(repos: int, errors: int, timestamp_seconds: int) -> str:
    """One line proving the collector itself ran this cycle.

    A single global series (no state/org/workflow tags — the heartbeat is about
    the collector, not the fleet) carrying the sweep size, so an absent
    heartbeat means the collector is down, distinct from any individual repo or
    workflow being down. Emitted on every run, even an all-errored or empty
    sweep, so the orchestrator always has something to push and an all-null
    fleet is provably the collector working on a broken fleet, not the collector
    failing to run.
    """
    timestamp_ns = int(timestamp_seconds) * 1_000_000_000
    fields = f"repos={_format_value(repos)},errors={_format_value(errors)}"
    return f"fleet_collector_heartbeat {fields} {timestamp_ns}\n"


def _record_lines(record, timestamp_ns: int) -> list:
    """The line-protocol lines for one poller record. Raises (ValueError from a
    bad tag/field, KeyError from a missing key) if the record can't be encoded;
    the caller isolates that per record, so a bad line is never half-built into
    the payload."""
    base = [("state", record["state"]), ("org", record["org"])]
    paused = ("paused", "true" if record["paused"] else "false")
    lines = []
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
    return lines


def encode_metrics(poller_records, timestamp_seconds: int) -> str:
    """Return the Influx line-protocol payload for a list of poller records.

    Pure function of its inputs: the same records and timestamp always produce
    a byte-identical payload (snapshot-tested). ``timestamp_seconds`` is epoch
    seconds, encoded as nanoseconds — the endpoint's default precision.

    Resilient per record, the way the poller is resilient per repo: a record
    that can't be encoded (a control character in a tag value, a non-numeric
    field, a missing key) is skipped, never a half-built line, and never blanks
    the rest of the sweep. Absence marks the gap — the same as a repo with no
    value to report — so one degraded record can't turn an otherwise-good sweep
    into an empty payload.
    """
    timestamp_ns = int(timestamp_seconds) * 1_000_000_000
    lines = []
    for record in poller_records:
        try:
            lines.extend(_record_lines(record, timestamp_ns))
        except (ValueError, KeyError, TypeError):
            # ValueError: bad tag (control char) or non-numeric string field.
            # KeyError: a missing required key. TypeError: a structured (list/
            # dict) field value reaching float(). Any shape of one repo's bad
            # data is skipped, never aborts the sweep.
            continue
    return "\n".join(lines) + "\n" if lines else ""
