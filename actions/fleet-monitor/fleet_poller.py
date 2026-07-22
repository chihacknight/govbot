"""Poll GitHub for each fleet repo's run status and data freshness.

All GitHub REST knowledge lives here. Input is jurisdiction records from
fleet_config.read_fleet; output is one plain poller record per repo, shaped by
schemas/fleet-poller-record.schema.json (validated on every snapshot render):

    {
        "fleet": str, "config": str,      # lineage from the jurisdiction record
        "state": str, "org": str, "repo": str, "paused": bool,
        "polled_at": str,                 # ISO 8601 UTC fetch time
        "workflows": [
            {"workflow": str,             # file name, e.g. "openstates-scrape.yml"
             "latest_conclusion": str|None,   # of the latest *completed* run
             "hours_since_success": float|None},
        ],
        "data_commit_age_hours": float|None,
        "errors": [str],              # per-repo failures land here, never raise
    }

Per-repo failures are recorded on the record and skipped — one bad repo must
never abort the fleet sweep. An unknown base template, by contrast, is a
config gap and fails the whole sweep before any polling starts. API usage is
deliberately conservative: only single-page queries, so a full sweep costs 2
requests per expected workflow (recent runs + latest successful run) plus 1
per repo for the data-path commit; repos are polled concurrently but bounded
(MAX_CONCURRENCY) to stay inside GitHub's secondary-rate-limit etiquette.
estimate_request_count() documents the arithmetic; render-snapshots.sh asserts
it stays in the low hundreds for the real fleet. GITHUB_TOKEN is required for
live sweeps (enforced by the CLI): one sweep costs ~336 requests against an
unauthenticated limit of 60/hour.
"""

import os
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from http_util import RequestFailed, request_json

GITHUB_API = "https://api.github.com"
MAX_CONCURRENCY = 8

# Where fresh data lands in each repo, by *base* template (the -paused suffix
# is fleet_config's convention; records carry base_template so this map never
# duplicates it). Scraper repos commit raw scraped JSON under _data/<locale>/
# (actions/scrape); data repos commit the formatted OCD tree under country:us/
# (actions/format).
DATA_PATHS = {
    "openstates-scrape": "_data/{state}",
    "openstates-to-ocd-files": "country:us",
}


def _github_fetcher():
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return lambda url: request_json(url, headers=headers)


def _hours_since(iso_timestamp, now):
    then = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return round((now - then).total_seconds() / 3600, 2)


def _runs_url(org, repo, workflow, **params):
    query = urllib.parse.urlencode({"per_page": 1, "exclude_pull_requests": "true", **params})
    workflow = urllib.parse.quote(workflow, safe="")
    return f"{GITHUB_API}/repos/{org}/{repo}/actions/workflows/{workflow}/runs?{query}"


def _poll_workflow(jurisdiction, workflow, fetch_json, now):
    # The three most recent runs, unfiltered, and the conclusion comes from the
    # most recent *completed* one — so active runs (conclusion null) never mask
    # the last finished conclusion; per_page=3 keeps a completed run in the
    # window even with a run in progress and another queued behind it.
    # Deliberately NOT the status=completed filter: that filtered index
    # intermittently returns an empty page with HTTP 200 (observed live, ~5/112
    # workflows in one sweep), silently dropping status samples; the unfiltered
    # listing is the primary index. Still one page, so the request arithmetic
    # is unchanged.
    latest_runs = fetch_json(
        _runs_url(jurisdiction["org"], jurisdiction["repo"], workflow, per_page=3)
    ).get("workflow_runs", [])
    success_runs = fetch_json(
        _runs_url(jurisdiction["org"], jurisdiction["repo"], workflow, status="success")
    ).get("workflow_runs", [])
    completed = next((run for run in latest_runs if run.get("status") == "completed"), {})
    success = success_runs[0] if success_runs else None
    if success is None:
        # The status=success filtered index can flake empty with HTTP 200 (same
        # index class as status=completed, observed live); fall back to a
        # success visible in the unfiltered page. If neither shows one, null
        # stands: a never-succeeded workflow and a flaked old success are
        # indistinguishable without extra requests, and recording an error
        # would false-alarm every legitimately never-succeeded workflow.
        success = next((run for run in latest_runs if run.get("conclusion") == "success"), None)
    return {
        "workflow": workflow,
        "latest_conclusion": completed.get("conclusion"),
        "hours_since_success": _hours_since(success["updated_at"], now) if success else None,
    }


def _poll_data_commit(jurisdiction, fetch_json, now):
    path = DATA_PATHS[jurisdiction["base_template"]].format(state=jurisdiction["state"])
    query = urllib.parse.urlencode({"per_page": 1, "path": path})
    try:
        commits = fetch_json(
            f"{GITHUB_API}/repos/{jurisdiction['org']}/{jurisdiction['repo']}/commits?{query}"
        )
    except RequestFailed as e:
        if e.status == 409:  # "Git Repository is empty" — no commits yet, not an error
            return None
        raise
    if not commits:
        return None
    return _hours_since(commits[0]["commit"]["committer"]["date"], now)


def _poll_repo(jurisdiction, fetch_json, now):
    record = {
        "fleet": jurisdiction["fleet"],
        "config": jurisdiction["config"],
        "state": jurisdiction["state"],
        "org": jurisdiction["org"],
        "repo": jurisdiction["repo"],
        "paused": jurisdiction["paused"],
        "polled_at": now.isoformat(),
        "workflows": [],
        "data_commit_age_hours": None,
        "errors": [],
    }
    for workflow in jurisdiction["expected_workflows"]:
        try:
            record["workflows"].append(_poll_workflow(jurisdiction, workflow, fetch_json, now))
        except Exception as e:
            record["errors"].append(str(e))
    try:
        record["data_commit_age_hours"] = _poll_data_commit(jurisdiction, fetch_json, now)
    except Exception as e:
        record["errors"].append(str(e))
    return record


def poll_fleet(jurisdictions, fetch_json=None, now=None):
    """Return one poller record per jurisdiction record, never raising per-repo.

    ``fetch_json(url) -> parsed JSON`` defaults to a live GitHub client using
    GITHUB_TOKEN from the environment when present; injectable for tests (it
    is called from worker threads, so an injected fake must be thread-safe).
    ``now`` (ISO 8601 string or datetime, default: current UTC time) anchors
    the age arithmetic and is stamped on every record as ``polled_at``.

    Raises ValueError before any polling when a jurisdiction's base_template
    has no DATA_PATHS entry — that is a config gap, not a per-repo failure.
    Repos are polled concurrently (bounded by MAX_CONCURRENCY); the returned
    list keeps the input order.
    """
    fetch_json = fetch_json or _github_fetcher()
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))

    unknown = sorted({j["base_template"] for j in jurisdictions} - DATA_PATHS.keys())
    if unknown:
        raise ValueError(
            f"no data path known for base template(s) {', '.join(unknown)}; "
            "add them to fleet_poller.DATA_PATHS"
        )

    if not jurisdictions:
        return []
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENCY, len(jurisdictions))) as pool:
        return list(pool.map(lambda j: _poll_repo(j, fetch_json, now), jurisdictions))


def estimate_request_count(jurisdictions):
    """GitHub API requests one full sweep costs: 2 per workflow + 1 per repo."""
    return sum(2 * len(j["expected_workflows"]) + 1 for j in jurisdictions)
