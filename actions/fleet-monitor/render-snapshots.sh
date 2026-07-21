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
# The fixture covers success, failure, a workflow that never completed a run
# (null conclusion), a workflow name needing tag escaping, and an unreachable
# repo (error record) — missing values emit no series. The timestamp derives
# from the fixture's fixed polled_at, so the snapshot is byte-identical across
# runs. The errored record makes collect exit 1 (degraded sweep ≠ clean sweep);
# that exit code is part of the contract and asserted here.
if pipenv run python3 main.py collect --metrics-only --dry-run \
    --poller-records fixtures/poller-records.jsonl \
    > "$output_dir/metrics-payload.txt" 2> "$stderr_tmp"; then
  echo "✗ collect with an errored fixture record should exit nonzero"
  exit 1
fi
if ! grep -q 'poll errors on 1 of 5 repos' "$stderr_tmp"; then
  echo "✗ collect should report the errored-repo count on stderr; got:"
  cat "$stderr_tmp"
  exit 1
fi
echo "✓ collect: errored fixture record exits 1 with an errored-repo count"

# Every poller record consumed or produced must validate against its schema —
# same contract mechanism as the jurisdiction records above.
pipenv run python3 - <<'EOF'
import json
from pathlib import Path
from jsonschema import validate

schema = json.load(open("../../schemas/fleet-poller-record.schema.json"))
lines = Path("fixtures/poller-records.jsonl").read_text().splitlines()
for line in lines:
    validate(instance=json.loads(line), schema=schema)
print(f"✓ {len(lines)} fixture poller records validate against fleet-poller-record.schema.json")
EOF

# Poller resilience: a repo whose API calls fail yields an error record and
# never aborts the run, while an unknown template (a config gap) fails the
# sweep before any polling (offline — GitHub is a fake fetcher here). Output
# records must validate against the poller-record schema. The poller is
# otherwise deliberately untested at launch (pass-through against a live API).
pipenv run python3 - <<'EOF'
import json
from jsonschema import validate

from fleet_poller import poll_fleet

SCHEMA = json.load(open("../../schemas/fleet-poller-record.schema.json"))
FLEET = [
    {"fleet": "f", "config": "f.yml", "state": "wy", "org": "good-org",
     "repo": "wy-legislation", "paused": False, "template": "openstates-scrape",
     "expected_workflows": ["openstates-scrape.yml"]},
    {"fleet": "f", "config": "f.yml", "state": "zz", "org": "bad-org",
     "repo": "zz-legislation", "paused": False, "template": "openstates-to-ocd-files",
     "expected_workflows": ["format.yml"]},
]

def fake_fetch(url):
    if "bad-org" in url:
        raise RuntimeError(f"GET {url}: HTTP 404")
    if "/actions/workflows/" in url:
        return {"workflow_runs": [{"status": "completed", "conclusion": "success",
                                   "updated_at": "2026-07-21T00:00:00Z"}]}
    return [{"commit": {"committer": {"date": "2026-07-21T00:00:00Z"}}}]

records = poll_fleet(FLEET, fetch_json=fake_fetch,
                     now="2026-07-21T12:00:00Z")
assert len(records) == 2, records
for record in records:
    validate(instance=record, schema=SCHEMA)
good, bad = records
assert good["errors"] == [], good
assert good["workflows"][0]["latest_conclusion"] == "success", good
assert good["workflows"][0]["hours_since_success"] == 12.0, good
assert good["data_commit_age_hours"] == 12.0, good
assert good["polled_at"] == "2026-07-21T12:00:00+00:00", good
assert bad["errors"] and "HTTP 404" in bad["errors"][0], bad
assert bad["workflows"] == [] and bad["data_commit_age_hours"] is None, bad
print("✓ poller: unreachable repo yields a schema-valid error record, run continues")

# Unknown template = config gap = fatal before any request is made.
try:
    poll_fleet([dict(FLEET[0], template="brand-new-template")],
               fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("polled")))
except ValueError as e:
    assert "brand-new-template" in str(e), e
else:
    raise AssertionError("unknown template should raise ValueError")
print("✓ poller: unknown template fails the sweep before polling")
EOF

# HTTP retry policy: 4xx fails fast, 5xx retries with no sleep before giving
# up, a 429 with an HTTP-date Retry-After falls back to exponential backoff,
# POST verb appears in push errors, and push refuses to run with missing env.
# All offline: fake urlopen, injected sleep.
pipenv run python3 - <<'EOF'
import email.message
import urllib.error
import urllib.request

import http_util
from http_util import request_with_retry
from metrics_push import push_metrics
from metrics_shipper import _escape_tag

def http_error(code, headers=None):
    message = email.message.Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError("https://x.test/y", code, "err", message, None)

calls, sleeps = [], []
def fake_urlopen(request, timeout=None):
    calls.append(request)
    raise http_error(fake_urlopen.code, fake_urlopen.headers)
urllib.request.urlopen = fake_urlopen

fake_urlopen.code, fake_urlopen.headers = 404, {}
try:
    request_with_retry("https://x.test/y", sleep=sleeps.append)
except RuntimeError as e:
    assert "GET https://x.test/y: HTTP 404" in str(e), e
assert len(calls) == 1 and sleeps == [], "4xx must fail fast, no retry, no sleep"

calls.clear()
fake_urlopen.code = 500
try:
    request_with_retry("https://x.test/y", sleep=sleeps.append)
except RuntimeError as e:
    assert "giving up after 3 attempts (HTTP 500)" in str(e), e
assert len(calls) == 3, "5xx must retry to max_retries"
assert len(sleeps) == 2, "no sleep before giving up on the final attempt"

calls.clear(); sleeps.clear()
fake_urlopen.code = 429
fake_urlopen.headers = {"Retry-After": "Wed, 22 Jul 2026 07:28:00 GMT"}
try:
    request_with_retry("https://x.test/y", data=b"", sleep=sleeps.append)
except RuntimeError as e:
    assert "POST https://x.test/y" in str(e), e   # b'' is still a POST
assert sleeps == [8, 16], f"HTTP-date Retry-After must fall back to exponential: {sleeps}"

try:
    push_metrics("payload", env={})
except RuntimeError as e:
    assert "GRAFANA_PUSH_URL, GRAFANA_PUSH_USER, GRAFANA_PUSH_KEY" in str(e), e
else:
    raise AssertionError("push_metrics with empty env should raise")

try:
    _escape_tag("wy\nfleet_repo,state=ca x=1")
except ValueError:
    pass
else:
    raise AssertionError("control character in tag value should raise")
print("✓ http/push: retry policy, POST labeling, env guard, control-char guard")
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
