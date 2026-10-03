#!/usr/bin/env python3
"""Daily scraper-error digest -- catches scrape failures *the same day they
happen*, instead of the weekly bill-discovery audit's multi-day flatline
window or a human stumbling onto them months later in a GitHub Actions log.

Built 2026-10-02 after a real incident: usa-legislation's scrape crashed on
an unhandled `KeyError: 'Concurrent Resolution Rejected'` in the openstates
`usa` scraper, got misclassified as H3_RATE_LIMITED by scrape.sh's failure
regex (a bare "429" false-matched a logged bill number, "HR 429" -- see
actions/scrape/scrape.sh's ERROR_SUMMARY comment), fell back to nightly data,
and the whole run still showed GREEN in GitHub's UI. Nothing paged on it:
the annotation is a ::warning::, not ::error::, GitHub doesn't notify on
warnings, and the weekly audit only flags a 7+ day bill-discovery flatline --
this run still had fallback bills, so no flatline. The gap: a per-run
failure masked by a successful fallback was invisible everywhere except the
raw Action log.

Two checks, run nightly for every CURRENTLY ACTIVE (non-paused) state --
paused states have no fresh runs to check, so including them would only add
stale noise:

  1. Failure signal: read today's entry (if any) from each scraper repo's
     committed `.windycivi/warning_history.json` (durable, PR #189; now also
     carries failure_type/error_summary, see scrape.sh). No live API calls,
     no retention risk -- same shape the weekly audit already relies on.
     Filtered through NOISE_PATTERNS below, built empirically from a real
     12-state sample (tamara-notes session, 2026-10-02), not guessed:
     self-logged WARNING lines like "no session provided, using active
     sessions" and "Duplicate entry in 'documents'" showed up as the
     overwhelming majority of warning volume on both usa and gu while
     representing zero actual problems. A failure_type of NONE, or a known
     benign out-of-session code (S1_*/S2_*), is skipped outright -- not a
     failure to report. Everything else surfaces, UNCLASSIFIED (UNKNOWN)
     included on purpose: an error the regex bucketing doesn't recognize is
     exactly what a human should see, not what gets filtered out.

  2. Runner/infra signal: a failure class the committed-file check above
     structurally cannot see, because the job never produces a
     scrape-summary.json at all. Confirmed live on fl/ma-legislation
     (2026-09-29 runs): "The job has exceeded the maximum execution time
     while awaiting a runner for 24h0m0s", then cancelled -- nothing to read
     from any committed file. This needs one live GitHub Actions API call per
     active state (same call shape as actions/fleet-monitor/fleet_poller.py)
     to catch a `cancelled`/`timed_out` conclusion or a run still not
     `completed` long after it should be.

This script lives in its own action (actions/openstates-scrape-audits/),
scoped specifically to the OpenStates-based bill scraper pipeline
(actions/scrape/, chn-openstates-scrape.yml) -- it has no visibility into
the other scraper pipelines in this repo (actions/scrape-elections/,
actions/scrape-hearings/, actions/scrape-maps/), hence the explicit
"openstates" in the name. Separate from actions/pipeline-manager/
(repo/template provisioning) -- the only functional tie to
pipeline-manager is reading its locale config (chn-openstates-scrape.yml)
for the active/paused state list, via the relative path below, not shared
ownership of any file here.

Usage: python3 daily-scraper-error-digest.py [--report-file path.md]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PIPELINE_MANAGER = REPO_ROOT / "actions" / "pipeline-manager"

SCRAPER_ORG = "govbot-openstates-scrapers"
GITHUB_API = "https://api.github.com"

# Benign by construction -- a scraper telling you what session it picked, or
# that it already has this document from an earlier page, is not a failure.
# Confirmed empirically (not guessed): these two patterns were 66/66 and 3/3
# of usa's and gu's respective warning samples on 2026-10-02, zero of which
# indicated an actual problem. Substring match against error_summary and each
# sample_warning line -- add to this list as real noise patterns turn up,
# same empirical approach as the weekly audit's gu/or/nv flatline exceptions.
NOISE_PATTERNS = [
    "no session provided, using active sessions",
    "Duplicate entry in 'documents'",
]

# failure_type values that are not failures worth a human's attention.
# NONE: the run actually succeeded. S1_*/S2_*: already-classified benign
# out-of-session codes (see scrape.sh) -- a paused/off-season state failing
# to find bills is expected, not news.
BENIGN_FAILURE_PREFIXES = ("NONE", "S1_", "S2_")

# How long a scheduled scrape run may sit before "still not completed" itself
# becomes the finding (mirrors the real fl/ma incident: a 24h runner wait).
# Deliberately generous -- the point is to catch a run that's stuck, not to
# police normal multi-hour scrapes (today's usa run alone took 2h22m).
STUCK_RUN_HOURS = 20


def fetch_raw_json(org: str, repo: str, path: str) -> dict | None:
    url = f"https://raw.githubusercontent.com/{org}/{repo}/main/{path}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  fetch error {url}: HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  fetch error {url}: {e}", file=sys.stderr)
        return None


def _github_api_get(url: str) -> dict | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  API error {url}: HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  API error {url}: {e}", file=sys.stderr)
        return None


def load_active_states() -> list[str]:
    with open(PIPELINE_MANAGER / "chn-openstates-scrape.yml") as f:
        cfg = yaml.safe_load(f)
    return sorted(
        code for code, loc in cfg["locales"].items()
        if "paused" not in loc.get("template", "")
    )


def is_noise(failure_type: str, error_summary: str, sample_warnings: list[str]) -> bool:
    # These two dimensions are independent findings, not one combined gate --
    # a run can exit 0 (failure_type NONE) while self.warning() is quietly
    # dropping bills (exactly PR #187's original MA case: "Server Error on
    # {}" for over a month, every run reporting success). Short-circuiting on
    # a benign failure_type before ever looking at the warnings would hide
    # precisely that scenario, which defeats the point of this digest.
    failure_is_benign = any(failure_type.startswith(p) for p in BENIGN_FAILURE_PREFIXES)
    if not failure_is_benign:
        return False
    # failure_type is benign -- still surface if any warning line looks real
    # (doesn't match a known-noise pattern). No warnings at all -> nothing to
    # surface.
    if not sample_warnings:
        return True
    return all(any(p in w for p in NOISE_PATTERNS) for w in sample_warnings)


def check_failure_signal(code: str, now: datetime) -> dict | None:
    wh = fetch_raw_json(SCRAPER_ORG, f"{code}-legislation", ".windycivi/warning_history.json")
    if not wh:
        return None
    # The most recent committed day, not a hardcoded "today" -- a nightly
    # cron's UTC date doesn't line up exactly with each state's own scrape
    # schedule (confirmed live: this script ran on 2026-10-03 UTC while
    # usa's most recent entry was still dated 2026-10-02). Bounded to the
    # last 2 days so a long-stale entry from a since-paused state doesn't
    # get re-surfaced as if it just happened.
    latest_date = max(wh.keys(), default=None)
    if latest_date is None:
        return None
    age_days = (now.date() - datetime.strptime(latest_date, "%Y-%m-%d").date()).days
    if age_days > 2:
        return None
    entry = wh[latest_date]
    if "failure_type" not in entry:
        # Pre-rollout entry, written before scrape.sh started recording
        # failure_type/error_summary -- absence is not itself a finding (it
        # would otherwise default to a false "UNKNOWN" for every repo until
        # each one's next scrape run picks up the updated template).
        return None
    failure_type = entry["failure_type"]
    error_summary = entry.get("error_summary", "")
    sample_warnings = entry.get("sample_warnings", [])
    if is_noise(failure_type, error_summary, sample_warnings):
        return None
    return {
        "date": latest_date,
        "failure_type": failure_type,
        "error_summary": error_summary,
        "warning_count": entry.get("warning_count", 0),
        "error_count": entry.get("error_count", 0),
    }


def check_runner_signal(code: str, now: datetime) -> dict | None:
    repo = f"{code}-legislation"
    url = (
        f"{GITHUB_API}/repos/{SCRAPER_ORG}/{repo}/actions/workflows/"
        f"openstates-scrape.yml/runs?{urllib.parse.urlencode({'per_page': 1})}"
    )
    data = _github_api_get(url)
    if not data:
        return None
    runs = data.get("workflow_runs", [])
    if not runs:
        return None
    run = runs[0]
    conclusion = run.get("conclusion")
    status = run.get("status")
    created_at = run.get("created_at")
    if conclusion in ("cancelled", "timed_out", "failure"):
        return {"status": status, "conclusion": conclusion, "html_url": run.get("html_url")}
    if status != "completed" and created_at:
        started = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        hours = (now - started).total_seconds() / 3600
        if hours >= STUCK_RUN_HOURS:
            return {
                "status": status,
                "conclusion": conclusion,
                "hours_running": round(hours, 1),
                "html_url": run.get("html_url"),
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-file", default=None)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    active_states = load_active_states()

    failure_findings = {}
    runner_findings = {}

    for i, code in enumerate(active_states, 1):
        print(f"[{i}/{len(active_states)}] {code}...", file=sys.stderr)
        finding = check_failure_signal(code, now)
        if finding:
            failure_findings[code] = finding
        runner_issue = check_runner_signal(code, now)
        if runner_issue:
            runner_findings[code] = runner_issue

    lines = [f"# Daily scraper-error digest -- {today_str}", ""]
    lines.append(f"Checked {len(active_states)} active states: {', '.join(active_states)}")
    lines.append("")

    lines.append(f"## Scrape failures today ({len(failure_findings)})")
    lines.append("")
    if failure_findings:
        for code, d in sorted(failure_findings.items()):
            lines.append(f"- ⚠️ **{code}** ({d['date']}): `{d['failure_type']}` -- {d['error_summary'] or '(no error text captured)'}")
            lines.append(f"  - {d['warning_count']} warnings, {d['error_count']} errors")
    else:
        lines.append("None.")
    lines.append("")

    lines.append(f"## Runs that never completed / got stuck ({len(runner_findings)})")
    lines.append("")
    if runner_findings:
        for code, d in sorted(runner_findings.items()):
            if "hours_running" in d:
                lines.append(f"- 🕐 **{code}**: still `{d['status']}` after {d['hours_running']}h -- {d['html_url']}")
            else:
                lines.append(f"- ❌ **{code}**: {d['conclusion']} -- {d['html_url']}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append(
        "Noise already filtered: `NONE`/`S1_*`/`S2_*` failure types, and warning sets "
        "made up entirely of known-benign lines (`no session provided...`, `Duplicate "
        "entry in 'documents'`). Add new confirmed-noise patterns to `NOISE_PATTERNS` "
        "in this script as they turn up -- don't guess ahead of time."
    )

    report = "\n".join(lines)
    print("\n" + report)

    if args.report_file:
        Path(args.report_file).write_text(report)
        print(f"\nReport written to {args.report_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
