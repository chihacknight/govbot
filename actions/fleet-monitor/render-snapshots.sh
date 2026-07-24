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

calls.clear(); sleeps.clear()
fake_urlopen.headers = {"X-RateLimit-Remaining": "0"}
try:
    request_with_retry("https://x.test/y", sleep=sleeps.append)
except RuntimeError as e:
    assert "rate limit exhausted" in str(e), e
assert len(calls) == 1 and sleeps == [], \
    "exhausted quota without Retry-After must fail fast (reset is up to an hour out)"

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

# push_metrics happy path: what actually goes over the wire — URL, verb,
# Basic auth, Content-Type, body — asserted offline with a succeeding fake.
import base64

class FakeResponse:
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *args): return False

def ok_urlopen(request, timeout=None):
    calls.append(request)
    return FakeResponse()
urllib.request.urlopen = ok_urlopen

calls.clear()
push_metrics("m,state=wy f=1 1\n", env={
    "GRAFANA_PUSH_URL": "https://push.test/api/v1/push/influx/write",
    "GRAFANA_PUSH_USER": "123456",
    "GRAFANA_PUSH_KEY": "write-key",
})
request = calls[0]
assert request.full_url == "https://push.test/api/v1/push/influx/write", request.full_url
assert request.data == b"m,state=wy f=1 1\n", request.data
assert request.get_method() == "POST", request.get_method()
expected_auth = "Basic " + base64.b64encode(b"123456:write-key").decode()
assert request.get_header("Authorization") == expected_auth, request.header_items()
assert request.get_header("Content-type") == "text/plain; charset=utf-8", request.header_items()

# A naive `now` must fail once and clearly, not as 112 per-repo errors.
from fleet_poller import poll_fleet
try:
    poll_fleet([], now="2026-07-21T12:00:00")
except ValueError as e:
    assert "timezone-aware" in str(e), e
else:
    raise AssertionError("naive now should raise ValueError")
print("✓ http/push: retry policy (incl. exhausted quota), POST labeling, push wire format, guards")
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

# Explicit --timestamp overrides the polled_at default on every line.
pipenv run python3 main.py collect --metrics-only --dry-run \
  --poller-records "$clean_records" --timestamp 1750000000 > "$clean_out"
if grep -qv ' 1750000000000000000$' "$clean_out"; then
  echo "✗ --timestamp 1750000000 should stamp every series line"
  cat "$clean_out"
  exit 1
fi
echo "✓ collect: explicit --timestamp overrides the polled_at default"

# An all-null push (empty payload) must not read as a clean run: stack-side
# it is indistinguishable from the monitor never running.
empty_records=$(mktemp)
trap 'rm -f "$stderr_tmp" "$clean_records" "$clean_out" "$empty_records"' EXIT
grep '"errors": \[\"' fixtures/poller-records.jsonl > "$empty_records"
for mode in "" "--dry-run"; do
  if pipenv run python3 main.py collect --metrics-only $mode \
      --poller-records "$empty_records" > /dev/null 2> "$stderr_tmp"; then
    echo "✗ collect ${mode:-push mode} with an empty payload should exit nonzero"
    exit 1
  fi
  if ! grep -q 'nothing to push' "$stderr_tmp"; then
    echo "✗ empty-payload failure should say 'nothing to push'; got:"
    cat "$stderr_tmp"
    exit 1
  fi
done
echo "✓ collect: empty payload fails loudly in push and dry-run modes"

# Orchestrator `run` — the unattended hourly sweep. Its exit contract diverges
# from collect's on purpose: a red workflow run must mean the *collector* is
# down, so only an outright collector failure (config/poll error, or a failed
# push) exits nonzero. Per-repo poll errors are logged but keep the run green —
# a degraded fleet surfaces through metrics and Grafana alerts, not a red
# collector workflow. A collector heartbeat ships on every run, so an all-null
# sweep still proves the collector ran.

# Heartbeat encoder: one untagged global line, always emitted.
pipenv run python3 - <<'EOF'
from metrics_shipper import encode_heartbeat

assert encode_heartbeat(5, 1, 1784635200) == \
    "fleet_collector_heartbeat repos=5,errors=1 1784635200000000000\n"
# Always non-empty, even for a zero-repo sweep — the one line that always ships.
assert encode_heartbeat(0, 0, 1) == "fleet_collector_heartbeat repos=0,errors=0 1000000000\n"
print("✓ heartbeat: one untagged global line carrying the sweep size, always emitted")
EOF

# Partial-fail sweep (the fixture's 1-of-5 errored record): run exits 0 and its
# dry-run payload is the metric lines PLUS a heartbeat carrying the sweep size.
if ! pipenv run python3 main.py run --dry-run \
    --poller-records fixtures/poller-records.jsonl \
    > "$output_dir/run-payload.txt" 2> "$stderr_tmp"; then
  echo "✗ run with a partial-fail fixture must stay green (exit 0)"
  cat "$stderr_tmp"
  exit 1
