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

# Poller resilience, offline (GitHub is a fake fetcher): a repo whose API
# calls fail yields an error record and never aborts the run; an unknown base
# template (a config gap) fails the sweep before any polling; active runs
# never mask the last completed conclusion; a flaked status=success page falls
# back to the unfiltered listing; an empty repo (HTTP 409 on /commits) is null,
# not an error; workflow names are percent-encoded into the URL path. Output
# records must validate against the poller-record schema. The poller is
# otherwise deliberately untested at launch (pass-through against a live API).
pipenv run python3 - <<'EOF'
import json
from jsonschema import validate

from fleet_poller import poll_fleet
from http_util import RequestFailed

SCHEMA = json.load(open("../../schemas/fleet-poller-record.schema.json"))

def jurisdiction(state, org, workflows, template="openstates-scrape"):
    return {"fleet": "f", "config": "f.yml", "state": state, "org": org,
            "repo": f"{state}-legislation", "paused": False, "template": template,
            "base_template": template.removesuffix("-paused"),
            "expected_workflows": workflows}

FLEET = [
    jurisdiction("wy", "good-org", ["openstates-scrape.yml"]),
    jurisdiction("ak", "flaky-org", ["openstates-scrape.yml"]),
    jurisdiction("mi", "masked-org", ["openstates-scrape.yml"]),
    jurisdiction("gu", "space-org", ["nightly build.yml"]),
    jurisdiction("nv", "empty-org", ["openstates-scrape.yml"]),
    jurisdiction("zz", "bad-org", ["format.yml"], template="openstates-to-ocd-files"),
]

SUCCESS_RUN = {"status": "completed", "conclusion": "success",
               "updated_at": "2026-07-21T00:00:00Z"}

# flaky-org: the status=success filtered index returns an empty page with
# HTTP 200 (observed GitHub quirk) while the unfiltered listing shows the
# success. masked-org: the two newest runs are still active; the completed
# failure behind them must supply the conclusion. empty-org: /commits gives
# HTTP 409 on a repo with no commits yet.
def fake_fetch(url):
    assert " " not in url, f"unencoded URL: {url}"
    if "bad-org" in url:
        raise RuntimeError(f"GET {url}: HTTP 404")
    if "empty-org" in url and "/commits?" in url:
        raise RequestFailed(f"GET {url}: HTTP 409", status=409)
    if "space-org" in url and "/actions/workflows/" in url:
        assert "nightly%20build.yml" in url, f"workflow name not percent-encoded: {url}"
    if "status=success" in url:
        if "flaky-org" in url or "masked-org" in url:
            return {"workflow_runs": []}
        return {"workflow_runs": [SUCCESS_RUN]}
    if "/actions/workflows/" in url:
        if "masked-org" in url:
            return {"workflow_runs": [
                {"status": "in_progress", "conclusion": None},
                {"status": "queued", "conclusion": None},
                {"status": "completed", "conclusion": "failure",
                 "updated_at": "2026-07-21T03:00:00Z"},
            ]}
        return {"workflow_runs": [{"status": "completed", "conclusion": "success",
                                   "updated_at": "2026-07-21T06:00:00Z"}]}
    return [{"commit": {"committer": {"date": "2026-07-21T00:00:00Z"}}}]

records = poll_fleet(FLEET, fetch_json=fake_fetch,
                     now="2026-07-21T12:00:00Z")
assert len(records) == 6, records
for record in records:
    validate(instance=record, schema=SCHEMA)
good, flaky, masked, spaced, empty, bad = records
assert good["errors"] == [], good
assert good["workflows"][0]["latest_conclusion"] == "success", good
assert good["workflows"][0]["hours_since_success"] == 12.0, good
assert good["data_commit_age_hours"] == 12.0, good
assert good["polled_at"] == "2026-07-21T12:00:00+00:00", good
assert flaky["errors"] == [], flaky
assert flaky["workflows"][0]["hours_since_success"] == 6.0, \
    f"empty status=success page must fall back to the unfiltered listing: {flaky}"
assert masked["errors"] == [], masked
assert masked["workflows"][0]["latest_conclusion"] == "failure", \
    f"active runs must not mask the last completed conclusion: {masked}"
