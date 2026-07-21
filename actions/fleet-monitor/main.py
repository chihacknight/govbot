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
    """Poll the fleet and push (or print) Grafana Cloud metric payloads."""
    import time

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

    payload = encode_metrics(records, timestamp if timestamp is not None else int(time.time()))
    for record in records:
        for error in record.get("errors", []):
            click.echo(f"poll error: {record['org']}/{record['repo']}: {error}", err=True)

    if dry_run:
        click.echo(payload, nl=False)
        return
    _push(payload)


def _poll_live(config_dir):
    """Read the fleet config and poll GitHub for every repo's current state."""
    try:
        jurisdictions = read_fleet(config_dir)
    except (ValueError, yaml.YAMLError) as e:
        raise click.ClickException(str(e)) from e
    from fleet_poller import poll_fleet

    return poll_fleet(jurisdictions)


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
    """Poll, push, then query Grafana for a shipped series; skips without credentials.

    End-to-end proof against the live stack: runs a real collect (GitHub poll +
    Grafana push), then asks the stack's Prometheus query API for
    fleet_workflow_run_status and fails unless series come back. Needs all six
    GRAFANA_{PUSH,QUERY}_{URL,USER,KEY} env vars; exits 0 with a skip notice
    otherwise, so offline runs (CI) pass without a Grafana account.
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

    payload = encode_metrics(_poll_live(config_dir), int(time.time()))
    _push(payload)

    credentials = f"{os.environ['GRAFANA_QUERY_USER']}:{os.environ['GRAFANA_QUERY_KEY']}"
    query = urllib.parse.urlencode({"query": "fleet_workflow_run_status"})
    result = request_json(
        f"{os.environ['GRAFANA_QUERY_URL'].rstrip('/')}/api/v1/query?{query}",
        headers={"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()},
    )
    series = result.get("data", {}).get("result", [])
    if not series:
        raise click.ClickException("push succeeded but fleet_workflow_run_status returned no series")
    click.echo(f"✓ live check: {len(series)} fleet_workflow_run_status series queryable")


if __name__ == "__main__":
    cli(auto_envvar_prefix="FLEET_MONITOR")
