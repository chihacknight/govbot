#!/usr/bin/env python3
"""Fleet-wide sweep: apply the new WARNING-level detection (PR #187,
scrape.sh) retroactively against each state's most recent successful
openstates-scrape.yml run log. MA was found by accident; this answers
"which other states have the same silently-lossy pattern" systematically.

For each of the 56 scraper repos: find the most recent run with
conclusion=success, download its log, count lines matching the same
\bWARNING\b pattern (with the same exclusions) scrape.sh now uses. A high
count means the run reported GitHub Actions "success" while real scraper
warnings were landing silently -- exactly MA's pattern, found 2026-10-02.

Deliberately checks the most recent SUCCESS run only (not history) -- this
is a one-time retroactive sweep of current 2026 data, not a trend analysis
(see fetch_fleet_monitor_data.py for the live/ongoing infrastructure-layer
signal, and what-does-healthy-mean.md for the design reasoning).

Usage: python3 sweep_scraper_warnings.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ORG = "govbot-openstates-scrapers"

WARNING_RE = re.compile(r"\bWARNING\b")
EXCLUDE_RE = re.compile(
    r"( INFO |scrape attempt|retry|retrying|resolved|recovered|succeeded|SKIPPED BILL)",
    re.IGNORECASE,
)


def load_states() -> list[str]:
    with open(REPO_ROOT / "actions" / "pipeline-manager" / "chn-openstates-scrape.yml") as f:
        cfg = yaml.safe_load(f)
    return sorted(cfg["locales"].keys())


def latest_success_run(code: str) -> dict | None:
    # gh run list's --status=success filter is unreliable -- confirmed it misses
    # recent success runs that definitely exist (MA: returned 2026-07-06 as "most
    # recent success" when 2026-08-07 success runs are real and verified). Fetch
    # unfiltered and pick the most recent conclusion=="success" client-side instead.
    out = subprocess.run(
        [
            "gh", "run", "list",
            "--repo", f"{ORG}/{code}-legislation",
            "--workflow=openstates-scrape.yml",
            "--limit=100",
            "--json", "databaseId,createdAt,conclusion",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        return None
    try:
        runs = json.loads(out.stdout)
    except Exception:
        return None
    successes = [r for r in runs if r.get("conclusion") == "success"]
    if not successes:
        return None
    return max(successes, key=lambda r: r["createdAt"])


def count_warnings(code: str, run_id: int) -> tuple[int, list[str], int]:
    """Returns (warning_count, sample_items, total_log_lines)."""
    out = subprocess.run(
        ["gh", "run", "view", str(run_id), "--repo", f"{ORG}/{code}-legislation", "--log"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        return 0, [], 0
    lines = out.stdout.splitlines()
    matches = []
    for line in lines:
        if WARNING_RE.search(line) and not EXCLUDE_RE.search(line):
            matches.append(line)
    samples = [m.split("\t")[-1].strip() for m in matches[:3]]
    return len(matches), samples, len(lines)


def main():
    states = load_states()
    results = []
    for i, code in enumerate(states, 1):
        print(f"[{i}/{len(states)}] {code}...", file=sys.stderr)
        run = latest_success_run(code)
        if not run:
            results.append({"code": code, "status": "no_success_run_found"})
            continue
        warning_count, samples, total_lines = count_warnings(code, run["databaseId"])
        results.append({
            "code": code,
            "run_id": run["databaseId"],
            "run_date": run["createdAt"],
            "warning_count": warning_count,
            "sample_warnings": samples,
            "log_lines": total_lines,
        })
        print(
            f"    run {run['databaseId']} ({run['createdAt'][:10]}): "
            f"{warning_count} warnings / {total_lines} log lines",
            file=sys.stderr,
        )

    out_path = Path(__file__).parent / "warning_sweep_output.json"
    out_path.write_text(json.dumps(results, indent=2))

    ranked = sorted(
        [r for r in results if "warning_count" in r],
        key=lambda r: -r["warning_count"],
    )
    print("\n# Fleet-wide warning sweep -- ranked by silent-warning count\n")
    for r in ranked[:20]:
        print(f"  {r['code']}: {r['warning_count']} warnings ({r['run_date'][:10]})")
    no_runs = [r["code"] for r in results if r.get("status") == "no_success_run_found"]
    if no_runs:
        print(f"\nNo successful run found at all for: {', '.join(no_runs)}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
