import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import click
import yaml

sys.path.append(str(Path(__file__).parent))

from fleet_config import read_fleet
from log_harvester import github_log_fetchers, harvest_logs
from logs_shipper import encode_logs
from metrics_shipper import encode_heartbeat, encode_metrics
from watermark import load_watermarks, save_watermarks


@click.group()
def cli():
    """Fleet monitor: observability for the govbot scraper and data-repo fleets."""


@cli.command("collect")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Pipeline-manager config directory to poll (required unless --poller-records).",
)
@click.option("--metrics-only", is_flag=True, help="Collect metrics only.")
@click.option("--logs-only", is_flag=True, help="Harvest and ship run logs only.")
@click.option("--dry-run", is_flag=True, help="Print the encoded payload instead of pushing.")
@click.option(
    "--poller-records",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSONL file of pre-built poller records; skips the GitHub poll (used by snapshots).",
)
@click.option(
    "--log-fixture",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Directory of offline log-run fixtures; skips the GitHub log fetch (used by snapshots).",
)
@click.option(
    "--watermark-file",
    type=click.Path(dir_okay=False, path_type=Path),
    help="JSON file tracking the last shipped run per repo/workflow (log idempotency).",
)
@click.option(
    "--timestamp",
    type=int,
    default=None,
    help="Epoch-seconds timestamp for every series (default: the records' polled_at, "
         "else now); also anchors the log harvester's look-back window.",
)
def collect(config_dir, metrics_only, logs_only, dry_run, poller_records, log_fixture,
            watermark_file, timestamp):
    """Poll the fleet and push (or print) Grafana Cloud metric and/or log payloads.

    Both legs share collect's exit contract — a degraded sweep must never look
    like a clean one: the metrics leg exits 1 when any repo had poll errors, and
    the logs leg exits 1 when any repo's harvest erred. Partial data still ships
    (or prints) first. An *empty* log sweep, though — no run newer than the
    watermark — is the idempotent steady state and exits 0: nothing was degraded,
    there was simply nothing new.
    """
    if not (metrics_only or logs_only):
        raise click.ClickException("pass --metrics-only and/or --logs-only")
    log_errors = []
    if logs_only:
        log_errors = _collect_logs(config_dir, log_fixture, watermark_file, dry_run,
                                   _harvest_now(timestamp))
    if not metrics_only:
        if log_errors:
            raise click.ClickException(f"log harvest errors on {len(log_errors)} target(s)")
        return

    records = _load_records(config_dir, poller_records)

    errored = _report_poll_errors(records)
    payload = _encode(records, timestamp if timestamp is not None else _default_timestamp(records))

    if not payload:
        # An all-null sweep emitting nothing is indistinguishable, stack-side,
        # from the monitor never running — that must not read as clean, in
        # push mode or on the dry-run path operators use to verify a sweep.
        raise click.ClickException(
            "nothing to push: payload is empty"
            + (f" (poll errors on {len(errored)} of {len(records)} repos)" if errored else "")
        )
    if dry_run:
        click.echo(payload, nl=False)
    else:
        _push(payload)
    if errored or log_errors:
        parts = []
        if errored:
            parts.append(f"poll errors on {len(errored)} of {len(records)} repos")
        if log_errors:
            parts.append(f"log harvest errors on {len(log_errors)} target(s)")
        raise click.ClickException("; ".join(parts))


