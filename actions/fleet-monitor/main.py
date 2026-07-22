import json
import sys
from pathlib import Path

import click
import yaml

sys.path.append(str(Path(__file__).parent))

from fleet_config import read_fleet
from metrics_shipper import encode_metrics


@click.group()
def cli():
    """Fleet monitor: observability for the govbot scraper and data-repo fleets."""


@cli.command("collect")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Pipeline-manager config directory to poll (required unless --poller-records).",
)
@click.option(
    "--metrics-only",
    is_flag=True,
    required=True,
    help="Collect metrics only. Required until the log harvester exists (task 0004).",
)
@click.option("--dry-run", is_flag=True, help="Print the encoded payload instead of pushing.")
@click.option(
    "--poller-records",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSONL file of pre-built poller records; skips the GitHub poll (used by snapshots).",
)
@click.option(
    "--timestamp",
    type=int,
    default=None,
    help="Epoch-seconds timestamp for every series (default: now). Snapshots pin this.",
)
def collect(config_dir, metrics_only, dry_run, poller_records, timestamp):
    """Poll the fleet and push (or print) Grafana Cloud metric payloads.

    Exits 1 when any repo had poll errors — partial data still ships (or
    prints), but a degraded sweep must never look like a clean one.
    """
    if poller_records is not None:
        records = [
            json.loads(line)
            for line in poller_records.read_text().splitlines()
            if line.strip()
        ]
    elif config_dir is not None:
        records = _poll_live(config_dir)
    else:
        raise click.ClickException("pass --config-dir (live poll) or --poller-records (fixture)")

    try:
        payload = encode_metrics(records, timestamp if timestamp is not None else _default_timestamp(records))
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    errored = _report_poll_errors(records)

    if dry_run:
        click.echo(payload, nl=False)
    elif not payload:
        click.echo("nothing to push: payload is empty", err=True)
    else:
        _push(payload)
    if errored:
        raise click.ClickException(f"poll errors on {len(errored)} of {len(records)} repos")


def _report_poll_errors(records):
    """Echo every per-repo poll error to stderr; return the errored records."""
    errored = [r for r in records if r.get("errors")]
    for record in errored:
        for error in record["errors"]:
            click.echo(f"poll error: {record['org']}/{record['repo']}: {error}", err=True)
    return errored


def _default_timestamp(records):
    """Series timestamp when --timestamp is absent: the records' own polled_at
    (so replayed --poller-records files keep honest fetch times), else now."""
    import time
    from datetime import datetime

    stamps = [r["polled_at"] for r in records if r.get("polled_at")]
    if stamps:
        return int(datetime.fromisoformat(max(stamps).replace("Z", "+00:00")).timestamp())
    return int(time.time())


def _poll_live(config_dir):
    """Read the fleet config and poll GitHub for every repo's current state."""
    import os

    if not os.environ.get("GITHUB_TOKEN"):
        raise click.ClickException(
            "GITHUB_TOKEN is required for live polls: one sweep of the current fleet "
            "costs ~336 requests and the unauthenticated GitHub limit is 60/hour"
        )
    try:
        jurisdictions = read_fleet(config_dir)
    except (ValueError, yaml.YAMLError) as e:
        raise click.ClickException(str(e)) from e
    from fleet_poller import poll_fleet

    try:
        return poll_fleet(jurisdictions)
    except ValueError as e:
        raise click.ClickException(str(e)) from e


def _push(payload):
    from metrics_push import push_metrics

    try:
        push_metrics(payload)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"pushed {len(payload.splitlines())} series lines", err=True)


@cli.command("list-fleet")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Directory holding pipeline-manager config YAMLs and their templates/ folder.",
)
def list_fleet(config_dir: Path):
    """Print one JSON Lines jurisdiction record per locale per fleet."""
    try:
        records = read_fleet(config_dir)
    except (ValueError, yaml.YAMLError) as e:
        raise click.ClickException(str(e)) from e
    for record in records:
        click.echo(json.dumps(record, ensure_ascii=False))


@cli.command("live-check")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Pipeline-manager config directory to poll and push.",
)
def live_check(config_dir):
    """Poll, push, then query Grafana for every shipped metric; skips without credentials.

    End-to-end proof against the live stack: runs a real collect (GitHub poll +
    Grafana push), then asks the stack's Prometheus query API for all three
    shipped metric names, retrying for up to a minute — Grafana Cloud ingestion
    lags a push by seconds, so an instant query would flake false-negative on a
    fresh stack. Refuses an empty payload, and exits 1 after the proof when any
    repo had poll errors: a degraded sweep must never look like a clean one.
    Needs all six GRAFANA_{PUSH,QUERY}_{URL,USER,KEY} env vars; exits 0 with a
    skip notice otherwise, so offline runs (CI) pass without a Grafana account.
    """
    import base64
    import os
    import time
    import urllib.parse

    names = [
        f"GRAFANA_{role}_{part}" for role in ("PUSH", "QUERY") for part in ("URL", "USER", "KEY")
    ]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        click.echo(f"live check skipped: missing {', '.join(missing)}")
        return

    from http_util import request_json

    records = _poll_live(config_dir)
    errored = _report_poll_errors(records)
    payload = encode_metrics(records, int(time.time()))
    if not payload:
        raise click.ClickException("nothing to push: payload is empty")
    _push(payload)

    credentials = f"{os.environ['GRAFANA_QUERY_USER']}:{os.environ['GRAFANA_QUERY_KEY']}"
    auth = {"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}
    metrics = [
        "fleet_workflow_run_status",
        "fleet_workflow_run_hours_since_success",
        "fleet_repo_data_commit_age_hours",
    ]
    deadline = time.monotonic() + 60
    for metric in metrics:
        while True:
            query = urllib.parse.urlencode({"query": metric})
            result = request_json(
                f"{os.environ['GRAFANA_QUERY_URL'].rstrip('/')}/api/v1/query?{query}",
                headers=auth,
            )
            series = result.get("data", {}).get("result", [])
            if series:
                click.echo(f"✓ live check: {len(series)} {metric} series queryable")
                break
            if time.monotonic() >= deadline:
                raise click.ClickException(
                    f"push succeeded but {metric} returned no series within 60s"
                )
            time.sleep(5)
    if errored:
        # The proof ran, but a degraded sweep must never look like a clean one.
        raise click.ClickException(f"poll errors on {len(errored)} of {len(records)} repos")


if __name__ == "__main__":
    cli(auto_envvar_prefix="FLEET_MONITOR")
