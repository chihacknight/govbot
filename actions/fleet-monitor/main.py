import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import click
import yaml

sys.path.append(str(Path(__file__).parent))

from dashboard import DASHBOARD_PATH, encode_dashboard
from fleet_config import EXCLUDED_FLEETS, read_fleet
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
@click.option(
    "--exclude-fleet",
    "exclude_fleets",
    multiple=True,
    default=EXCLUDED_FLEETS,
    show_default=True,
    help="Fleet config stem to skip (repeatable). Pass --exclude-fleet= to monitor every "
         "fleet discovery finds, including non-production ones.",
)
def collect(config_dir, metrics_only, logs_only, dry_run, poller_records, log_fixture,
            watermark_file, timestamp, exclude_fleets):
    """Poll the fleet and push (or print) Grafana Cloud metric and/or log payloads.

    Both legs share collect's exit contract — a degraded sweep must never look
    like a clean one: the metrics leg exits 1 when any repo had poll errors, and
    the logs leg exits 1 when any repo's harvest erred or a push failed. Partial
    data still ships (or prints) first — in combined mode each leg runs to
    completion regardless of the other's failure (metrics first, mirroring
    ``run``), and the failures merge into one exit-1 message at the end. An
    *empty* log sweep, though — no run newer than the watermark — is the
    idempotent steady state and exits 0: nothing was degraded, there was simply
    nothing new.
    """
    if not (metrics_only or logs_only):
        raise click.ClickException("pass --metrics-only and/or --logs-only")
    failures = []
    if metrics_only:
        try:
            _collect_metrics(config_dir, poller_records, dry_run, timestamp,
                             exclude_fleets)
        except click.ClickException as e:
            failures.append(e.message)
    if logs_only:
        try:
            log_errors = _collect_logs(config_dir, log_fixture, watermark_file, dry_run,
                                       _harvest_now(timestamp), exclude_fleets)
            if log_errors:
                failures.append(f"log harvest errors on {len(log_errors)} target(s)")
        except click.ClickException as e:
            failures.append(e.message)
    if failures:
        raise click.ClickException("; ".join(failures))


def _collect_metrics(config_dir, poller_records, dry_run, timestamp, exclude_fleets):
    """collect's metrics leg: poll, encode, ship (or print). Raises ClickException
    on poll errors — after shipping what it has — so the caller decides whether
    that failure stands alone or merges with the logs leg's."""
    records = _load_records(config_dir, poller_records, exclude_fleets)

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
    if errored:
        raise click.ClickException(f"poll errors on {len(errored)} of {len(records)} repos")


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
@click.option(
    "--exclude-fleet",
    "exclude_fleets",
    multiple=True,
    default=EXCLUDED_FLEETS,
    show_default=True,
    help="Fleet config stem to skip (repeatable). Pass --exclude-fleet= to monitor every "
         "fleet discovery finds, including non-production ones.",
)
def run(config_dir, dry_run, poller_records, log_fixture, watermark_file, timestamp,
        exclude_fleets):
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
    records = _load_records(config_dir, poller_records, exclude_fleets)

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
                      _harvest_now(timestamp), exclude_fleets)


def _load_records(config_dir, poller_records, exclude_fleets=EXCLUDED_FLEETS):
    """Records for a sweep: a pre-built --poller-records fixture (offline) or a
    live poll of --config-dir. Shared by ``collect`` and ``run``."""
    if poller_records is not None:
        return [
            json.loads(line)
            for line in poller_records.read_text().splitlines()
            if line.strip()
        ]
    if config_dir is not None:
        return _poll_live(config_dir, exclude_fleets)
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


def _poll_live(config_dir, exclude_fleets=EXCLUDED_FLEETS):
    """Read the fleet config and poll GitHub for every repo's current state."""
    import os

    if not os.environ.get("GITHUB_TOKEN"):
        raise click.ClickException(
            "GITHUB_TOKEN is required for live polls: one sweep of the current fleet "
            "costs ~336 requests and the unauthenticated GitHub limit is 60/hour"
        )
    try:
        jurisdictions = read_fleet(config_dir, exclude_fleets)
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
    """Tz-aware anchor for the log harvester's look-back window — which bounds
    every sweep — and for the live fetchers' pagination boundary (one clock for
    both, so selection never wants a run pagination didn't fetch): the explicit
    --timestamp (so a fixture render is deterministic), else the current UTC
    time. Entry timestamps come from the log lines themselves."""
    from datetime import datetime, timezone

    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _log_sources(config_dir, log_fixture, now, exclude_fleets=EXCLUDED_FLEETS):
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
            jurisdictions = read_fleet(config_dir, exclude_fleets)
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


