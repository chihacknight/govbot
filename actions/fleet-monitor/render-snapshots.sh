#!/bin/bash

# Regenerate snapshot outputs for fleet-monitor.
# Fixture configs in fixtures/ go in; jurisdiction records (JSON Lines) come out.
# Verified in CI by scripts/verify-snapshots.sh (git diff against committed snapshots).

set -e

output_dir="./__snapshots__"
mkdir -p "$output_dir"

pipenv run python3 main.py list-fleet --config-dir fixtures > "$output_dir/fleet.jsonl"

# Broken configs must fail loudly (nonzero exit, clear error), never emit empty
# records. One subdirectory per failure mode; each error message is snapshotted.
stderr_tmp=$(mktemp)
trap 'rm -f "$stderr_tmp"' EXIT
for invalid in fixtures-invalid/*/; do
  mode=$(basename "$invalid")
  if pipenv run python3 main.py list-fleet --config-dir "$invalid" \
      > /dev/null 2> "$stderr_tmp"; then
    echo "✗ $invalid should have failed but exited 0"
    exit 1
  fi
  # Snapshot only the CLI's Error: line — pipenv adds environment-dependent
  # chatter (courtesy notices, lock warnings) that must not enter snapshots.
  if ! grep '^Error:' "$stderr_tmp" > "$output_dir/invalid-${mode}-error.txt"; then
    echo "✗ $invalid failed without a clean Error: line; stderr was:"
    cat "$stderr_tmp"
    exit 1
  fi
done

# Every record must validate against the module's declared contract in /schemas.
pipenv run python3 - <<'EOF'
import json
from pathlib import Path
from jsonschema import validate

schema = json.load(open("../../schemas/fleet-record.schema.json"))
lines = Path("__snapshots__/fleet.jsonl").read_text().splitlines()
for line in lines:
    validate(instance=json.loads(line), schema=schema)
print(f"✓ {len(lines)} records validate against fleet-record.schema.json")
EOF

# Metrics shipper: fixed poller records in, exact Grafana push payload out.
# The fixture covers success, failure, a still-running workflow (null conclusion),
# and an unreachable repo (error record) — errored/missing values emit no series.
# --timestamp pins the payload so the snapshot is byte-identical across runs.
pipenv run python3 main.py collect --metrics-only --dry-run \
  --poller-records fixtures/poller-records.jsonl \
  --timestamp 1750000000 > "$output_dir/metrics-payload.txt"

# Poller resilience: a repo whose API calls fail yields an error record and
# never aborts the run (offline — GitHub is a fake fetcher here). The poller is
# otherwise deliberately untested at launch (pass-through against a live API);
# this locks only the never-fatal contract.
pipenv run python3 - <<'EOF'
from fleet_poller import poll_fleet

FLEET = [
    {"state": "wy", "org": "good-org", "repo": "wy-legislation", "paused": False,
     "template": "openstates-scrape", "expected_workflows": ["openstates-scrape.yml"]},
    {"state": "zz", "org": "bad-org", "repo": "zz-legislation", "paused": False,
     "template": "openstates-to-ocd-files", "expected_workflows": ["format.yml"]},
]

def fake_fetch(url):
    if "bad-org" in url:
        raise RuntimeError(f"GET {url}: HTTP 404")
    if "/actions/workflows/" in url:
        return {"workflow_runs": [{"conclusion": "success", "status": "completed",
                                   "updated_at": "2026-07-21T00:00:00Z"}]}
    return [{"commit": {"committer": {"date": "2026-07-21T00:00:00Z"}}}]

records = poll_fleet(FLEET, fetch_json=fake_fetch,
                     now="2026-07-21T12:00:00Z")
assert len(records) == 2, records
good, bad = records
assert good["errors"] == [], good
assert good["workflows"][0]["latest_conclusion"] == "success", good
assert good["workflows"][0]["hours_since_success"] == 12.0, good
assert good["data_commit_age_hours"] == 12.0, good
assert bad["errors"] and "HTTP 404" in bad["errors"][0], bad
assert bad["workflows"] == [] and bad["data_commit_age_hours"] is None, bad
print("✓ poller: unreachable repo yields an error record, run continues")
EOF

# Smoke: the real pipeline-manager config must parse and be non-empty.
# Not snapshotted — the real config churns; this only locks "it still works".
real_count=$(pipenv run python3 main.py list-fleet --config-dir ../pipeline-manager | wc -l | tr -d ' ')
if [ "$real_count" -lt 1 ]; then
  echo "✗ real-config smoke failed: no records from ../pipeline-manager"
  exit 1
fi
echo "✓ real-config smoke: $real_count records from ../pipeline-manager"

# API budget: one sweep of the real fleet must stay in the low hundreds of
# GitHub requests (default GITHUB_TOKEN allows 1000/hour). Not snapshotted —
# the count moves with the fleet; this locks the ceiling, not the number.
pipenv run python3 - <<'EOF'
from fleet_config import read_fleet
from fleet_poller import estimate_request_count

count = estimate_request_count(read_fleet("../pipeline-manager"))
assert count < 400, f"fleet sweep now costs {count} GitHub requests; revisit the polling strategy"
print(f"✓ API budget: one sweep of the real fleet = {count} GitHub requests (< 400)")
EOF

# Live check self-skips without credentials (exit 0, says so) — CI has no
# Grafana account, so this locks the skip path; the live path runs only when
# GRAFANA_* env vars are present (see README).
skip_output=$(env -u GRAFANA_PUSH_URL -u GRAFANA_PUSH_USER -u GRAFANA_PUSH_KEY \
  -u GRAFANA_QUERY_URL -u GRAFANA_QUERY_USER -u GRAFANA_QUERY_KEY \
  pipenv run python3 main.py live-check --config-dir fixtures 2>&1)
if ! echo "$skip_output" | grep -q "live check skipped"; then
  echo "✗ live-check without credentials should skip cleanly; got:"
  echo "$skip_output"
  exit 1
fi
echo "✓ live-check: skips cleanly when credentials are absent"

echo "✓ Snapshot generation complete. Output in $output_dir"
