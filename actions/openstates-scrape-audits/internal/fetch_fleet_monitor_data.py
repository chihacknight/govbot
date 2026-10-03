#!/usr/bin/env python3
"""Pull fleet-monitor's own live poller records -- reuses Nate's existing,
battle-tested GitHub-polling code (actions/fleet-monitor/fleet_poller.py)
instead of re-deriving commit-age/workflow-status per repo by hand (which is
what the ad hoc FL investigation did). This is the infrastructure-layer half
of "healthy" (did the workflow run, how stale is the last data commit) --
see what-does-healthy-mean.md's "Two layers of healthy" section for how this
relates to the content-layer checks in audit_states.py.

Needs GITHUB_TOKEN (gh CLI's token works). Does NOT push to Grafana -- this
only polls and writes the raw records locally.

Usage: python3 fetch_fleet_monitor_data.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FLEET_MONITOR_DIR = REPO_ROOT / "actions" / "fleet-monitor"
CONFIG_DIR = REPO_ROOT / "actions" / "pipeline-manager"

sys.path.insert(0, str(FLEET_MONITOR_DIR))


def main():
    if not os.environ.get("GITHUB_TOKEN"):
        token = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True
        ).stdout.strip()
        if not token:
            print("No GITHUB_TOKEN and `gh auth token` returned nothing.", file=sys.stderr)
            sys.exit(1)
        os.environ["GITHUB_TOKEN"] = token

    from fleet_config import EXCLUDED_FLEETS, read_fleet
    from fleet_poller import poll_fleet

    jurisdictions = read_fleet(CONFIG_DIR, EXCLUDED_FLEETS)
    records = poll_fleet(jurisdictions)

    errored = [r for r in records if r.get("errors")]
    print(f"Polled {len(records)} repos, {len(errored)} had poll errors.", file=sys.stderr)
    for r in errored:
        print(f"  {r['state']} ({r['repo']}): {r['errors']}", file=sys.stderr)

    out_path = Path(__file__).parent / "fleet_monitor_snapshot.json"
    out_path.write_text(json.dumps(records, indent=2, default=str))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