def _collect_logs(config_dir, log_fixture, watermark_file, dry_run, now, exclude_fleets):
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
    jurisdictions, fetch_runs, fetch_archive = _log_sources(config_dir, log_fixture, now,
                                                            exclude_fleets)
    watermarks = (
        load_watermarks(watermark_file, warn=lambda message: click.echo(message, err=True))
        if watermark_file
        else {}
    )
    batches, new_watermarks, errors = harvest_logs(
        jurisdictions, watermarks, fetch_runs, fetch_archive, now
    )
    for error in errors:
        click.echo(f"log harvest error: {error}", err=True)

    if dry_run:
        # One combined payload for reading and snapshotting; a real push sends
        # one payload per workflow (below). Same streams either way — Loki
        # derives stream identity from the labels, not the request boundaries.
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
@click.option(
    "--exclude-fleet",
    "exclude_fleets",
    multiple=True,
    default=EXCLUDED_FLEETS,
    show_default=True,
    help="Fleet config stem to skip (repeatable). Pass --exclude-fleet= to monitor every "
         "fleet discovery finds, including non-production ones.",
)
def list_fleet(config_dir: Path, exclude_fleets):
    """Print one JSON Lines jurisdiction record per locale per fleet."""
    try:
        records = read_fleet(config_dir, exclude_fleets)
    except (ValueError, yaml.YAMLError) as e:
        raise click.ClickException(str(e)) from e
    for record in records:
        click.echo(json.dumps(record, ensure_ascii=False))


@cli.command("dashboard")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help=f"Write the dashboard JSON here instead of stdout (committed at {DASHBOARD_PATH}).",
)
def dashboard(out):
    """Emit the fleet-overview dashboard JSON, ready to import into any stack.

    The dashboard is built as data (dashboard.py) and committed rendered
    (dashboards/fleet-overview.json) so it reviews as code and imports as JSON.
    Datasource references are variables, not UIDs, so the same file imports into
    any Grafana Cloud stack; nothing here is specific to the account it was
    developed against.
    """
    text = encode_dashboard()
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        click.echo(f"wrote {out}", err=True)
    else:
        click.echo(text, nl=False)


@cli.command("alerts")
@click.option(
    "--out-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Write the alerting YAML here instead of stdout (committed at alerting/).",
)
def alerts(out_dir):
    """Emit the alert rules, contact point, and notification policy as provisioning YAML.

    Built as data (alerting.py) and committed rendered (alerting/*.yaml), same
    bargain as the dashboard: reviewable as code, and regenerating it is a diff
    rather than an export from somebody's browser. Stack-specific values — the
    datasource uid, the stack URL, the Slack webhook, the alert address — are
    $PLACEHOLDERS resolved by `provision-alerts`, so the committed files carry no
    credentials and apply to any stack.
    """
    from alerting import render_documents

    documents = render_documents()
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, text in documents.items():
            (out_dir / name).write_text(text)
        click.echo(f"wrote {len(documents)} files to {out_dir}", err=True)
        return
    for name, text in documents.items():
        click.echo(f"# ===== {name} =====")
        click.echo(text, nl=False)