@cli.command("run")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Pipeline-manager config directory to poll (required unless --poller-records).",
)
@click.option("--dry-run", is_flag=True, help="Print the encoded payload instead of pushing.")
@click.option(
    "--poller-records",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSONL file of pre-built poller records; skips the GitHub poll (used by snapshots).",
)
@click.option(
    "--log-fixture",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Directory of offline log-run fixtures; skips the GitHub log fetch (used by snapshots).",
)
@click.option(
    "--watermark-file",
    type=click.Path(dir_okay=False, path_type=Path),
    help="JSON file tracking the last shipped run per repo/workflow (log idempotency).",
)
@click.option(
    "--timestamp",
    type=int,
    default=None,
    help="Epoch-seconds timestamp for every series (default: the records' polled_at, "
         "else now); also anchors the log harvester's look-back window.",
)
def run(config_dir, dry_run, poller_records, log_fixture, watermark_file, timestamp):
    """Unattended hourly sweep: poll the fleet, ship metrics + a heartbeat + logs.

    The orchestrator the hourly workflow invokes. Wires config reader → poller →
    metrics shipper, appends a collector heartbeat that ships on every run, then
    harvests each repo's new run logs and ships them to Loki.

    Exit contract differs from ``collect`` on purpose: only an *outright*
    collector failure exits nonzero — a config or poll error, or a failed push
    (e.g. a bad Grafana key) — so a red workflow run always means the collector
    itself is down. Per-repo poll and log-harvest errors are logged to stderr but
    keep the run green: a degraded fleet surfaces through the shipped telemetry and
    Grafana alerts, not by turning the collector's own workflow red. The heartbeat
    always ships, so an all-null sweep still proves the collector ran.

    The logs leg runs only when a log source is configured (``--config-dir`` for a
    live harvest, or ``--log-fixture`` offline); a metrics-only invocation
    (``--poller-records`` alone) skips it.
    """
    records = _load_records(config_dir, poller_records)

    errored = _report_poll_errors(records)
    series_timestamp = timestamp if timestamp is not None else _default_timestamp(records)
    # encode_metrics is resilient per record — one repo's un-encodable data is
    # skipped, never blanks the rest of the sweep — so a red run always means the
    # collector itself is down, never a single degraded repo.
    payload = encode_metrics(records, series_timestamp)
    payload += encode_heartbeat(len(records), len(errored), series_timestamp)

    if dry_run:
        click.echo(payload, nl=False)
    else:
        _push(payload)

    if config_dir is not None or log_fixture is not None:
        _collect_logs(config_dir, log_fixture, watermark_file, dry_run,
                      _harvest_now(timestamp))


def _load_records(config_dir, poller_records):
    """Records for a sweep: a pre-built --poller-records fixture (offline) or a
    live poll of --config-dir. Shared by ``collect`` and ``run``."""
    if poller_records is not None:
        return [
            json.loads(line)
            for line in poller_records.read_text().splitlines()
            if line.strip()
        ]
    if config_dir is not None:
        return _poll_live(config_dir)
    raise click.ClickException("pass --config-dir (live poll) or --poller-records (fixture)")


def _expected_series(payload):
    """Per-metric series counts in a line-protocol payload — what a query-back
    proof should find. Metric name = <measurement>_<field>; field strings never
    contain spaces (values are numeric), so splitting the last two spaces off a
    line isolates them even when a tag value carries an escaped space."""
    counts = {
        "fleet_workflow_run_status": 0,
        "fleet_workflow_run_hours_since_success": 0,
        "fleet_repo_data_commit_age_hours": 0,
    }
    for line in payload.splitlines():
        measurement = line.split(",", 1)[0]
        fields = line.rsplit(" ", 2)[-2]
        for field in fields.split(","):
            name = f"{measurement}_{field.split('=', 1)[0]}"
            if name in counts:
                counts[name] += 1
    return counts


def _encode(records, timestamp):
    """encode_metrics with any residual ValueError surfaced as a clean CLI error
    instead of a traceback. (Per-record encode failures — a control char in a
    tag, a missing key — are skipped inside encode_metrics, not raised; this
    guard only catches a malformed timestamp.)"""
    try:
        return encode_metrics(records, timestamp)
    except ValueError as e:
        raise click.ClickException(str(e)) from e


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


def _harvest_now(timestamp):
    """Tz-aware anchor for the harvester's cold-start look-back: the explicit
    --timestamp (so a fixture render is deterministic), else the current UTC time.
    Only the cold-start window depends on it; entry timestamps come from the log
    lines themselves."""
    from datetime import datetime, timezone

    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _log_sources(config_dir, log_fixture, now):
    """Resolve (jurisdictions, fetch_runs, fetch_archive) for the logs leg: an
    offline fixture directory, or a live GitHub harvest of the fleet config.
    ``now`` is the harvest anchor, threaded into the live fetchers so pagination
    and selection share one clock."""
    if log_fixture is not None:
        return _load_log_fixture(log_fixture)
    if config_dir is not None:
        # Same clean-error contract as _poll_live and list-fleet: a malformed
        # config is a CLI error line, never a raw traceback.
        try:
            jurisdictions = read_fleet(config_dir)
        except (ValueError, yaml.YAMLError) as e:
            raise click.ClickException(str(e)) from e
        fetch_runs, fetch_archive = github_log_fetchers(now)
        return jurisdictions, fetch_runs, fetch_archive
    raise click.ClickException(
        "pass --config-dir (live harvest) or --log-fixture (offline) for logs"
    )