fi
if ! grep -q '^poll error: ' "$stderr_tmp"; then
  echo "✗ run should still log per-repo poll errors to stderr; got:"
  cat "$stderr_tmp"
  exit 1
fi
if ! grep -q '^fleet_collector_heartbeat repos=5,errors=1 ' "$output_dir/run-payload.txt"; then
  echo "✗ run payload must carry a heartbeat with the sweep size"
  cat "$output_dir/run-payload.txt"
  exit 1
fi
# The metric lines are exactly collect's (heartbeat aside): run adds the
# heartbeat without altering the encoded series.
if ! diff -q <(grep -v '^fleet_collector_heartbeat ' "$output_dir/run-payload.txt") \
    "$output_dir/metrics-payload.txt" > /dev/null; then
  echo "✗ run's metric lines should match the collect snapshot payload"
  diff <(grep -v '^fleet_collector_heartbeat ' "$output_dir/run-payload.txt") \
    "$output_dir/metrics-payload.txt" || true
  exit 1
fi
echo "✓ run: partial-fail sweep exits 0, logs errors, ships metrics + heartbeat"

# Clean sweep (errors-free records): exits 0, heartbeat reports zero errors.
if ! pipenv run python3 main.py run --dry-run --poller-records "$clean_records" 2> /dev/null \
    | grep -q '^fleet_collector_heartbeat repos=4,errors=0 '; then
  echo "✗ run on a clean sweep should exit 0 with a zero-error heartbeat"
  exit 1
fi
echo "✓ run: clean sweep exits 0 with a zero-error heartbeat"

# All-errored sweep: no metric lines, yet run still exits 0 and ships the
# heartbeat alone — an all-null fleet is the collector doing its job on a broken
# fleet, not the collector failing (collect, by contrast, fails loudly here).
run_all_errored=$(pipenv run python3 main.py run --dry-run --poller-records "$empty_records" 2> /dev/null)
if [ -n "$(echo "$run_all_errored" | grep -v '^fleet_collector_heartbeat ' || true)" ]; then
  echo "✗ an all-errored sweep should emit only the heartbeat line; got:"
  echo "$run_all_errored"
  exit 1
fi
if ! echo "$run_all_errored" | grep -q '^fleet_collector_heartbeat '; then
  echo "✗ an all-errored sweep must still ship the heartbeat"
  exit 1
fi
echo "✓ run: all-errored sweep still exits 0 and ships the heartbeat alone"

# Outright failure: absent Grafana push credentials in real push mode exits
# nonzero, so the workflow shows red — the acceptance case (a bad key = red).
if env -u GRAFANA_PUSH_URL -u GRAFANA_PUSH_USER -u GRAFANA_PUSH_KEY \
    pipenv run python3 main.py run --poller-records "$clean_records" \
    > /dev/null 2> "$stderr_tmp"; then
  echo "✗ run must exit nonzero when the Grafana push fails (missing credentials)"
  exit 1
fi
if ! grep -q 'GRAFANA_PUSH' "$stderr_tmp"; then
  echo "✗ an outright push failure should name the missing Grafana credentials; got:"
  cat "$stderr_tmp"
  exit 1
fi
echo "✓ run: outright push failure exits nonzero (workflow shows red)"

# The shipper is resilient per record, the way the poller is per repo: a record
# it can't encode (a control char in a tag, a missing key) is skipped — never a
# half-built line — and never blanks the rest of the sweep.
pipenv run python3 - <<'EOF'
from metrics_shipper import encode_metrics

good = {"state": "wy", "org": "o", "paused": False,
        "workflows": [{"workflow": "s.yml", "latest_conclusion": "success",
                       "hours_since_success": 1.0}],
        "data_commit_age_hours": 2.0}
bad = dict(good, state="w\ny")  # control char in a tag value -> ValueError
missing = {"org": "o", "paused": False, "workflows": [],
           "data_commit_age_hours": 1.0}  # no 'state' -> KeyError
structured = dict(good, org="z", data_commit_age_hours=[1, 2])  # list field -> TypeError
payload = encode_metrics([good, bad, missing, structured], 1784635200)
assert payload.count("state=wy") == 2, payload  # the good record's two lines survive
assert "w\ny" not in payload and "w\\ny" not in payload, "bad record must be skipped, not half-built"
assert "org=z" not in payload, "a structured (TypeError) field value must be skipped too"
print("✓ shipper: an un-encodable record (ValueError/KeyError/TypeError) is skipped; the rest ships")
EOF

