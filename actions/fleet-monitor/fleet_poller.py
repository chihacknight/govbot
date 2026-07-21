"""Poll GitHub for each fleet repo's run status and data freshness.

All GitHub REST knowledge lives here. Input is jurisdiction records from
fleet_config.read_fleet; output is one plain poller record per repo:

    {
        "fleet": str, "state": str, "org": str, "repo": str, "paused": bool,
        "workflows": [
            {"workflow": str,             # file name, e.g. "openstates-scrape.yml"
             "latest_conclusion": str|None,   # None while a run is in progress
             "latest_status": str|None,       # None when the workflow never ran
             "hours_since_success": float|None},
        ],
        "data_commit_age_hours": float|None,
        "errors": [str],              # per-repo failures land here, never raise
    }

Per-repo failures are recorded on the record and skipped — one bad repo must
never abort the fleet sweep. API usage is deliberately conservative: only
per_page=1 queries, so a full sweep costs 2 requests per expected workflow
(latest run + latest successful run) plus 1 per repo with a known data path.
estimate_request_count() documents that arithmetic; render-snapshots.sh
asserts it stays in the low hundreds for the real fleet, inside the default
GITHUB_TOKEN budget of 1000 requests/hour/repo.
"""

import os
import urllib.parse
from datetime import datetime, timezone

from http_util import request_json

GITHUB_API = "https://api.github.com"

# Where fresh data lands in each repo, by pipeline-manager template.
# Scraper repos commit raw scraped JSON under _data/<locale>/ (actions/scrape);
# data repos commit the formatted OCD tree under country:us/ (actions/format).
DATA_PATHS = {
    "openstates-scrape": "_data/{state}",
    "openstates-scrape-paused": "_data/{state}",
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
    return f"{GITHUB_API}/repos/{org}/{repo}/actions/workflows/{workflow}/runs?{query}"


def _poll_workflow(jurisdiction, workflow, fetch_json, now):
    latest_runs = fetch_json(
        _runs_url(jurisdiction["org"], jurisdiction["repo"], workflow)
    ).get("workflow_runs", [])
    success_runs = fetch_json(
        _runs_url(jurisdiction["org"], jurisdiction["repo"], workflow, status="success")
    ).get("workflow_runs", [])
    latest = latest_runs[0] if latest_runs else {}
    success = success_runs[0] if success_runs else None
    return {
        "workflow": workflow,
        "latest_conclusion": latest.get("conclusion"),
        "latest_status": latest.get("status"),
        "hours_since_success": _hours_since(success["updated_at"], now) if success else None,
    }


def _poll_data_commit(jurisdiction, fetch_json, now):
    path = DATA_PATHS[jurisdiction["template"]].format(state=jurisdiction["state"])
    query = urllib.parse.urlencode({"per_page": 1, "path": path})
    commits = fetch_json(
        f"{GITHUB_API}/repos/{jurisdiction['org']}/{jurisdiction['repo']}/commits?{query}"
    )
    if not commits:
        return None
    return _hours_since(commits[0]["commit"]["committer"]["date"], now)


def poll_fleet(jurisdictions, fetch_json=None, now=None):
    """Return one poller record per jurisdiction record, never raising per-repo.

    ``fetch_json(url) -> parsed JSON`` defaults to a live GitHub client using
    GITHUB_TOKEN from the environment when present; injectable for tests.
    ``now`` (ISO 8601 string or datetime, default: current UTC time) anchors
    the age arithmetic.
    """
    fetch_json = fetch_json or _github_fetcher()
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))

    records = []
    for jurisdiction in jurisdictions:
        record = {
            "fleet": jurisdiction.get("fleet"),
            "state": jurisdiction["state"],
            "org": jurisdiction["org"],
            "repo": jurisdiction["repo"],
            "paused": jurisdiction["paused"],
            "workflows": [],
            "data_commit_age_hours": None,
            "errors": [],
        }
        for workflow in jurisdiction["expected_workflows"]:
            try:
                record["workflows"].append(_poll_workflow(jurisdiction, workflow, fetch_json, now))
            except Exception as e:
                record["errors"].append(str(e))
        if jurisdiction["template"] in DATA_PATHS:
            try:
                record["data_commit_age_hours"] = _poll_data_commit(jurisdiction, fetch_json, now)
            except Exception as e:
                record["errors"].append(str(e))
        else:
            record["errors"].append(
                f"no data path known for template {jurisdiction['template']!r}; "
                "add it to fleet_poller.DATA_PATHS"
            )
        records.append(record)
    return records


def estimate_request_count(jurisdictions):
    """GitHub API requests one full sweep costs: 2/workflow + 1/repo with a data path."""
    return sum(
        2 * len(j["expected_workflows"]) + (1 if j["template"] in DATA_PATHS else 0)
        for j in jurisdictions
    )