@cli.command("provision-alerts")
@click.option(
    "--alerting-dir",
    type=click.Path(file_okay=False, path_type=Path),
    # Relative to this module, not to the caller's cwd. The committed directory
    # is a property of the action, and `exists=True` on a cwd-relative default is
    # validated by click BEFORE the command body — so running from anywhere else
    # exited 2 with a path error instead of the documented credential-free skip.
    default=Path(__file__).parent / "alerting",
    show_default="the module's own alerting/ directory",
    help="Directory of committed alerting YAML to apply.",
)
@click.option(
    "--deadline-seconds",
    type=int,
    default=None,
    help="How long to wait for the stack to evaluate the rules (default: two evaluation "
         "intervals plus a margin). The offline suite passes 0 to poll exactly once.",
)
def provision_alerts(alerting_dir, deadline_seconds):
    """Apply the committed alert rules, contact point, and notification policy to a
    real stack; skips without credentials.

    Provisioning is the check. The committed files are read from disk (not
    re-rendered), their $PLACEHOLDERS resolved from the environment, and the
    result applied through Grafana's provisioning API — then the stack is polled
    until it has actually *evaluated* the rules, because Grafana will happily
    store a rule pointing at a datasource that does not exist and only report
    `health: error` once it tries to run it.

    Needs GRAFANA_ALERTS_URL (the stack base URL) and GRAFANA_ALERTS_KEY (a
    service-account token with alerting write), plus SLACK_WEBHOOK_URL and
    ALERT_EMAIL for the contact point. GRAFANA_METRICS_DATASOURCE_UID pins the
    datasource when a stack has more than one Prometheus; otherwise it is
    discovered. GRAFANA_DASHBOARD_URL overrides the base used in alert deep
    links, which defaults to the stack URL. Exits 0 with a skip notice when
    credentials are absent, so an offline run passes without a Grafana account.
    """
    import os

    names = ["GRAFANA_ALERTS_URL", "GRAFANA_ALERTS_KEY", "SLACK_WEBHOOK_URL", "ALERT_EMAIL"]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        click.echo(f"alert provisioning skipped: missing {', '.join(missing)}")
        return

    from alerts_provision import check_stack_url, provision

    base = os.environ["GRAFANA_ALERTS_URL"]
    deadline = {} if deadline_seconds is None else {"deadline_seconds": deadline_seconds}
    try:
        # The stack that serves the UI is the stack being provisioned unless
        # someone says otherwise, so the deep links need no second variable.
        # `or base`, not a default: an unset CI secret renders as the EMPTY
        # STRING, and an empty base makes every alert link relative — which
        # resolves against slack.com wherever the notification is read.
        #
        # Validated like the API URL when supplied: it becomes the clickable link
        # in every notification and is never contacted, so a wrong value
        # provisions cleanly and sends on-call staff elsewhere indefinitely.
        # `allow_path`: unlike the API base this one is never contacted, and a
        # reverse-proxied Grafana served under /grafana needs the prefix for its
        # links to resolve.
        dashboard_url = check_stack_url(
            os.environ.get("GRAFANA_DASHBOARD_URL") or base,
            "GRAFANA_DASHBOARD_URL",
            allow_path=True,
        )
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    # The webhook is the credential this module is most careful about everywhere
    # else, so it gets the same scheme check as the URLs above: Slack only issues
    # https hooks, and a plain-http one has Grafana re-POST the hook path itself
    # in cleartext on every alert, from its own egress where nobody will see it.
    if not os.environ["SLACK_WEBHOOK_URL"].startswith("https://"):
        raise click.ClickException("SLACK_WEBHOOK_URL must be https")
    values = {
        "SLACK_WEBHOOK_URL": os.environ["SLACK_WEBHOOK_URL"],
        "ALERT_EMAIL": os.environ["ALERT_EMAIL"],
        "GRAFANA_DASHBOARD_URL": dashboard_url,
        "GRAFANA_METRICS_DATASOURCE_UID": os.environ.get("GRAFANA_METRICS_DATASOURCE_UID", ""),
    }
    try:
        provision(alerting_dir, base, os.environ["GRAFANA_ALERTS_KEY"], values,
                  echo=click.echo, **deadline)
    except RuntimeError as e:
        # RequestFailed and UnresolvedPlaceholder are both RuntimeErrors: a
        # rejected write, a stack that can't evaluate what it stored, and a
        # placeholder nobody supplied all end the run the same way.
        raise click.ClickException(str(e)) from e