# Through run: a good repo alongside a bad one — run exits 0, ships the good
# repo's metrics + the heartbeat, and the un-encodable repo simply contributes
# no line. One repo's bad data can neither blank the sweep nor turn it red.
bad_encode=$(mktemp)
trap 'rm -f "$stderr_tmp" "$clean_records" "$clean_out" "$empty_records" "$bad_encode"' EXIT
pipenv run python3 - "$bad_encode" <<'EOF'
import json, sys


def rec(state):
    return {"fleet": "f", "config": "f.yml", "state": state, "org": "o", "repo": "r-" + state,
            "paused": False, "polled_at": "2026-07-21T12:00:00+00:00",
            "workflows": [{"workflow": "openstates-scrape.yml",
                           "latest_conclusion": "success", "hours_since_success": 1.0}],
            "data_commit_age_hours": 2.0, "errors": []}


with open(sys.argv[1], "w") as f:
    f.write(json.dumps(rec("wy")) + "\n")    # good
    f.write(json.dumps(rec("w\ny")) + "\n")  # control char in a tag -> skipped
EOF
if ! pipenv run python3 main.py run --dry-run --poller-records "$bad_encode" \
    > "$clean_out" 2> "$stderr_tmp"; then
  echo "✗ run must stay green when one repo's data fails to encode"
  cat "$stderr_tmp"
  exit 1
fi
wf_lines=$(grep -c '^fleet_workflow_run,' "$clean_out" || true)
repo_lines=$(grep -c '^fleet_repo,' "$clean_out" || true)
if [ "$wf_lines" != "1" ] || [ "$repo_lines" != "1" ]; then
  echo "✗ only the good repo should contribute lines (got $wf_lines workflow, $repo_lines repo):"
  cat "$clean_out"
  exit 1
fi
if ! grep -q '^fleet_workflow_run,state=wy,' "$clean_out"; then
  echo "✗ the good repo's metrics must still ship when another repo can't encode; got:"
  cat "$clean_out"
  exit 1
fi
if ! grep -q '^fleet_collector_heartbeat repos=2,errors=0 ' "$clean_out"; then
  echo "✗ the heartbeat must report the full sweep size (repos=2), encode skips aside; got:"
  cat "$clean_out"
  exit 1
fi
echo "✓ run: a repo's un-encodable data is skipped, the good repo still ships, run stays green"

# The named acceptance case — a bad Grafana key — end to end through run: a fake
# urlopen returns HTTP 401, so the push fails at the wire (not the missing-env
# guard above) and run exits nonzero. Driven in-process (CliRunner) because a
# subprocess can't inject the fake urlopen.
pipenv run python3 - "$clean_records" <<'EOF'
import email.message
import sys
import urllib.error
import urllib.request

from click.testing import CliRunner

import main


def bad_key_urlopen(request, timeout=None):
    raise urllib.error.HTTPError(
        request.full_url, 401, "Unauthorized", email.message.Message(), None
    )


urllib.request.urlopen = bad_key_urlopen
result = CliRunner().invoke(
    main.cli,
    ["run", "--poller-records", sys.argv[1]],
    env={
        "GRAFANA_PUSH_URL": "https://push.test/api/v1/push/influx/write",
        "GRAFANA_PUSH_USER": "123456",
        "GRAFANA_PUSH_KEY": "bad-key",
    },
)
# click 8.2+ captures stdout/stderr separately; the ClickException lands on stderr.
combined = result.output + (result.stderr or "")
assert result.exit_code != 0, f"a rejected key (HTTP 401) must exit nonzero: {combined}"
assert "HTTP 401" in combined, combined
print("✓ run: a rejected Grafana key (HTTP 401) exits nonzero end to end")
EOF

# live-check's query-back proof derives expected series names AND counts from
# the payload it pushed; the accounting is locked against the snapshot payload
# (which includes an escaped-space tag value the parser must not trip on).
pipenv run python3 - <<'EOF'
from main import _expected_series

payload = open("__snapshots__/metrics-payload.txt").read()
counts = _expected_series(payload)
assert counts == {"fleet_workflow_run_status": 3,
                  "fleet_workflow_run_hours_since_success": 3,
                  "fleet_repo_data_commit_age_hours": 3}, counts
assert all(n == 0 for n in _expected_series("").values())
print("✓ live-check: expected-series accounting matches the snapshot payload")
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

# The real push-and-query proof is opt-in: a bare render must stay offline,
# deterministic, and side-effect-free even on a machine that happens to have
# GRAFANA_* set (each live check appends real samples to the production
# stack and its result tracks live fleet health). Opting in makes the render
# the automated live check.
if [ "${FLEET_MONITOR_LIVE_CHECK:-}" = "1" ]; then
  pipenv run python3 main.py live-check --config-dir ../pipeline-manager
else
  echo "· live-check (real push + query-back) not run; opt in with FLEET_MONITOR_LIVE_CHECK=1"
fi

echo "✓ Snapshot generation complete. Output in $output_dir"