assert spaced["errors"] == [], spaced
assert spaced["workflows"][0]["latest_conclusion"] == "success", spaced
assert empty["errors"] == [], f"an empty repo (409) is null, not an error: {empty}"
assert empty["data_commit_age_hours"] is None, empty
assert bad["errors"] and "HTTP 404" in bad["errors"][0], bad
assert bad["workflows"] == [] and bad["data_commit_age_hours"] is None, bad
print("✓ poller: unreachable repo yields a schema-valid error record, run continues")
print("✓ poller: flaked status=success page falls back to the unfiltered listing")
print("✓ poller: active runs never mask the last completed conclusion")
print("✓ poller: workflow names are percent-encoded; empty repo (409) is null")

# Unknown base template = config gap = fatal before any request is made.
try:
    poll_fleet([dict(FLEET[0], base_template="brand-new-template")],
               fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("polled")))
except ValueError as e:
    assert "brand-new-template" in str(e), e
else:
    raise AssertionError("unknown base template should raise ValueError")
print("✓ poller: unknown base template fails the sweep before polling")
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

calls.clear(); sleeps.clear()
fake_urlopen.headers = {"Retry-After": "60"}
try:
    request_with_retry("https://x.test/y", sleep=sleeps.append)
except RuntimeError:
    pass
assert sleeps == [60, 60], f"integer Retry-After must be honored: {sleeps}"

calls.clear(); sleeps.clear()
fake_urlopen.code = 403
fake_urlopen.headers = {"X-RateLimit-Remaining": "0", "Retry-After": "30"}
try:
    request_with_retry("https://x.test/y", sleep=sleeps.append)
except RuntimeError:
    pass
assert len(calls) == 3 and sleeps == [30, 30], \
    f"rate-limited 403 must retry like 429: {len(calls)} calls, sleeps {sleeps}"

calls.clear(); sleeps.clear()
fake_urlopen.headers = {}
try:
    request_with_retry("https://x.test/y", sleep=sleeps.append)
except RuntimeError as e:
    assert "HTTP 403" in str(e), e
assert len(calls) == 1 and sleeps == [], "plain 403 (no rate-limit headers) must fail fast"

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
print("✓ http/push: retry policy (incl. rate-limited 403), POST labeling, env guard, control-char guard")
EOF

# The clean path: an errors-free sweep must exit 0 and produce exactly the
# same series lines (the errored record contributes none), so exit-1 is
# provably tied to poll errors, not to collect itself.
clean_records=$(mktemp); clean_out=$(mktemp)
trap 'rm -f "$stderr_tmp" "$clean_records" "$clean_out"' EXIT
pipenv run python3 - "$clean_records" <<'EOF'
import json, sys
lines = [line for line in open("fixtures/poller-records.jsonl")
         if line.strip() and not json.loads(line)["errors"]]
open(sys.argv[1], "w").writelines(lines)
EOF
if ! pipenv run python3 main.py collect --metrics-only --dry-run \
    --poller-records "$clean_records" > "$clean_out"; then
  echo "✗ collect on an errors-free fleet should exit 0"
  exit 1
fi
if ! diff -q "$clean_out" "$output_dir/metrics-payload.txt" > /dev/null; then
  echo "✗ clean-sweep payload should match the snapshot (errored record adds no lines)"
  diff "$clean_out" "$output_dir/metrics-payload.txt" || true
  exit 1
fi
echo "✓ collect: errors-free sweep exits 0 with the identical payload"

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
from fleet_poller import DATA_PATHS, estimate_request_count

records = read_fleet("../pipeline-manager")
count = estimate_request_count(records)
assert count < 400, f"fleet sweep now costs {count} GitHub requests; revisit the polling strategy"
print(f"✓ API budget: one sweep of the real fleet = {count} GitHub requests (< 400)")

# Every real-fleet base template needs a DATA_PATHS entry, or the first live
# sweep after a new template ships would fail at startup while snapshots
# stayed green.
missing = {r["base_template"] for r in records} - DATA_PATHS.keys()
assert not missing, f"real-fleet base template(s) missing from DATA_PATHS: {sorted(missing)}"
print("✓ data paths: every real-fleet base template has a DATA_PATHS entry")
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

# And unconditionally, so the render IS the automated live check whenever the
# GRAFANA_* credentials are present in the environment (CI has none → the
# command self-skips; a credentialed local render runs the real poll, push,
# and query-back proof with no extra step).
pipenv run python3 main.py live-check --config-dir ../pipeline-manager

echo "✓ Snapshot generation complete. Output in $output_dir"