@cli.command("check-dashboard")
def check_dashboard():
    """Import the committed dashboard into a real stack and read it back; skips
    without credentials.

    A dashboard that only ever renders in the browser it was built in is not
    reproducible, so the check is the import itself: POST the JSON to the
    stack's dashboards API, then GET it by uid. The read-back matters — Grafana
    answers the push before it has stored anything renderable, and a payload it
    quietly mangles still returns 200.

    Needs GRAFANA_DASHBOARD_URL (the stack base URL) and GRAFANA_DASHBOARD_KEY
    (a service-account token with dashboards write; bearer-authed, unlike the
    Basic-auth push endpoints). Exits 0 with a skip notice otherwise, so an
    offline run passes without a Grafana account.
    """
    import os

    names = ["GRAFANA_DASHBOARD_URL", "GRAFANA_DASHBOARD_KEY"]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        click.echo(f"dashboard check skipped: missing {', '.join(missing)}")
        return

    from dashboard import DASHBOARD_UID, build_dashboard
    from http_util import RequestFailed, request_json, request_with_retry

    base = os.environ["GRAFANA_DASHBOARD_URL"].rstrip("/")
    auth = {"Authorization": f"Bearer {os.environ['GRAFANA_DASHBOARD_KEY']}"}
    board = build_dashboard()
    payload = json.dumps({
        "dashboard": board,
        # Idempotent by uid: re-running the check updates the same dashboard
        # instead of erroring on the second run or littering copies.
        "overwrite": True,
        "message": "fleet-monitor import check",
    }).encode()
    try:
        request_with_retry(
            f"{base}/api/dashboards/db",
            data=payload,
            headers={**auth, "Content-Type": "application/json"},
        )
    except RequestFailed as e:
        raise click.ClickException(f"dashboard import rejected: {e}") from e

    try:
        loaded = request_json(f"{base}/api/dashboards/uid/{DASHBOARD_UID}", headers=auth)
    except RequestFailed as e:
        raise click.ClickException(f"dashboard imported but does not load back: {e}") from e
    panels = loaded.get("dashboard", {}).get("panels", [])
    if len(panels) != len(board["panels"]):
        raise click.ClickException(
            f"dashboard loaded with {len(panels)} panels, expected {len(board['panels'])}"
        )
    # Panels alone are not proof. Every panel filters on `=~"$state"` and points
    # at `${metrics}`/`${logs}`, so a variable Grafana declined to migrate leaves
    # all five panels present and all five rendering nothing — a blank board that
    # a panel count reports as a clean import.
    stored = {
        v.get("name"): v
        for v in loaded.get("dashboard", {}).get("templating", {}).get("list", [])
    }
    want = {v["name"] for v in board["templating"]["list"]}
    if want - set(stored):
        raise click.ClickException(
            f"dashboard imported without variable(s) {', '.join(sorted(want - set(stored)))}; "
            "panels would render empty"
        )
    # Presence by name is not enough — that is precisely how the first broken
    # import passed. A picker stripped of its all-value, or repointed at the
    # wrong datasource, resolves to nothing and blanks every panel that filters
    # on it while the name sits there looking fine. Only the fields that decide
    # whether a picker resolves are compared; the query object itself is left
    # alone, since Grafana may legitimately normalise it on store.
    for variable in board["templating"]["list"]:
        landed = stored[variable["name"]]
        for field in ("allValue", "datasource"):
            if field in variable and landed.get(field) != variable[field]:
                raise click.ClickException(
                    f"variable {variable['name']} imported with {field}="
                    f"{landed.get(field)!r}, expected {variable[field]!r}; "
                    "it would resolve to nothing and blank every panel using it"
                )
    click.echo(
        f"✓ dashboard imports and loads back with all {len(panels)} panels "
        f"and {len(want)} variables"
    )


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
    """Probe the real Loki ingest window: push one line per age (1–24 h old) and
    **query each back**, reporting which ages are actually retrievable.

    The HTTP status alone lies. Grafana Cloud answers a too-old push ``204`` and
    then *silently discards* the line, so a status-only probe reports a false
    "accepted" (this is exactly what fooled an earlier version). Only a query-back
    tells the truth. This is now a diagnostic, not a launch gate: the harvester
    ships at collection time (README "Ingest window"), so correctness never depends
    on the window — the probe just characterizes the stack and validates that
    decision.

    Writes ~24 throwaway lines under a ``probe`` label (never a fleet label), each
    tagged with a per-run nonce so a re-run can't read a prior run's entries. Needs
    GRAFANA_LOGS_{URL,USER,KEY}; the token must also carry ``logs:read`` for the
    query-back. Exits 0 with a skip notice when credentials are absent, so a
    credential-free CI run passes.
    """
    import base64
    import os
    import time
    import urllib.parse

    names = ["GRAFANA_LOGS_URL", "GRAFANA_LOGS_USER", "GRAFANA_LOGS_KEY"]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        click.echo(f"loki probe skipped: missing {', '.join(missing)}")
        return

    from http_util import RequestFailed, request_json
    from logs_push import push_logs

    push_url = os.environ["GRAFANA_LOGS_URL"]
    if not push_url.endswith("/push"):
        raise click.ClickException(
            f"GRAFANA_LOGS_URL should end in /loki/api/v1/push to derive the query URL; got {push_url}"
        )
    query_url = push_url[: -len("/push")] + "/query_range"
    credentials = f"{os.environ['GRAFANA_LOGS_USER']}:{os.environ['GRAFANA_LOGS_KEY']}"
    auth = {"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}

    now = time.time()
    nonce = str(int(now * 1000))
    pushed = []
    for hours in range(1, 25):
        timestamp_ns = int((now - hours * 3600) * 1_000_000_000)
        payload = json.dumps({
            "streams": [{
                "stream": {"probe": "ingest_window", "nonce": nonce, "age_hours": str(hours)},
                "values": [[str(timestamp_ns),
                            f"fleet-monitor ingest-window probe {nonce}, {hours}h old"]],
            }]
        })
        try:
            push_logs(payload)
            pushed.append(hours)
        except RequestFailed as e:
            click.echo(f"! {hours:>2}h old: push failed (HTTP {e.status}) — "
                       "check credentials/endpoint")
    if not pushed:
        raise click.ClickException("every probe push failed; fix credentials/endpoint and re-run")

    def queryable(hours):
        query = urllib.parse.urlencode({
            "query": f'{{probe="ingest_window",nonce="{nonce}",age_hours="{hours}"}}',
            "start": str(int((now - 25 * 3600) * 1_000_000_000)),
            "end": str(int((now + 3600) * 1_000_000_000)),
            "limit": "5",
        })
        try:
            result = request_json(f"{query_url}?{query}", headers=auth)
        except RequestFailed as e:
            if e.status == 401:
                raise click.ClickException(
                    "query-back got HTTP 401 — the GRAFANA_LOGS_KEY token needs the logs:read "
                    "scope (not just logs:write) to verify what actually landed"
                ) from e
            raise click.ClickException(f"query-back failed: HTTP {e.status}") from e
        return any(stream.get("values") for stream in result.get("data", {}).get("result", []))

    # Grafana Cloud ingestion lags a push by seconds; wait for the freshest pushed
    # age to become queryable before judging the rest, so lag isn't read as a drop.
    click.echo("pushed; waiting for ingestion...", err=True)
    deadline = time.monotonic() + 45
    while not queryable(min(pushed)):
        if time.monotonic() >= deadline:
            raise click.ClickException(
                f"even the {min(pushed)}h-old entry isn't queryable after 45s — "
                "ingestion lag or a query problem; re-run"
            )
        time.sleep(5)

    retrievable, discarded = [], []
    for hours in pushed:
        if queryable(hours):
            retrievable.append(hours)
            click.echo(f"✓ {hours:>2}h old: accepted AND queryable")
        else:
            discarded.append(hours)
            click.echo(f"✗ {hours:>2}h old: pushed (204) but silently discarded")

    if discarded:
        window = max(retrievable) if retrievable else 0
        click.echo(
            f"ingest window ≈ {window}h: entries older than that are accepted then dropped "
            f"({len(discarded)} of {len(pushed)} ages). The harvester ships at collection time "
            "to stay inside it, so a short window is expected here — no action needed."
        )
    else:
        click.echo(
            f"all {len(pushed)} pushed ages (1–{max(pushed)}h) are queryable — this stack's window "
            "covers the whole look-back; collection-time stamping is belt-and-suspenders."
        )


if __name__ == "__main__":
    cli(auto_envvar_prefix="FLEET_MONITOR")
