"""Harvest workflow-run logs GitHub hasn't been shipped before, as labeled batches.

The logs counterpart to fleet_poller: all GitHub-logs REST knowledge lives here.
Each hourly sweep ships only runs newer than the per-(repo, workflow) watermark
(watermark.py), so re-running an unchanged window ships nothing. For every new
*completed* run it downloads the log archive, unpacks the per-job logs, parses the
RFC 3339 timestamp GitHub prefixes on every line, drops known-noise lines, and
applies a volume policy — full logs for a failed/cancelled run, the last ~100
lines for a success — then groups the result into batches labeled
``org``/``state``/``workflow``/``outcome`` for logs_shipper.

Three rules keep the watermark honest against partial progress:

- Runs are shipped in ascending id order and the watermark advances only across
  *contiguous* shipped runs. The first run that can't be shipped this sweep — one
  still in progress, or one whose archive fetch failed — halts advancement, so it
  is retried next sweep rather than skipped forever. (Run ids are monotonic in
  creation order, so id ordering is creation ordering.)
- The watermark is keyed per (repo, *workflow*), not per repo: each workflow's run
  stream is independent, so an in-progress run in one workflow never blocks
  shipping another workflow's completed runs.
- The look-back window bounds *every* sweep, not just a cold start: only runs
  created within the last LOOKBACK_HOURS are candidates, and the live run listing
  pages just far enough to cover that window (MAX_RUN_PAGES cap). Selection and
  fetching therefore agree on the same boundary — the watermark can never advance
  past a run that pagination didn't fetch, because a run outside the window is
  outside the contract for both. The trade, same as the cold-start rule: a
  collector outage longer than a day loses the overflow, by the same budget
  rationale, and loses it *by policy* rather than by a silent page cutoff.

Timestamps: an hourly collector ships logs from runs that finished up to an hour
(or, on a cold cache, a day) earlier. Loki rejects samples older than its ingest
window, so the ingest-window behavior is probed before trusting event-time
timestamps — see README "Logs: harvester + shipper" for the probe and the chosen
strategy. Each entry preserves the run's original event time; the shipper carries
run/job identity in structured metadata, never labels.
"""

import os
import re
import urllib.parse
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO

from http_util import request_json, request_with_retry

GITHUB_API = "https://api.github.com"

# The harvest window: only runs created within the last LOOKBACK_HOURS ship, on
# every sweep (see module docstring). Run listings page RUNS_PER_PAGE at a time,
# stopping as soon as a page dips past the window (or runs short), capped at
# MAX_RUN_PAGES — 120 runs per workflow per day before the cap bites, ~10× the
# busiest hourly workflow. Hourly cadence means page 1 almost always suffices;
# the cap only matters recovering from a long collector outage.
LOOKBACK_HOURS = 24
RUNS_PER_PAGE = 30
MAX_RUN_PAGES = 4

# Outcomes whose full logs we keep — the ones an operator debugs. Deliberately
# wider than the task's named "failed/cancelled": timed_out and startup_failure
# are equally debuggable failures, and they are rare enough that the log-volume
# budget (README Budgets) is unaffected. Everything else (a success) is tailed to
# the last SUCCESS_TAIL lines: proof it ran, not a transcript.
FULL_LOG_OUTCOMES = frozenset({"failure", "cancelled", "timed_out", "startup_failure"})
SUCCESS_TAIL = 100

# RFC 3339 with an optional fractional part and a literal Z, the exact form GitHub
# prefixes on every Actions log line (fractional part is up to 9 digits — more
# than datetime.fromisoformat accepts, so it is parsed by hand).
_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z$")


def _to_ns(token: str):
    """Epoch nanoseconds for a GitHub log timestamp token, or None if it isn't one."""
    match = _TIMESTAMP.match(token)
    if not match:
        return None
    when = datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
    nanoseconds = int(when.timestamp()) * 1_000_000_000
    fraction = match.group(2)
    if fraction:
        nanoseconds += int((fraction + "000000000")[:9])
    return nanoseconds


def unpack_archive(archive_bytes: bytes):
    """The per-job log texts in a run's log archive, as ``(name, text)`` sorted by
    name. GitHub's zip carries each job's full log at the top level (``N_job.txt``)
    and duplicates it split by step under a ``job/`` folder; we read only the
    top-level per-job files so no line is counted twice."""
    texts = []
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        for name in archive.namelist():
            if "/" in name or not name.endswith(".txt"):
                continue
            texts.append((name, archive.read(name).decode("utf-8", errors="replace")))
    return sorted(texts, key=lambda pair: pair[0])