def _load_log_fixture(directory):
    """Build offline fetchers from a fixture directory: ``jurisdictions.jsonl``,
    ``runs/<org>__<repo>__<workflow>.json`` listings, and ``archives/<run_id>/*.txt``
    per-job logs (zipped on the fly to stand in for a real GitHub log archive)."""
    jurisdictions = [
        json.loads(line)
        for line in (directory / "jurisdictions.jsonl").read_text().splitlines()
        if line.strip()
    ]

    def fetch_runs(org, repo, workflow):
        listing = directory / "runs" / f"{org}__{repo}__{workflow}.json"
        return json.loads(listing.read_text()) if listing.exists() else []

    def fetch_archive(org, repo, run_id):
        run_dir = directory / "archives" / str(run_id)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for text_file in sorted(run_dir.glob("*.txt")):
                archive.writestr(text_file.name, text_file.read_text())
        return buffer.getvalue()

    return jurisdictions, fetch_runs, fetch_archive


def _collect_logs(config_dir, log_fixture, watermark_file, dry_run, now):
    """Harvest new-run logs and print (dry-run) or push them to Loki. Returns the
    per-repo harvest errors so ``collect`` can turn them into a nonzero exit while
    ``run`` keeps them green.

    Per-repo harvest errors are logged to stderr but never raise here — one bad
    repo must not abort the sweep, the same contract the poller keeps. An empty
    payload (no run newer than the watermark) ships nothing and stays green: that
    is the idempotent steady state.

    Pushes go **per workflow**, one payload per watermark entry, and each
    watermark advances only after its own payload lands — so one un-pushable
    payload (an oversized recovery sweep hitting the endpoint's size limit, say)
    fails only its own workflow's logs and holds only its own watermark, instead
    of blocking the whole fleet's logs and boundaries every sweep until the runs
    age out of the look-back. Watermarks that advanced with nothing to push (all
    new runs empty after filtering) advance unconditionally. Any failed push
    still exits nonzero after the rest have shipped and their watermarks saved —
    a red run means the collector needs attention, but it never un-ships the
    fleet's progress.
    """
    jurisdictions, fetch_runs, fetch_archive = _log_sources(config_dir, log_fixture, now)
    watermarks = load_watermarks(watermark_file) if watermark_file else {}
    batches, new_watermarks, errors = harvest_logs(
        jurisdictions, watermarks, fetch_runs, fetch_archive, now
    )
    for error in errors:
        click.echo(f"log harvest error: {error}", err=True)

    if dry_run:
        click.echo(encode_logs(batches))
        return errors

    from logs_push import push_logs

    by_key = {}
    for batch in batches:
        by_key.setdefault(batch["watermark_key"], []).append(batch)
    saved = dict(watermarks)
    push_errors = []
    for key in sorted(by_key):
        try:
            push_logs(encode_logs(by_key[key]))
        except RuntimeError as e:
            push_errors.append(f"{key}: {e}")
            continue
        saved[key] = new_watermarks[key]
    for key, value in new_watermarks.items():
        if key not in by_key:  # advanced with nothing to push
            saved[key] = value
    if watermark_file is not None:
        save_watermarks(watermark_file, saved)

    if by_key:
        shipped = len(by_key) - len(push_errors)
        click.echo(f"pushed logs for {shipped} of {len(by_key)} workflows", err=True)
    for error in push_errors:
        click.echo(f"log push error: {error}", err=True)
    if push_errors:
        raise click.ClickException(
            f"log push failed for {len(push_errors)} of {len(by_key)} workflows"
        )
    return errors


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
    pushed_at = int(time.time())
    payload = _encode(records, pushed_at)
    if not payload:
        raise click.ClickException("nothing to push: payload is empty")
    _push(payload)

    credentials = f"{os.environ['GRAFANA_QUERY_USER']}:{os.environ['GRAFANA_QUERY_KEY']}"
    auth = {"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}
    deadline = time.monotonic() + 60
    for metric, want in _expected_series(payload).items():
        if want == 0:
            # Legitimately absent from this payload (e.g. a bootstrapped fleet
            # where nothing has succeeded yet) — nothing to prove, not a failure.
            click.echo(f"· live check: {metric} absent from this payload, skipped")
            continue
        while True:
            # timestamp(<metric>) returns each series' raw sample time, so the
            # proof only accepts samples stamped at/after THIS run's payload
            # timestamp — a previous push inside Prometheus's 5-minute instant
            # lookback can't satisfy it. The count must reach what this payload
            # shipped: a partially ingested push (some series rejected) fails.
            query = urllib.parse.urlencode({"query": f"timestamp({metric})"})
            result = request_json(
                f"{os.environ['GRAFANA_QUERY_URL'].rstrip('/')}/api/v1/query?{query}",
                headers=auth,
            )
            series = result.get("data", {}).get("result", [])
            fresh = [s for s in series if float(s["value"][1]) >= pushed_at]
            if len(fresh) >= want:
                click.echo(
                    f"✓ live check: {len(fresh)}/{want} {metric} series from this push queryable"
                )
                break
            if time.monotonic() >= deadline:
                raise click.ClickException(
                    f"push succeeded but {metric} has {len(fresh)} of {want} expected "
                    "fresh series after 60s"
                )
            time.sleep(5)
    if errored:
        # The proof ran, but a degraded sweep must never look like a clean one.
        raise click.ClickException(f"poll errors on {len(errored)} of {len(records)} repos")


@cli.command("probe-loki")
def probe_loki():
    """Probe the Loki ingest window: push one line per age (1–24 h old), report
    which the endpoint accepts, and skip without credentials.

    The logs risk the PRD flags first: an hourly collector ships logs from runs
    that finished hours earlier, and Loki rejects entries older than its ingest
    window. This retires that risk empirically before trusting event-time
    timestamps — each age is its own push, so a rejected age (Loki answers HTTP
    400, "entry too far behind") is isolated to that age, not the whole batch. It
    writes ~24 throwaway lines under a ``probe`` label (not a fleet label), so it
    is safe to run against the real stack. Needs GRAFANA_LOGS_{URL,USER,KEY};
    exits 0 with a skip notice otherwise, so a credential-free CI run passes.
    """
    import os
    import time

    names = ["GRAFANA_LOGS_URL", "GRAFANA_LOGS_USER", "GRAFANA_LOGS_KEY"]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        click.echo(f"loki probe skipped: missing {', '.join(missing)}")
        return

    from http_util import RequestFailed
    from logs_push import push_logs

    now = time.time()
    accepted, rejected, setup_failed, transient = [], [], [], []
    for hours in range(1, 25):
        timestamp_ns = int((now - hours * 3600) * 1_000_000_000)
        payload = json.dumps({
            "streams": [{
                "stream": {"probe": "ingest_window", "age_hours": str(hours)},
                "values": [[str(timestamp_ns), f"fleet-monitor ingest-window probe, {hours}h old"]],
            }]
        })
        try:
            push_logs(payload)
            accepted.append(hours)
            click.echo(f"✓ {hours:>2}h old: accepted")
        except RequestFailed as e:
            # Only HTTP 400 is evidence about the ingest window — that is Loki
            # refusing the entry itself ("too far behind"). Any other fail-fast
            # 4xx (401/403 bad key, 413 too large, 429 quota) is a probe-setup
            # problem, and a retries-exhausted 5xx/network failure (status None)
            # is transient — neither may masquerade as an age rejection, or a
            # bad credential would print "adopt the fallback" for every age.
            if e.status == 400:
                rejected.append(hours)
                click.echo(f"✗ {hours:>2}h old: rejected (HTTP 400)")
            elif e.status is not None:
                setup_failed.append(hours)
                click.echo(f"! {hours:>2}h old: probe setup failure (HTTP {e.status}) — "
                           "check credentials/endpoint, not the ingest window")
            else:
                transient.append(hours)
                click.echo(f"? {hours:>2}h old: push failed ({e}) — transient, not an age rejection")
    if setup_failed:
        click.echo(
            f"setup failures at {len(setup_failed)} age(s); fix the credentials/endpoint "
            "and re-run — these say nothing about the ingest window."
        )
    if transient:
        click.echo(
            f"transient failures at {len(transient)} age(s) "
            f"({', '.join(f'{h}h' for h in transient)}); re-run the probe for a clean read."
        )
    if rejected:
        click.echo(
            f"ingest window rejects entries ≥ {min(rejected)}h old; the harvester's "
            "24h look-back would lose the oldest recovered logs — adopt the "
            "ship-at-collection-time fallback (README 'Logs')."
        )
    elif not setup_failed and not transient:
        click.echo(f"ingest window accepts all of 1–24h old ({len(accepted)}/24); "
                   "event-time timestamps are safe within the harvester's look-back.")


if __name__ == "__main__":
    cli(auto_envvar_prefix="FLEET_MONITOR")