def parse_log_text(text: str, fallback_ns: int):
    """Parse ``(timestamp_ns, message)`` for each line of a job log.

    GitHub stamps every line ``<rfc3339> <message>``. A line without a parseable
    stamp (a wrapped continuation of the previous line) keeps its full text and
    inherits the last seen timestamp, defaulting to ``fallback_ns`` before the
    first stamp — so an unparseable line is preserved, never dropped or mis-timed
    into a different second.
    """
    lines = []
    last_ns = fallback_ns
    for raw in text.splitlines():
        head, _, rest = raw.partition(" ")
        # _to_ns alone decides: a spaceless non-timestamp line still parses to
        # None, and a bare timestamp with no trailing space is a stamp with an
        # empty message (noise-dropped), not content.
        stamp = _to_ns(head)
        if stamp is None:
            lines.append((last_ns, raw))
        else:
            last_ns = stamp
            lines.append((stamp, rest))
    return lines


def _is_noise(message: str) -> bool:
    """Drop empty lines and Actions grouping markers — structural noise with no
    diagnostic value. Kept deliberately small and conservative: real log content,
    including warnings, is never filtered."""
    stripped = message.strip()
    if not stripped:
        return True
    return stripped.startswith("##[group]") or stripped.startswith("##[endgroup]")


def apply_volume_policy(entries, outcome, tail=SUCCESS_TAIL):
    """Full logs for a debuggable outcome (failure/cancelled/timed out); the last
    ``tail`` lines for anything else. Absence of a transcript for a green run is
    the budget trade the README documents."""
    if outcome in FULL_LOG_OUTCOMES:
        return entries
    return entries[-tail:]


def harvest_run(run, archive_bytes, now):
    """Labeled entries for one run's logs: unpack → parse → drop noise → apply the
    volume policy. Each entry carries the run's identity (id, url) in metadata, not
    labels. Unstamped lines fall back to the run's creation time (or ``now``)."""
    created_ns = _to_ns(run.get("created_at") or "")
    fallback_ns = created_ns if created_ns is not None else int(now.timestamp()) * 1_000_000_000
    parsed = []
    for _name, text in unpack_archive(archive_bytes):
        for stamp, message in parse_log_text(text, fallback_ns):
            if not _is_noise(message):
                parsed.append((stamp, message))
    parsed = apply_volume_policy(parsed, run.get("conclusion"))
    metadata = {"run_id": str(run["id"])}
    if run.get("html_url"):
        metadata["run_url"] = run["html_url"]
    return [{"timestamp_ns": stamp, "line": message, "metadata": metadata} for stamp, message in parsed]


def _select_new(runs, last_id, cutoff_ns):
    """New runs in ascending id order: id past the watermark AND created within
    the look-back window. The window applies on every sweep, not just a cold
    start (module docstring, third rule): it is what lets a lost cache recover
    the last day instead of the full history, and what guarantees selection
    never wants a run the paged listing didn't fetch."""
    selected = []
    for run in sorted(runs, key=lambda r: r["id"]):
        if run["id"] <= last_id:
            continue
        created_ns = _to_ns(run.get("created_at") or "")
        if created_ns is None or created_ns < cutoff_ns:
            continue
        selected.append(run)
    return selected


def _bad_label(value) -> bool:
    """A label value the shipper would reject (control characters). Checked at
    harvest time so a bad label surfaces as a per-repo error that HOLDS the
    watermark — if it were left for encode_logs to drop, the batch would vanish
    after the watermark had already advanced, losing those logs permanently."""
    return any(c in str(value) for c in "\n\r")


def harvest_logs(jurisdictions, watermarks, fetch_runs, fetch_archive, now,
                 lookback_hours=LOOKBACK_HOURS):
    """Harvest new-run logs across the fleet as labeled batches.

    ``fetch_runs(org, repo, workflow) -> [run]`` and
    ``fetch_archive(org, repo, run_id) -> bytes`` are injectable (live GitHub by
    default via ``github_log_fetchers``; fakes in tests). ``watermarks`` maps
    ``"<org>/<repo>/<workflow>"`` to the last shipped run id. ``now`` is a
    tz-aware datetime anchoring the cold-start look-back.

    Returns ``(batches, new_watermarks, errors)``. Never raises per repo: a failed
    run listing or archive fetch is recorded in ``errors`` and skipped, exactly as
    the poller records a per-repo failure — one bad repo never aborts the sweep.
    """
    cutoff_ns = int((now - timedelta(hours=lookback_hours)).timestamp()) * 1_000_000_000
    grouped = {}
    new_watermarks = dict(watermarks)
    errors = []
    for jurisdiction in jurisdictions:
        org, state, repo = jurisdiction["org"], jurisdiction["state"], jurisdiction["repo"]
        for workflow in jurisdiction["expected_workflows"]:
            key = f"{org}/{repo}/{workflow}"
            if any(_bad_label(value) for value in (org, state, workflow)):
                # The shipper would drop this batch; erroring here instead keeps
                # the watermark untouched, so nothing is marked shipped that never
                # made it into a payload.
                errors.append(f"{org}/{repo} {workflow}: control character in label value")
                continue
            last_id = watermarks.get(key, 0)
            try:
                runs = fetch_runs(org, repo, workflow)
            except Exception as error:
                errors.append(f"{org}/{repo} {workflow}: {error}")
                continue
            candidate = last_id
            for run in _select_new(runs, last_id, cutoff_ns):
                if run.get("status") != "completed" or run.get("conclusion") is None:
                    # An active run: stop advancing so it is retried once complete,
                    # rather than skipped when the watermark passes its id.
                    break
                if _bad_label(run["conclusion"]):
                    # Same rule as above, per run: a label the shipper would
                    # reject must hold the watermark, not silently lose the run.
                    errors.append(f"{org}/{repo} run {run['id']}: control character in outcome")
                    break
                try:
                    entries = harvest_run(run, fetch_archive(org, repo, run["id"]), now)
                except Exception as error:
                    # Couldn't ship this run's logs — hold the watermark below it so
                    # the next sweep retries it instead of stepping over it.
                    errors.append(f"{org}/{repo} run {run['id']}: {error}")
                    break
                if entries:
                    grouped.setdefault((org, state, workflow, run["conclusion"]), []).extend(entries)
                candidate = run["id"]
            if candidate > 0:
                new_watermarks[key] = candidate
    batches = [
        {"labels": {"org": org, "state": state, "workflow": workflow, "outcome": outcome},
         "entries": entries}
        for (org, state, workflow, outcome), entries in sorted(grouped.items())
    ]
    return batches, new_watermarks, errors


def github_log_fetchers():
    """Live GitHub fetchers for run listings and log archives, authenticated with
    GITHUB_TOKEN when present (public reads work without it, at a lower rate limit).
    Mirrors fleet_poller's header construction; the archive endpoint 302-redirects
    to a zip, which urllib follows, so request_with_retry returns the zip bytes.

    The run listing pages until it has covered the harvest window: it stops as
    soon as a page runs short (no more runs) or its oldest run predates the
    look-back boundary (everything older is outside _select_new's contract
    anyway), capped at MAX_RUN_PAGES. Page 1 suffices on a normal hourly sweep;
    the extra pages only exist so a burst of more than one page of new runs
    can't leave a gap the watermark then leaps over.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def fetch_runs(org, repo, workflow):
        # One hour of slack past the look-back so a run created right at the
        # boundary is fetched by the same sweep that would select it.
        boundary = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS + 1)
        boundary_ns = int(boundary.timestamp()) * 1_000_000_000
        workflow = urllib.parse.quote(workflow, safe="")
        runs = []
        for page in range(1, MAX_RUN_PAGES + 1):
            query = urllib.parse.urlencode(
                {"per_page": RUNS_PER_PAGE, "exclude_pull_requests": "true", "page": page}
            )
            url = f"{GITHUB_API}/repos/{org}/{repo}/actions/workflows/{workflow}/runs?{query}"
            page_runs = request_json(url, headers=headers).get("workflow_runs", [])
            runs.extend(page_runs)
            if len(page_runs) < RUNS_PER_PAGE:
                break
            oldest = min((_to_ns(run.get("created_at") or "") or 0) for run in page_runs)
            if oldest < boundary_ns:
                break
        return runs

    def fetch_archive(org, repo, run_id):
        return request_with_retry(
            f"{GITHUB_API}/repos/{org}/{repo}/actions/runs/{run_id}/logs", headers=headers
        )

    return fetch_runs, fetch_archive
