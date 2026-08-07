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

# request_with_retry must strip the Authorization header on a cross-host redirect
# but keep it on a same-host one. GitHub's log-archive endpoint 302-redirects to
# Azure blob storage; a forwarded GitHub token makes Azure answer 403 (and leaks
# the token). Proven end to end against two loopback servers (localhost vs
# 127.0.0.1 = a host change), no external network.
pipenv run python3 - <<'EOF'
import http.server
import threading

from http_util import request_with_retry

seen = {}

class Target(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        seen["auth"] = self.headers.get("Authorization")
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass

class Redirector(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # same-host hop first (keep auth), then cross-host to the target (strip)
        if self.path == "/same":
            seen["same_auth"] = self.headers.get("Authorization")
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:{target_port}/blob")
        self.end_headers()
    def log_message(self, *a): pass

target = http.server.HTTPServer(("127.0.0.1", 0), Target)
target_port = target.server_address[1]
redir = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
redir_port = redir.server_address[1]
threading.Thread(target=target.serve_forever, daemon=True).start()
threading.Thread(target=redir.serve_forever, daemon=True).start()

auth = {"Authorization": "Bearer SECRET-TOKEN"}
# Cross-host: localhost -> 127.0.0.1 is a host change, so auth must be dropped.
request_with_retry(f"http://localhost:{redir_port}/logs", headers=auth)
assert seen.get("auth") is None, f"Authorization leaked across a cross-host redirect: {seen}"
# Same-host: no redirect, auth must survive (GitHub API calls rely on it).
seen.clear()
request_with_retry(f"http://127.0.0.1:{target_port}/blob", headers=auth)
assert seen.get("auth") == "Bearer SECRET-TOKEN", f"auth must survive a direct request: {seen}"

# The comparison is (scheme, host, port), not host alone: a SAME-host redirect
# that downgrades https to http would otherwise forward a bearer token in
# cleartext. Asserted on the comparison itself — a live https downgrade needs a
# certificate, and the handler's decision is the whole behaviour.
import urllib.request

from http_util import _StripAuthOnCrossHostRedirect


def forwards_auth(origin, target):
    """Whether the real handler carries Authorization on this hop."""
    request = urllib.request.Request(origin, headers={"Authorization": "Bearer SECRET-TOKEN"})
    followed = _StripAuthOnCrossHostRedirect().redirect_request(
        request, None, 302, "Found", {}, target
    )
    return followed is not None and followed.get_header("Authorization") is not None


base = "https://stack.grafana.net/api/x"
assert not forwards_auth(base, "http://stack.grafana.net/api/y"), "token forwarded on https→http"
assert not forwards_auth(base, "https://stack.grafana.net:8443/api/y"), "token forwarded on a port change"
assert not forwards_auth(base, "https://elsewhere.example/api/y"), "token forwarded cross-host"
# ...but a redirect that merely spells out the default port never left the
# origin, and dropping the token there breaks provisioning on a 401.
assert forwards_auth(base, "https://stack.grafana.net:443/api/y"), "token dropped on an explicit :443"
assert forwards_auth("https://stack.grafana.net:443/api/x", "https://stack.grafana.net/api/y")
# An authority we cannot parse is not an origin we can match, so the header goes.
# Letting urlparse's ValueError escape would surface inside urlopen as a retried
# network error — a bad redirect reported as a timeout.
assert not forwards_auth(base, "https://stack.grafana.net:notaport/api/y")

print("✓ http: Authorization is stripped on a cross-host redirect and on a scheme or port "
      "change, kept on a direct request and across an explicit default port")
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

# ── Logs: harvester + Loki shipper + watermark (task 0004) ──────────────────
# The logs tracer bullet, all offline. Loki shipper (pure encoder), watermark
# store (load/save), harvester (unpack archive → parse GitHub's line-timestamp
# prefix → drop noise → volume policy → labeled batches, incremental against a
# per-repo/workflow watermark), Loki push wire format, and the CLI logs leg
# (fixture archives in → exact Loki push payload out, an idempotent re-run ships
# nothing, a lost watermark recovers via the 24h look-back).
logs_wm=$(mktemp)
trap 'rm -f "$stderr_tmp" "$clean_records" "$clean_out" "$empty_records" "$bad_encode" "$logs_wm"' EXIT

# Loki shipper: labeled batches in, exact Loki push JSON out. Labels are capped
# at org/state/workflow/outcome; run identity rides in structured metadata, never
# a label; streams and values are sorted so the bytes are deterministic; an
# un-encodable batch (control char in a label, a missing key) is skipped and an
# empty batch emits no stream — the same per-item resilience the metrics shipper has.
pipenv run python3 - <<'EOF'
import json
from logs_shipper import encode_logs

batches = [
    {"labels": {"org": "o", "state": "wy", "workflow": "s.yml", "outcome": "failure"},
     "entries": [{"timestamp_ns": 2, "line": "second", "metadata": {"run_id": 9}},
                 {"timestamp_ns": 1, "line": "first", "metadata": {"run_id": 9}}]},
    {"labels": {"org": "o", "state": "w\ny", "workflow": "s.yml", "outcome": "failure"},
     "entries": [{"timestamp_ns": 1, "line": "x"}]},                # control char -> ValueError -> skipped
    {"labels": {"org": "o", "state": "mi", "workflow": "s.yml"},    # no outcome -> KeyError -> skipped
     "entries": [{"timestamp_ns": 1, "line": "x"}]},
    {"labels": {"org": "o", "state": "ak", "workflow": "s.yml", "outcome": "failure"},
     "entries": [{"timestamp_ns": [1], "line": "x"}]},              # structured ts -> TypeError -> skipped
    {"labels": {"org": "o", "state": "nv", "workflow": "s.yml", "outcome": "success"},
     "entries": []},                                                # empty -> no stream
]
obj = json.loads(encode_logs(batches))
assert len(obj["streams"]) == 1, obj
stream = obj["streams"][0]
assert stream["stream"] == {"org": "o", "state": "wy", "workflow": "s.yml", "outcome": "failure"}, stream
assert stream["values"][0] == ["1", "first", {"run_id": "9"}], stream["values"]  # sorted, ns as str, metadata stringified
assert "run_id" not in stream["stream"], "run id must never be a label"
payload = encode_logs(batches)
assert "mi" not in payload and "ak" not in payload, "KeyError/TypeError batches must be skipped whole"
assert ", " not in payload and '": ' not in payload, "payload must be compact + deterministic"
assert encode_logs([]) == '{"streams":[]}'
print("✓ logs shipper: labeled batches -> deterministic Loki JSON; run id in metadata, not labels")
print("✓ logs shipper: un-encodable batches (ValueError/KeyError/TypeError) skipped; the rest ships")
EOF

# Watermark store: a missing/empty file reads as {} (a lost cache is a look-back,
# not a crash); writes round-trip.
pipenv run python3 - <<'EOF'
import os, tempfile
from watermark import load_watermarks, save_watermarks

path = os.path.join(tempfile.mkdtemp(), "wm.json")
assert load_watermarks(path) == {}, "missing file must read as empty"
save_watermarks(path, {"o/r/w.yml": 42})
assert load_watermarks(path) == {"o/r/w.yml": 42}
open(path, "w").write("")
assert load_watermarks(path) == {}, "empty file must read as empty, not error"
# A truncated/garbled cache save must self-heal as the documented lost-cache
# recovery (bounded look-back), never crash — a crash would re-persist the
# corrupt file via the workflow's always-save and stay red every hour.
open(path, "w").write('{"o/r/w.yml": 4')
assert load_watermarks(path) == {}, "corrupt file must read as empty, not raise"
print("✓ watermark: missing/empty/corrupt reads as {}, writes round-trip")
EOF

# Harvester, offline (GitHub is fake fetchers): unpack the archive (top-level
# per-job .txt only, step folders ignored), parse GitHub's RFC3339 line-timestamp
# prefix (incl. a 7-digit fractional part and trailing Z), drop
# ##[group]/##[endgroup] noise, apply the volume policy (full logs for a failure,
# the last ~100 lines for a success), advance the per-repo/workflow watermark only
# across contiguous shipped runs (an in-progress run or a failed archive fetch
# halts advance so the run retries next sweep), bound a cold start to a 24h
# look-back, and never raise per repo.
pipenv run python3 - <<'EOF'
import io, zipfile
from datetime import datetime, timezone

from log_harvester import _to_ns, harvest_logs, parse_log_text, unpack_archive

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

def zip_of(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buf.getvalue()

assert _to_ns("2026-07-21T00:00:00Z") == 1784592000000000000
assert _to_ns("2026-07-21T00:00:00.5000000Z") == 1784592000500000000
assert _to_ns("nope") is None
assert [n for n, _ in unpack_archive(zip_of({"1_j.txt": "x\n", "j/1_step.txt": "dup\n"}))] == ["1_j.txt"]
parsed = parse_log_text("2026-07-21T11:00:00.0000000Z hi\ntail without ts\n", _to_ns("2026-07-21T11:00:00Z"))
assert parsed[0] == (_to_ns("2026-07-21T11:00:00Z"), "hi"), parsed
assert parsed[1] == (_to_ns("2026-07-21T11:00:00Z"), "tail without ts"), parsed
# A bare timestamp with no trailing space is a stamp with an empty message
# (noise-dropped downstream), never shipped verbatim as content.
bare = parse_log_text("2026-07-21T11:00:05Z\n", 0)
assert bare == [(_to_ns("2026-07-21T11:00:05Z"), "")], bare

juris = [{"org": "o", "state": "wy", "repo": "r", "expected_workflows": ["w.yml"]}]
FAIL = ("2026-07-21T11:00:00.0000000Z ##[group]setup\n"
        "2026-07-21T11:00:01.0000000Z building\n"
        "2026-07-21T11:00:02.0000000Z ##[endgroup]\n"
        "2026-07-21T11:00:03.0000000Z ERROR: boom\n")
def runs_fail(o, r, w):
    return [{"id": 100, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-21T11:00:00Z", "html_url": "u/100"}]
batches, wm, errors = harvest_logs(juris, {}, runs_fail, lambda o, r, i: zip_of({"1_j.txt": FAIL}), NOW)
assert errors == [] and len(batches) == 1, (errors, batches)
assert batches[0]["labels"] == {"org": "o", "state": "wy", "workflow": "w.yml", "outcome": "failure"}
assert batches[0]["watermark_key"] == "o/r/w.yml", "batch must name its watermark entry"
assert [e["line"] for e in batches[0]["entries"]] == ["building", "ERROR: boom"], "group markers dropped, full logs kept"
# Entries are stamped at COLLECTION time (NOW), not event time, with a per-stream
# offset for ordering — Grafana Cloud silently discards event-time-stamped old
# logs. The real event time is preserved as event_time metadata.
collection_ns = int(NOW.timestamp()) * 1_000_000_000
assert [e["timestamp_ns"] for e in batches[0]["entries"]] == [collection_ns, collection_ns + 1], \
    f"entries must be stamped at collection time + offset: {[e['timestamp_ns'] for e in batches[0]['entries']]}"
assert batches[0]["entries"][0]["metadata"] == {
    "run_id": "100", "run_url": "u/100", "job": "1_j",
    "event_time": "2026-07-21T11:00:01.000000000Z"}, batches[0]["entries"][0]["metadata"]
assert batches[0]["entries"][1]["metadata"]["event_time"] == "2026-07-21T11:00:03.000000000Z"
assert wm == {"o/r/w.yml": 100}

big = "".join(f"2026-07-21T11:00:00.0000000Z line {i}\n" for i in range(250))
def runs_ok(o, r, w):
    return [{"id": 5, "status": "completed", "conclusion": "success",
             "created_at": "2026-07-21T11:00:00Z", "html_url": "u"}]
b2, _, _ = harvest_logs(juris, {}, runs_ok, lambda o, r, i: zip_of({"1.txt": big}), NOW)
assert len(b2[0]["entries"]) == 100 and b2[0]["entries"][-1]["line"] == "line 249", "success tailed to 100"

# A failure keeps FULL logs but bounded to the last ~MAX_FAILURE_BYTES: an
# unbounded dump (a real 9 MB Florida run) times out the push and trips Loki's
# rate limit. Over-cap failures are truncated to the tail (error/traceback) with
# a marker; the last line — where the failure lands — always survives.
from log_harvester import MAX_FAILURE_BYTES
huge = "".join(f"2026-07-21T11:00:00.0000000Z filler line {i}\n" for i in range(200000))
huge += "2026-07-21T11:00:09.0000000Z FATAL: the actual error\n"
def runs_huge(o, r, w):
    return [{"id": 9, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-21T11:00:00Z", "html_url": "u"}]
b_huge, _, _ = harvest_logs(juris, {}, runs_huge, lambda o, r, i: zip_of({"1.txt": huge}), NOW)
kept_lines = [e["line"] for e in b_huge[0]["entries"]]
kept_bytes = sum(len(line.encode()) + 1 for line in kept_lines)
assert kept_bytes <= MAX_FAILURE_BYTES + 200, f"failure log not capped: {kept_bytes} bytes"
assert len(kept_lines) < 200001, "an over-cap failure must be truncated, not shipped whole"
assert kept_lines[-1] == "FATAL: the actual error", "the tail (the error) must survive the cap"
assert kept_lines[0].startswith("[fleet-monitor]") and "dropped" in kept_lines[0], \
    f"a truncation marker must lead the capped log: {kept_lines[0]}"
print("✓ harvester: an oversized failure log is capped to the tail with a truncation marker")

def runs_mix(o, r, w):
    return [{"id": 10, "status": "completed", "conclusion": "success",
             "created_at": "2026-07-21T11:00:00Z", "html_url": "u"},
            {"id": 11, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-21T11:30:00Z", "html_url": "u"},
            {"id": 12, "status": "in_progress", "conclusion": None,
             "created_at": "2026-07-21T11:45:00Z", "html_url": "u"}]
b3, wm3, _ = harvest_logs(juris, {"o/r/w.yml": 10}, runs_mix,
                          lambda o, r, i: zip_of({"1.txt": "2026-07-21T11:30:00.0000000Z x\n"}), NOW)
assert {e["metadata"]["run_id"] for b in b3 for e in b["entries"]} == {"11"}, "only the new completed run ships"
assert wm3 == {"o/r/w.yml": 11}, "watermark not advanced past the in-progress run"

def runs_hist(o, r, w):
    return [{"id": 1, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-01T00:00:00Z", "html_url": "u"},   # 3 weeks old -> skip
            {"id": 2, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-21T06:00:00Z", "html_url": "u"}]   # 6h old -> ship
b4, wm4, _ = harvest_logs(juris, {}, runs_hist,
                          lambda o, r, i: zip_of({"1.txt": "2026-07-21T06:00:00.0000000Z x\n"}), NOW)
assert {e["metadata"]["run_id"] for b in b4 for e in b["entries"]} == {"2"}, "cold start bounded to a 24h look-back"
b5, wm5, _ = harvest_logs(juris, wm4, runs_hist, lambda o, r, i: zip_of({"1.txt": "x\n"}), NOW)
assert b5 == [] and wm5 == wm4, "idempotent re-run with the same watermark ships nothing"

def boom(o, r, i):
    raise RuntimeError("archive 500")
b6, wm6, e6 = harvest_logs(juris, {}, runs_hist, boom, NOW)
assert b6 == [] and e6 and "archive 500" in e6[0], (b6, e6)
assert wm6.get("o/r/w.yml", 0) == 0, "watermark held below a run whose archive fetch failed"

# The look-back bounds every sweep, not just a cold start: with a warm watermark,
# a new-by-id run created outside the window is skipped by the same policy the
# cold start uses — so selection never wants a run the paged listing wouldn't fetch.
def runs_warm(o, r, w):
    return [{"id": 5, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-01T00:00:00Z", "html_url": "u"},   # past wm but 3 weeks old
            {"id": 6, "status": "completed", "conclusion": "failure",
             "created_at": "2026-07-21T06:00:00Z", "html_url": "u"}]
b7, wm7, _ = harvest_logs(juris, {"o/r/w.yml": 4}, runs_warm,
                          lambda o, r, i: zip_of({"1.txt": "2026-07-21T06:00:00.0000000Z x\n"}), NOW)
assert {e["metadata"]["run_id"] for b in b7 for e in b["entries"]} == {"6"}, b7
assert wm7 == {"o/r/w.yml": 6}, wm7

# A label the shipper would reject (control char) is a harvest-time error that
# HOLDS the watermark — never a batch silently dropped after the watermark moved.
bad_juris = [{"org": "o", "state": "w\ny", "repo": "r", "expected_workflows": ["w.yml"]}]
b8, wm8, e8 = harvest_logs(bad_juris, {}, runs_hist,
                           lambda o, r, i: zip_of({"1.txt": "x\n"}), NOW)
assert b8 == [] and e8 and "control character" in e8[0], (b8, e8)
assert wm8 == {}, "watermark must not advance for a batch the shipper would drop"
print("✓ harvester: unpack/parse/noise/volume policy; incremental watermark; look-back bounds every sweep; per-repo error isolation")
print("✓ harvester: a shipper-rejectable label errors at harvest time and holds the watermark")
EOF

# The live run listing pages until the harvest window is covered: stops on a
# short page, stops once a page dips past the look-back boundary, and never
# exceeds MAX_RUN_PAGES — so a burst of more than one page of new runs can't
# leave a gap for the watermark to leap. Offline: request_json is monkeypatched.
pipenv run python3 - <<'EOF'
from datetime import datetime, timedelta, timezone

import log_harvester

# A fixed anchor, threaded into github_log_fetchers the way _collect_logs
# threads the harvest now — pagination and selection must share one clock.
ANCHOR = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

def iso(hours_ago):
    return (ANCHOR - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

pages_requested = []
def fake_request_json(url, headers=None):
    from urllib.parse import parse_qs, urlparse
    page = int(parse_qs(urlparse(url).query)["page"][0])
    pages_requested.append(page)
    return {"workflow_runs": fake_request_json.pages.get(page, [])}
log_harvester.request_json = fake_request_json

full_recent = [{"id": 200 - i, "created_at": iso(1)} for i in range(30)]
full_old = [{"id": 100 - i, "created_at": iso(30)} for i in range(30)]

# Page 2's oldest run predates the boundary -> stop after 2 pages, keep both.
fake_request_json.pages = {1: full_recent, 2: full_old, 3: full_recent}
fetch_runs, _ = log_harvester.github_log_fetchers(ANCHOR)
runs = fetch_runs("o", "r", "w.yml")
assert pages_requested == [1, 2], pages_requested
assert len(runs) == 60, len(runs)

# A short page means no more runs -> one request.
pages_requested.clear()
fake_request_json.pages = {1: full_recent[:3]}
assert len(fetch_runs("o", "r", "w.yml")) == 3
assert pages_requested == [1], pages_requested

# All pages full and recent -> the MAX_RUN_PAGES cap bounds the requests.
pages_requested.clear()
fake_request_json.pages = {p: full_recent for p in range(1, 10)}
fetch_runs("o", "r", "w.yml")
assert pages_requested == [1, 2, 3, 4], pages_requested

# A missing/garbled created_at is not evidence of oldness: a full page whose
# only unparseable stamp would have coerced "old" must page on, not stop —
# stopping early would let the watermark leap runs that were never fetched.
pages_requested.clear()
one_bad = [dict(run) for run in full_recent]
one_bad[7] = {"id": 193}                                 # no created_at at all
fake_request_json.pages = {1: one_bad, 2: full_recent[:5]}
assert len(fetch_runs("o", "r", "w.yml")) == 35
assert pages_requested == [1, 2], "an unparseable stamp must not stop pagination"
pages_requested.clear()
all_bad = [{"id": 300 - i, "created_at": "garbled"} for i in range(30)]
fake_request_json.pages = {1: all_bad, 2: full_recent[:5]}
fetch_runs("o", "r", "w.yml")
assert pages_requested == [1, 2], "a page with no parseable stamps pages on"
print("✓ run listing: pages to the look-back boundary (anchored to the harvest now), stops on a")
print("  short page, caps at MAX_RUN_PAGES; unparseable stamps never fake oldness")
EOF

# Loki push wire format + missing-env guard, offline (fake urlopen).
pipenv run python3 - <<'EOF'
import base64
import urllib.request

from logs_push import push_logs

try:
    push_logs("{}", env={})
except RuntimeError as e:
    assert "GRAFANA_LOGS_URL, GRAFANA_LOGS_USER, GRAFANA_LOGS_KEY" in str(e), e
else:
    raise AssertionError("push_logs with empty env should raise")

class FakeResponse:
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *args): return False

calls = []
def ok_urlopen(request, timeout=None):
    calls.append(request)
    return FakeResponse()
urllib.request.urlopen = ok_urlopen

push_logs('{"streams":[]}', env={"GRAFANA_LOGS_URL": "https://l.test/loki/api/v1/push",
                                 "GRAFANA_LOGS_USER": "42", "GRAFANA_LOGS_KEY": "k"})
request = calls[0]
assert request.full_url == "https://l.test/loki/api/v1/push" and request.get_method() == "POST"
# The body is gzip-compressed (log payloads are multi-MB); Loki decodes it via
# Content-Encoding. Decompress to prove the payload round-trips.
assert request.get_header("Content-encoding") == "gzip", request.header_items()
import gzip as _gzip
assert _gzip.decompress(request.data) == b'{"streams":[]}', request.data
assert request.get_header("Authorization") == "Basic " + base64.b64encode(b"42:k").decode()
assert request.get_header("Content-type") == "application/json", request.header_items()
print("✓ logs push: Loki wire format (URL, POST, Basic auth, gzip json body) + missing-env guard")
EOF

# CLI logs leg: fixture archives in -> exact Loki push payload out (dry-run),
# byte-identical from the fixed --timestamp. The fixture covers a failed run
# (full logs, ##[group] noise dropped) and a successful run (tail); run/job ids
# land in structured metadata while labels stay org/state/workflow/outcome.
pipenv run python3 main.py collect --logs-only --dry-run \
  --log-fixture fixtures/log-runs --timestamp 1784635200 \
  > "$output_dir/logs-payload.json"
pipenv run python3 - <<'EOF'
import json

obj = json.load(open("__snapshots__/logs-payload.json"))
streams = {s["stream"]["outcome"]: s for s in obj["streams"]}
assert set(streams) == {"failure", "success"}, streams
fail_lines = [value[1] for value in streams["failure"]["values"]]
assert "ERROR: HTTP 500 from source" in fail_lines, fail_lines
assert "Traceback (most recent call last):" in fail_lines, fail_lines
lines = [value[1] for s in obj["streams"] for value in s["values"]]
assert not any("##[group]" in line or "##[endgroup]" in line for line in lines), "noise must be dropped"
assert all(set(s["stream"]) == {"org", "state", "workflow", "outcome"} for s in obj["streams"]), "labels capped"
assert all(value[2]["run_id"] for s in obj["streams"] for value in s["values"]), "run id in structured metadata"
assert all(value[2]["job"] == "1_scrape" for s in obj["streams"] for value in s["values"]), \
    "job identity (archive member name) in structured metadata"
# Entries are stamped at collection time (the pinned --timestamp 1784635200 =
# 1784635200000000000 ns), not their 2026-07-21 event time; the event time is
# preserved as event_time metadata so it survives the collection-time stamping.
assert all(int(value[0]) >= 1784635200000000000 for s in obj["streams"] for value in s["values"]), \
    "entries must be stamped at collection time, not their older event time"
assert all(value[2]["event_time"].startswith("2026-07-21T") for s in obj["streams"] for value in s["values"]), \
    "original event time must be preserved as event_time metadata"
print("✓ logs snapshot: fixture archives render to the exact Loki payload (collection-time stamps, event_time kept)")
EOF

# The log fixture's jurisdiction records are full fleet-record-shaped and
# validate against the same schema as every other record crossing the module
# boundary — drift between read_fleet output and what harvest_logs consumes
# must not go uncaught.
pipenv run python3 - <<'EOF'
import json
from pathlib import Path
from jsonschema import validate

schema = json.load(open("../../schemas/fleet-record.schema.json"))
lines = Path("fixtures/log-runs/jurisdictions.jsonl").read_text().splitlines()
for line in lines:
    validate(instance=json.loads(line), schema=schema)
print(f"✓ {len(lines)} log-fixture jurisdiction records validate against fleet-record.schema.json")
EOF

# Idempotency + recovery, end to end through the CLI with a fake Loki push:
# the first collection ships and advances the watermark; a second collection of
# the same window ships nothing (no run newer than the watermark); deleting the
# watermark recovers via the 24h look-back rather than re-shipping the full
# history. Driven in-process (CliRunner) so the fake urlopen counts real pushes.
pipenv run python3 - "$logs_wm" <<'EOF'
import os
import sys
import urllib.request

from click.testing import CliRunner

import main

wm = sys.argv[1]
if os.path.exists(wm):
    os.remove(wm)

pushes = []
class FakeResponse:
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *args): return False
def fake_urlopen(request, timeout=None):
    pushes.append(request.data)
    return FakeResponse()
urllib.request.urlopen = fake_urlopen

env = {"GRAFANA_LOGS_URL": "https://l.test/loki/api/v1/push",
       "GRAFANA_LOGS_USER": "42", "GRAFANA_LOGS_KEY": "k"}
args = ["collect", "--logs-only", "--log-fixture", "fixtures/log-runs",
        "--watermark-file", wm, "--timestamp", "1784635200"]

# Pushes go per workflow (one payload per watermark entry): the fixture's two
# repos are two watermark keys, so a shipping collection is exactly two pushes.
r1 = CliRunner().invoke(main.cli, args, env=env)
assert r1.exit_code == 0, (r1.output, r1.exception)
assert len(pushes) == 2, f"first collection must push once per workflow, got {len(pushes)}"

r2 = CliRunner().invoke(main.cli, args, env=env)
assert r2.exit_code == 0, (r2.output, r2.exception)
assert len(pushes) == 2, "a second collection of the same window must ship nothing (idempotent)"

os.remove(wm)  # a lost Actions cache
r3 = CliRunner().invoke(main.cli, args, env=env)
assert r3.exit_code == 0, (r3.output, r3.exception)
assert len(pushes) == 4, "a deleted watermark recovers via the look-back and ships the recent window again"
print("✓ logs CLI: idempotent re-run ships nothing; a deleted watermark recovers via the 24h look-back")
EOF

# Per-workflow push isolation: one workflow's un-pushable payload fails only its
# own logs and holds only its own watermark — the other workflow ships, its
# watermark saves, and the run exits nonzero (a red run means the collector
# needs attention, but it never un-ships the fleet's progress). The next sweep
# retries only the failed workflow.
pipenv run python3 - "$logs_wm" <<'EOF'
import gzip
import json
import os
import sys
import urllib.error
import urllib.request

import email.message
from click.testing import CliRunner

import main

wm = sys.argv[1]
if os.path.exists(wm):
    os.remove(wm)

pushes = []
class FakeResponse:
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *args): return False
def wy_fails_urlopen(request, timeout=None):
    pushes.append(request.data)
    if b'"state":"wy"' in gzip.decompress(request.data):  # bodies are gzipped
        raise urllib.error.HTTPError(request.full_url, 413, "Payload Too Large",
                                     email.message.Message(), None)
    return FakeResponse()
urllib.request.urlopen = wy_fails_urlopen

env = {"GRAFANA_LOGS_URL": "https://l.test/loki/api/v1/push",
       "GRAFANA_LOGS_USER": "42", "GRAFANA_LOGS_KEY": "k"}
args = ["collect", "--logs-only", "--log-fixture", "fixtures/log-runs",
        "--watermark-file", wm, "--timestamp", "1784635200"]

r1 = CliRunner().invoke(main.cli, args, env=env)
combined = r1.output + (r1.stderr or "")
assert r1.exit_code != 0, "a failed per-workflow push must exit nonzero"
assert "log push failed for 1 of 2 workflows" in combined, combined
saved = json.load(open(wm))
assert "govbot-openstates-scrapers/il-legislation/openstates-scrape.yml" in saved, saved
assert "govbot-openstates-scrapers/wy-legislation/openstates-scrape.yml" not in saved, \
    f"the failed workflow's watermark must hold: {saved}"

# Next sweep, push healthy again: only the held workflow re-ships.
def ok_urlopen(request, timeout=None):
    pushes.append(request.data)
    return FakeResponse()
urllib.request.urlopen = ok_urlopen
before = len(pushes)
r2 = CliRunner().invoke(main.cli, args, env=env)
assert r2.exit_code == 0, (r2.output, r2.exception)
assert len(pushes) == before + 1, "only the failed workflow should re-ship"
saved = json.load(open(wm))
assert len(saved) == 2, saved
os.remove(wm)
print("✓ logs CLI: a failed workflow push holds only its own watermark; the rest ship and save")
EOF

# collect's exit contract covers the logs leg: per-repo harvest errors exit 1
# (degraded must never look clean), unlike `run` which keeps them green.
pipenv run python3 - <<'EOF'
import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

import main

fixture = Path(tempfile.mkdtemp())
(fixture / "runs").mkdir()
(fixture / "jurisdictions.jsonl").write_text(json.dumps(
    {"org": "o", "state": "w\ny", "repo": "r", "expected_workflows": ["w.yml"]}) + "\n")
result = CliRunner().invoke(
    main.cli, ["collect", "--logs-only", "--dry-run", "--log-fixture", str(fixture),
               "--timestamp", "1784635200"])
combined = result.output + (result.stderr or "")
assert result.exit_code != 0, "collect --logs-only must exit nonzero on harvest errors"
assert "log harvest errors on 1 target(s)" in combined, combined
print("✓ collect --logs-only: per-repo harvest errors exit 1 (degraded never looks clean)")
EOF

# Combined mode (--metrics-only --logs-only): each leg runs to completion
# regardless of the other's failure — partial data still ships (or prints)
# first — and the failures merge into one exit-1 message. Dry-run: both payloads
# print even though the poller fixture carries an errored repo.
if pipenv run python3 main.py collect --metrics-only --logs-only --dry-run \
    --poller-records fixtures/poller-records.jsonl --log-fixture fixtures/log-runs \
    --timestamp 1784635200 > "$clean_out" 2> "$stderr_tmp"; then
  echo "✗ combined collect with an errored poller record should exit nonzero"
  exit 1
fi
if ! grep -q '^fleet_workflow_run,' "$clean_out" || ! grep -q '"streams":' "$clean_out"; then
  echo "✗ combined dry-run must print BOTH the metrics payload and the logs payload; got:"
  cat "$clean_out"
  exit 1
fi
if ! grep -q 'poll errors on 1 of 5 repos' "$stderr_tmp"; then
  echo "✗ combined collect should still report the poll errors; got:"
  cat "$stderr_tmp"
  exit 1
fi
echo "✓ collect combined mode: both payloads print, poll errors still exit 1"

# Both legs failing at once: the single exit-1 message carries BOTH fragments,
# proving the merge (not just one leg's failure surfacing). Metrics fails on the
# errored poller record; logs fails on a bad-label jurisdiction. Dry-run, no
# network. Driven in-process to read the merged ClickException message.
pipenv run python3 - <<'EOF'
import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

import main

fixture = Path(tempfile.mkdtemp())
(fixture / "runs").mkdir()
(fixture / "jurisdictions.jsonl").write_text(json.dumps(
    {"org": "o", "state": "w\ny", "repo": "r", "expected_workflows": ["w.yml"]}) + "\n")
result = CliRunner().invoke(main.cli, [
    "collect", "--metrics-only", "--logs-only", "--dry-run",
    "--poller-records", "fixtures/poller-records.jsonl",
    "--log-fixture", str(fixture), "--timestamp", "1784635200"])
combined = result.output + (result.stderr or "")
assert result.exit_code != 0, combined
assert "poll errors on 1 of 5 repos" in combined, f"metrics fragment missing: {combined}"
assert "log harvest errors on 1 target(s)" in combined, f"logs fragment missing: {combined}"
print("✓ collect combined mode: both legs failing merge into one exit-1 message")
EOF

# Combined push mode with Loki down: the metrics leg must still ship before the
# logs failure exits 1 — one leg's failure never silences the other's data.
pipenv run python3 - "$clean_records" "$logs_wm" <<'EOF'
import json
import os
import sys
import urllib.error
import urllib.request

import email.message
from click.testing import CliRunner

import main

clean_records, wm = sys.argv[1], sys.argv[2]
if os.path.exists(wm):
    os.remove(wm)

influx_pushes, loki_pushes = [], []
class FakeResponse:
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *args): return False
def loki_down_urlopen(request, timeout=None):
    # Distinguish the legs by endpoint, not body — the Loki body is now gzipped.
    # 413 (fail-fast 4xx) rather than 5xx: the real retry path would sleep for
    # real here, since the CLI cannot inject a fake sleep.
    if "/loki/" in request.full_url:
        loki_pushes.append(request.data)
        raise urllib.error.HTTPError(request.full_url, 413, "Payload Too Large",
                                     email.message.Message(), None)
    influx_pushes.append(request.data)
    return FakeResponse()
urllib.request.urlopen = loki_down_urlopen

result = CliRunner().invoke(main.cli, [
    "collect", "--metrics-only", "--logs-only",
    "--poller-records", clean_records, "--log-fixture", "fixtures/log-runs",
    "--watermark-file", wm, "--timestamp", "1784635200",
], env={
    "GRAFANA_PUSH_URL": "https://push.test/api/v1/push/influx/write",
    "GRAFANA_PUSH_USER": "123456", "GRAFANA_PUSH_KEY": "metrics-key",
    "GRAFANA_LOGS_URL": "https://l.test/loki/api/v1/push",
    "GRAFANA_LOGS_USER": "42", "GRAFANA_LOGS_KEY": "logs-key",
})
combined = result.output + (result.stderr or "")
assert result.exit_code != 0, "a failed logs leg must still exit nonzero in combined mode"
assert len(influx_pushes) == 1, "the metrics leg must ship even when the logs leg fails"
assert loki_pushes, "the logs leg must have attempted its pushes"
assert "log push failed" in combined, combined
saved = json.load(open(wm))
assert saved == {}, f"no watermark may advance when every Loki push failed: {saved}"
os.remove(wm)
print("✓ collect combined mode: metrics ship even when Loki is down; failures merge into exit 1")
EOF

# probe-loki: a bad credential (HTTP 401 on every push) exits nonzero without any
# ingest-window verdict — a failed push says nothing about the window.
pipenv run python3 - <<'EOF'
import email.message
import urllib.error
import urllib.request

from click.testing import CliRunner

import main


def unauthorized_urlopen(request, timeout=None):
    raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized",
                                 email.message.Message(), None)


urllib.request.urlopen = unauthorized_urlopen
result = CliRunner().invoke(main.cli, ["probe-loki"], env={
    "GRAFANA_LOGS_URL": "https://l.test/loki/api/v1/push",
    "GRAFANA_LOGS_USER": "42", "GRAFANA_LOGS_KEY": "bad-key"})
combined = result.output + (result.stderr or "")
assert result.exit_code != 0, combined
assert "push failed (HTTP 401)" in combined and "every probe push failed" in combined, combined
assert "queryable" not in combined and "ingest window" not in combined, \
    f"a failed push must not produce a window verdict: {combined}"
print("✓ probe-loki: a bad credential exits nonzero with no ingest-window verdict")
EOF

# probe-loki query-back: the truth-teller. Push succeeds (204) for every age, but
# only ages ≤2h are queryable; the probe must report the ~2h window and name the
# older ages as silently discarded — NOT trust the 204. Offline: a fake urlopen
# 204s pushes and answers query_range with data only for age ≤ 2.
pipenv run python3 - <<'EOF'
import re
import urllib.parse
import urllib.request

from click.testing import CliRunner

import main


class Resp:
    def __init__(self, body):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


def fake_urlopen(request, timeout=None):
    if request.data is not None:          # a push (POST) — accept with 204/empty
        return Resp(b"")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)["query"][0]
    age = int(re.search(r'age_hours="(\d+)"', query).group(1))
    # Simulate Grafana Cloud silently dropping anything older than 2h.
    if age <= 2:
        return Resp(b'{"data":{"result":[{"values":[["1","x"]]}]}}')
    return Resp(b'{"data":{"result":[]}}')


urllib.request.urlopen = fake_urlopen
result = CliRunner().invoke(main.cli, ["probe-loki"], env={
    "GRAFANA_LOGS_URL": "https://l.test/loki/api/v1/push",
    "GRAFANA_LOGS_USER": "42", "GRAFANA_LOGS_KEY": "rw-key"})
combined = result.output + (result.stderr or "")
assert result.exit_code == 0, combined
assert " 1h old: accepted AND queryable" in combined, combined
assert " 3h old: pushed (204) but silently discarded" in combined, combined
assert "ingest window ≈ 2h" in combined, combined
print("✓ probe-loki: query-back detects silent discard and reports the real ~2h window")
EOF

# A malformed config on the logs-only path fails with a clean CLI error line,
# the same contract as list-fleet and the metrics poll — never a raw traceback.
bad_config_dir=$(ls -d fixtures-invalid/*/ | head -1)
if pipenv run python3 main.py collect --logs-only --config-dir "$bad_config_dir" \
    > /dev/null 2> "$stderr_tmp"; then
  echo "✗ collect --logs-only with a broken config should exit nonzero"
  exit 1
fi
if ! grep -q '^Error:' "$stderr_tmp"; then
  echo "✗ collect --logs-only should fail with a clean Error: line; stderr was:"
  cat "$stderr_tmp"
  exit 1
fi
echo "✓ collect --logs-only: a malformed config fails with a clean Error: line"

# The orchestrator `run` wires the logs leg only when a log source is present: a
# dry-run with the fixture prints the metrics + heartbeat payload AND the Loki
# stream payload; a metrics-only run (no log source) omits it — the run-payload
# snapshot above carries no streams.
run_with_logs=$(pipenv run python3 main.py run --dry-run --poller-records "$clean_records" \
  --log-fixture fixtures/log-runs --timestamp 1784635200 2> /dev/null)
if ! echo "$run_with_logs" | grep -q '^fleet_collector_heartbeat '; then
  echo "✗ run --log-fixture must still ship metrics + heartbeat"
  exit 1
fi
if ! echo "$run_with_logs" | grep -q '"streams":'; then
  echo "✗ run --log-fixture must also ship the harvested logs"
  exit 1
fi
if grep -q '"streams":' "$output_dir/run-payload.txt"; then
  echo "✗ a metrics-only run (no log source) must not emit a logs payload"
  exit 1
fi
echo "✓ run: the logs leg ships when a log source is present, and is skipped otherwise"

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

# API budget: one sweep of the real fleet, against the GITHUB_TOKEN ceiling of
# 1000 requests/hour. Not snapshotted — the count moves with the fleet; this
# locks the ceiling, not the number.
#
# It counts BOTH legs. The old check looked only at the metrics leg against a
# flat 400, which understated a sweep by the logs leg's run-listing request per
# workflow — and it fired for real when upstream added a third fleet config plus
# a second production workflow, at which point the true cost was over the
# ceiling, not merely over 400. Budget the whole sweep or the tripwire lies.
pipenv run python3 - <<'EOF'
from fleet_config import read_fleet
from fleet_poller import DATA_PATHS, estimate_request_count

# GITHUB_TOKEN's documented limit for an Actions workflow, and the sweep runs
# hourly, so one sweep must fit inside one hour's budget with room for the
# archive downloads (one per NEW run, unpredictable and unbounded by config).
# 80% leaves ~200 requests/hour for those; the measured fleet sits at ~62%.
TOKEN_LIMIT_PER_HOUR = 1000
HEADROOM = 0.8

records = read_fleet("../pipeline-manager")
metrics_requests = estimate_request_count(records)
# The logs leg lists runs once per workflow; archive downloads are extra and
# depend on how many runs actually finished, which is why the ceiling keeps 40%.
logs_requests = sum(len(r["expected_workflows"]) for r in records)
count = metrics_requests + logs_requests
budget = int(TOKEN_LIMIT_PER_HOUR * HEADROOM)
assert count < budget, (
    f"fleet sweep now costs {count} GitHub requests/hour ({metrics_requests} metrics + "
    f"{logs_requests} log listings) against a {TOKEN_LIMIT_PER_HOUR}/hour token limit; "
    "revisit the polling strategy or exclude a fleet"
)
utilisation = 100 * count / TOKEN_LIMIT_PER_HOUR
print(f"✓ API budget: one sweep of the real fleet = {count} GitHub requests "
      f"({metrics_requests} metrics + {logs_requests} log listings) = "
      f"{utilisation:.0f}% of the {TOKEN_LIMIT_PER_HOUR}/hour token limit")
if utilisation > 60:
    # Not a failure — a heads-up that the next fleet or workflow may not fit.
    print(f"· note: the sweep is over 60% of the token budget; one more fleet or "
          f"workflow would need a polling-strategy change")

# Every real-fleet base template needs a DATA_PATHS entry, or the first live
# sweep after a new template ships would fail at startup while snapshots
# stayed green.
missing = {r["base_template"] for r in records} - DATA_PATHS.keys()
assert not missing, f"real-fleet base template(s) missing from DATA_PATHS: {sorted(missing)}"
print("✓ data paths: every real-fleet base template has a DATA_PATHS entry")

# Non-production fleets stay out of the sweep by default. `chn-openstates-test`
# mirrors the files fleet against govbot-test and its own header says some
# locales are expected to fail — monitoring it would put permanent expected-red
# on the board, page someone once alerting lands, and (with its 56 repos ×
# 2 workflows) take the sweep over the token ceiling above.
from fleet_config import EXCLUDED_FLEETS

fleets = {r["fleet"] for r in records}
assert not fleets & set(EXCLUDED_FLEETS), sorted(fleets & set(EXCLUDED_FLEETS))
# ...but the config stays the authority: opting out restores everything, so the
# skip is a visible, reversible statement about what is worth alerting on.
everything = {r["fleet"] for r in read_fleet("../pipeline-manager", exclude_fleets=())}
skipped = everything - fleets
print(f"✓ fleet exclusion: monitoring {sorted(fleets)}"
      + (f", skipping {sorted(skipped)}" if skipped else " (nothing to skip in this checkout)"))
EOF

# Dashboard: built as data, committed rendered. The checks below are the whole
# test for it — there is no snapshot file, because the committed artifact
# (dashboards/fleet-overview.json) IS the snapshot: the drift check further down
# regenerates it and fails if the repo copy no longer matches the builder.
pipenv run python3 - <<'EOF'
import json
import re

from dashboard import (DEFAULT_LOGS_DATASOURCE, DEFAULT_METRICS_DATASOURCE,
                       OBSERVED_MAX_SWEEP_GAP_HOURS, SCRAPE_WORKFLOW, build_dashboard,
                       encode_dashboard)

board = build_dashboard()
panels = {p["title"]: p for p in board["panels"] if "title" in p}
variables = {v["name"]: v for v in board["templating"]["list"]}


def colors(node):
    """Every colour named anywhere under a panel, however nested."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "color" and isinstance(value, str):
                found.append(value)
            elif key == "color" and isinstance(value, dict) and "fixedColor" in value:
                found.append(value["fixedColor"])
            else:
                found.extend(colors(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(colors(item))
    return found


def datasource_uids(node):
    found = []
    if isinstance(node, dict):
        if set(node) >= {"type", "uid"} and node["type"] in ("prometheus", "loki"):
            found.append(node["uid"])
        for value in node.values():
            found.extend(datasource_uids(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(datasource_uids(item))
    return found


# 1. Datasources are pickers, not UIDs — a UID belongs to one stack, and the
#    committed JSON has to import into any of them.
assert variables["metrics"]["type"] == "datasource", variables["metrics"]
assert variables["metrics"]["query"] == "prometheus", variables["metrics"]
assert variables["logs"]["query"] == "loki", variables["logs"]
# ...and each defaults to this fleet's own stack, because the import screen never
# asks and Grafana's own fallback is the first datasource of the type in name
# order — on Grafana Cloud as likely to be grafanacloud-usage as the real one.
assert variables["metrics"]["current"]["value"] == DEFAULT_METRICS_DATASOURCE, variables["metrics"]
assert variables["logs"]["current"]["value"] == DEFAULT_LOGS_DATASOURCE, variables["logs"]
uids = datasource_uids(board["panels"])
assert uids, "no panel datasource references found"
assert set(uids) <= {"${metrics}", "${logs}"}, sorted(set(uids))

# 2. A fresh stack must accept this as a NEW dashboard; a numeric id would
#    collide with whatever holds it there.
assert board["id"] is None, board["id"]
assert board["uid"] == "fleet-monitor-overview", board["uid"]
ids = [p["id"] for p in board["panels"]]
assert len(ids) == len(set(ids)), ids

# 2b. The collector sweeps hourly and an instant query looks back only 5
#     minutes, so a bare selector leaves every metric panel empty for ~55
#     minutes of each hour — a whole-board "No data" that every offline check
#     here would otherwise pass. Observed on a real import; locked so it cannot
#     come back.
#
#     Derived from the board, not a hand-written list of titles: a sixth metric
#     panel added later must be covered too, or the same regression returns for
#     it with a green suite. And the window is asserted against a measured sweep
#     gap rather than against LOOKBACK itself — importing the constant under test
#     would let LOOKBACK="1m" reintroduce the exact bug and stay green.
#
#     The gap is MEASURED, not the cron expression. The workflow says hourly;
#     GitHub runs scheduled workflows best-effort and on a fork's non-default
#     branch they drift hard — 25 consecutive sweeps showed a median of 2.0h and
#     a max of 3.6h. Sizing the window off "0 * * * *" is what blanked the board
#     a second time, so this asserts real headroom over the observed worst case.
metric_panels = [
    p for p in board["panels"]
    if p.get("datasource", {}).get("uid") == "${metrics}"
]
assert len(metric_panels) == 3, [p.get("title") for p in metric_panels]
for panel in metric_panels:
    target = panel["targets"][0]
    expr = target["expr"]
    assert expr.startswith("last_over_time("), (panel["title"], expr)
    window = re.search(r"\[(\d+)([smh])\]\)$", expr)
    assert window, (panel["title"], expr)
    hours = int(window.group(1)) * {"s": 1 / 3600, "m": 1 / 60, "h": 1}[window.group(2)]
    assert hours >= 1.5 * OBSERVED_MAX_SWEEP_GAP_HOURS, (panel["title"], expr, hours)
    # Still an instant vector, so the table transformations and the stat
    # reducer keep working unchanged.
    assert target["instant"] is True, (panel["title"], target)
assert OBSERVED_MAX_SWEEP_GAP_HOURS >= 3.6, OBSERVED_MAX_SWEEP_GAP_HOURS

# 3. One status grid per workflow — 112 tiles in a single panel shrank the text
#    past legibility, so the split is the readability fix, not decoration.
#    Scrapers is pinned to the top (the fleet's entry point, worth seeing without
#    scrolling); every OTHER workflow is generated by Grafana's panel repeat and
#    sits after the logs. Only the scrape may be named in dashboard.py: a
#    hardcoded workflow list is how `extract-text.yml` shipped upstream and went
#    unmonitored, and no offline check could have caught it.
ordered = sorted((p["gridPos"]["y"], p["title"]) for p in board["panels"] if "title" in p)
titles = [t for _, t in ordered]
assert titles[0] == "Scrapers", titles
assert titles.index("Data freshness") < titles.index("Run logs"), titles

scrapers = panels["Scrapers"]
assert f'workflow="{SCRAPE_WORKFLOW}"' in scrapers["targets"][0]["expr"], scrapers["targets"][0]
assert "repeat" not in scrapers, scrapers.get("repeat")

repeated = next(p for p in board["panels"] if p.get("repeat"))
assert repeated["repeat"] == "other_workflow", repeated["repeat"]
assert repeated["title"] == "$other_workflow", repeated["title"]
# REGEX matcher, never exact. Grafana interpolates a multi-value variable into a
# Prometheus query using the regex form — `(format.yml)`, parentheses included —
# even where a repeat has scoped it to one value, so `workflow="$var"` compares
# against a literal "(format.yml)" and matches nothing. That renders "No data"
# under a title that interpolated as plain text and reads perfectly right, which
# is exactly how it shipped. The rule is asserted over every panel below.
assert 'workflow=~"$other_workflow"' in repeated["targets"][0]["expr"], repeated["targets"][0]
for panel in board["panels"]:
    for target in panel.get("targets", []):
        assert '="$' not in target.get("expr", ""), (panel.get("title"), target.get("expr"))
# After the logs, as laid out deliberately.
assert repeated["gridPos"]["y"] > panels["Run logs"]["gridPos"]["y"], ordered
# The repeat variable is every workflow EXCEPT the pinned one, excluded in the
# query itself — otherwise the scrapers grid renders a second time at the bottom.
other = variables["other_workflow"]
assert other["type"] == "query", other
assert f'workflow!="{SCRAPE_WORKFLOW}"' in other["query"]["query"], other["query"]
assert other["multi"] and other["includeAll"], other

for grid in (scrapers, repeated):
    # A tile is its jurisdiction and nothing else: the workflow is the panel it
    # sits in now, so repeating it per tile only shrank the identifying part.
    assert grid["targets"][0]["legendFormat"] == "{{state}}", grid["targets"][0]
    # ...rendered as large as the OK/FAILING beside it.
    text = grid["options"]["text"]
    assert text["titleSize"] == text["valueSize"], text
    for target in grid["targets"]:
        assert target["instant"] is True, target

    # Paused jurisdictions live in the SAME grid (a separate panel was an empty
    # box whenever the whole fleet was in session), dimmed via an override on
    # the second query's frame — the only way Grafana will colour some tiles by
    # value and leave others flat.
    active, paused = grid["targets"]
    assert 'paused="false"' in active["expr"], active["expr"]
    assert 'paused="true"' in paused["expr"], paused["expr"]
    assert paused["refId"] == "B", paused
    options = grid["fieldConfig"]["defaults"]["mappings"][0]["options"]
    assert options["0"] == {"color": "red", "index": 0, "text": "FAILING"}, options
    assert options["1"] == {"color": "green", "index": 1, "text": "OK"}, options
    override = next(
        o for o in grid["fieldConfig"]["overrides"]
        if o["matcher"] == {"id": "byFrameRefID", "options": "B"}
    )
    properties = {p["id"]: p["value"] for p in override["properties"]}
    assert properties["color"] == {"fixedColor": "text", "mode": "fixed"}, properties
    paused_options = properties["mappings"][0]["options"]
    assert paused_options["0"]["text"].startswith("paused"), paused_options
    assert paused_options["1"]["text"].startswith("paused"), paused_options
    # A paused tile is never red, whatever its last run did.
    assert "red" not in repr(properties).lower(), properties

# 4. One full-width freshness table for the whole fleet, red exactly at the 48h
#    alert line (one number, so dashboard and alert can never disagree), paused
#    carried as a column rather than a second table, in-session rows first with
#    the worst staleness on top, and every row linking to its own filtered view.
fresh = panels["Data freshness"]
assert "Data freshness · paused" not in panels, list(panels)
assert fresh["gridPos"]["w"] == 24, fresh["gridPos"]
target = fresh["targets"][0]
assert "fleet_repo_data_commit_age_hours{" in target["expr"], target["expr"]
assert target["instant"] is True and target["format"] == "table", target
# No paused filter: one query covers the fleet.
assert "paused=" not in target["expr"], target["expr"]
# ...and the paused label survives as a column rather than being dropped.
organize = next(t for t in fresh["transformations"] if t["id"] == "organize")
assert not organize["options"]["excludeByName"].get("paused"), organize
sort = next(t for t in fresh["transformations"] if t["id"] == "sortBy")["options"]["sort"]
assert sort[0] == {"desc": False, "field": "paused"}, sort
assert sort[1] == {"desc": True, "field": "Value"}, sort
steps = fresh["fieldConfig"]["defaults"]["thresholds"]["steps"]
assert {"color": "red", "value": 48} in steps, steps
assert any(s["color"] == "green" and s["value"] is None for s in steps), steps
# The paused column is a label, not a measurement: it must not be coloured by
# the staleness thresholds.
paused_column = next(
    o for o in fresh["fieldConfig"]["overrides"] if o["matcher"]["options"] == "paused"
)
paused_properties = {p["id"]: p["value"] for p in paused_column["properties"]}
assert paused_properties["custom.cellOptions"] == {"type": "auto"}, paused_properties
assert "red" not in repr(paused_properties).lower(), paused_properties
# The row link narrows the whole board through the single `state` picker. It is
# an absolute dashboard path: a bare "?var=..." relative URL rewrote the address
# bar and re-ran nothing, so the link looked live and did nothing.
links = fresh["fieldConfig"]["defaults"]["links"]
assert links, "no data link on the freshness table"
assert links[0]["url"].startswith("/d/fleet-monitor-overview"), links
assert "var-state=${__data.fields.state}" in links[0]["url"], links
# The jurisdiction, not one of its two repos: var-org would hide the sibling.
assert "var-org=" not in links[0]["url"], links
# Carry the chosen time range through, so a drill-down does not silently reset it.
assert "${__url_time_range}" in links[0]["url"], links

# 5. The logs panel filters on every stream label the harvester ships, each as a
#    regex matcher so multi-select "All" and a single pick both work. Run id
#    and run URL are structured metadata, not labels, so they surface by
#    expanding a line — log details must stay on.
#
#    One jurisdiction picker drives the whole board — grids, table, and logs —
#    so the filter shown at the top is the filter applied everywhere.
logs = panels["Run logs"]
assert logs["type"] == "logs", logs["type"]
for label in ("state", "org", "workflow", "outcome"):
    assert f'{label}=~"${label}"' in logs["targets"][0]["expr"], logs["targets"][0]["expr"]
assert "log_state" not in repr(board["templating"]), "a second jurisdiction picker came back"
for title in ("Scrapers", "Data freshness", "$other_workflow"):
    assert 'state=~"$state"' in panels[title]["targets"][0]["expr"], title
assert logs["options"]["enableLogDetails"] is True, logs["options"]
assert logs["options"]["sortOrder"] == "Descending", logs["options"]

# 6. Pickers are label-driven (a new jurisdiction appears without a dashboard
#    edit) and URL-synced, which is what makes a filtered view a shareable link.
#    Each speaks its own datasource's variable-query dialect: a Prometheus-shaped
#    query on the Loki picker leaves it empty, which blanks the logs panel.
for name in ("state", "org", "workflow"):
    variable = variables[name]
    assert variable["type"] == "query", variable
    assert variable["datasource"]["type"] == "prometheus", variable
    assert variable["query"]["query"] == f"label_values(fleet_workflow_run_status, {name})", variable
    # Editor-state keys are deliberately absent: a partial set opens the
    # variable editor half-populated, and saving from there writes back an
    # empty label_values() that resolves to nothing.
    assert set(variable["query"]) == {"query", "refId"}, variable
    assert variable["multi"] and variable["includeAll"], variable
outcome = variables["outcome"]
assert outcome["datasource"]["type"] == "loki", outcome
# Loki's own dialect (type 1 = label values), scoped to fleet streams so another
# producer's `outcome` label in the same logs instance can't leak into the picker.
assert outcome["query"]["type"] == 1 and outcome["query"]["label"] == "outcome", outcome
assert outcome["query"]["stream"] == '{state=~".+"}', outcome
# Every picker needs an explicit allValue: blank, Grafana expands "All" to an
# alternation of the options it resolved, and to the EMPTY STRING when it
# resolved none — turning each =~ matcher into one that matches nothing. A
# not-yet-populated picker would silently blank every panel that uses it.
#
# It must be ".+", not ".*": LogQL rejects a stream selector whose every matcher
# is empty-compatible, so with all four pickers on All (the default on a fresh
# import) ".*" makes the logs panel a parse error rather than an empty result.
for name in ("state", "org", "workflow", "outcome", "other_workflow"):
    assert variables[name]["allValue"] == ".+", variables[name]
    assert variables[name].get("skipUrlSync") is not True, variables[name]

# Proven on the rendered selector, not just the variable: interpolate every
# picker to its All value and confirm the logs query still holds one matcher
# that cannot match empty.
interpolated = re.sub(r"\$(state|org|workflow|outcome)", ".+", logs["targets"][0]["expr"])
matchers = re.findall(r'(\w+)\s*=~\s*"([^"]*)"', interpolated)
assert matchers, interpolated
assert any(not re.fullmatch(value, "") for _, value in matchers), interpolated

# 7. Nothing volatile in the encoding — a timestamp or a run-varying id would
#    make the committed artifact drift on every render. (Determinism itself is
#    proven by the byte diff against the committed JSON further down, which is a
#    real oracle; comparing encode_dashboard() to itself in one process is not.)
encoded = encode_dashboard()
assert not re.search(r"20\d\d-\d\d-\d\dT", encoded), "a timestamp leaked into the dashboard"
print(f"✓ dashboard: {len(board['panels'])} panels, parameterized datasources, "
      "scrapers before formatters, paused dimmed inline, logs filtered on all four labels")
EOF

# The committed dashboard must be exactly what the builder produces — otherwise
# the JSON people import and the code reviewers read have quietly diverged.
dashboard_tmp=$(mktemp)
pipenv run python3 main.py dashboard > "$dashboard_tmp"
if ! diff -u dashboards/fleet-overview.json "$dashboard_tmp"; then
  echo "✗ dashboards/fleet-overview.json is stale; regenerate it:"
  echo "    pipenv run python3 main.py dashboard --out dashboards/fleet-overview.json"
  rm -f "$dashboard_tmp"
  exit 1
fi
rm -f "$dashboard_tmp"
echo "✓ dashboard: committed dashboards/fleet-overview.json matches the builder"

# The import check pushes to a real stack, so like every other live path it must
# self-skip without credentials; the offline suite locks that skip.
dashboard_skip=$(env -u GRAFANA_DASHBOARD_URL -u GRAFANA_DASHBOARD_KEY \
  pipenv run python3 main.py check-dashboard 2>&1)
if ! echo "$dashboard_skip" | grep -q "dashboard check skipped"; then
  echo "✗ check-dashboard without credentials should skip cleanly; got:"
  echo "$dashboard_skip"
  exit 1
fi
echo "✓ check-dashboard: skips cleanly when credentials are absent"

# Offline proof of the import itself: a fake Grafana answers the push and the
# read-back, so the request shape (endpoint, bearer auth, overwrite-by-uid) and
# the rejection path are both tested without an account. The real import runs
# opt-in below.
pipenv run python3 - <<'EOF'
import json
import urllib.error
import urllib.request
from io import BytesIO

from click.testing import CliRunner

import main
from dashboard import DASHBOARD_UID, build_dashboard

CREDS = {"GRAFANA_DASHBOARD_URL": "https://stack.grafana.net/", "GRAFANA_DASHBOARD_KEY": "tok"}


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def run(env, respond):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return respond(request)

    real, urllib.request.urlopen = urllib.request.urlopen, fake_urlopen
    try:
        return CliRunner().invoke(main.cli, ["check-dashboard"], env=env), calls
    finally:
        urllib.request.urlopen = real


def happy(request):
    if request.full_url.endswith("/api/dashboards/db"):
        return FakeResponse(json.dumps({"uid": DASHBOARD_UID, "status": "success"}).encode())
    return FakeResponse(json.dumps({"dashboard": build_dashboard()}).encode())


ok, calls = run(CREDS, happy)
assert ok.exit_code == 0, ok.output + str(ok.exception)
posted, fetched = calls[0], calls[-1]
assert posted.full_url == "https://stack.grafana.net/api/dashboards/db", posted.full_url
assert posted.get_header("Authorization") == "Bearer tok", posted.header_items()
body = json.loads(posted.data)
assert body["dashboard"]["uid"] == DASHBOARD_UID, body["dashboard"]["uid"]
# Idempotent by uid: a re-run updates the same dashboard rather than erroring or
# littering copies across the stack.
assert body["overwrite"] is True, body
# A 200 on the push is not proof it renders, so the check reads it back by uid.
assert fetched.full_url == f"https://stack.grafana.net/api/dashboards/uid/{DASHBOARD_UID}", (
    fetched.full_url
)


def rejected(request):
    raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)


bad, _ = run(CREDS, rejected)
assert bad.exit_code != 0, bad.output
assert "400" in bad.output, bad.output

# A push that succeeds but comes back missing panels is a failure, not a pass:
# Grafana will happily store a payload it then renders as an empty dashboard.
def truncated(request):
    if request.full_url.endswith("/api/dashboards/db"):
        return FakeResponse(json.dumps({"status": "success"}).encode())
    return FakeResponse(json.dumps({"dashboard": {"panels": []}}).encode())


empty, _ = run(CREDS, truncated)
assert empty.exit_code != 0, empty.output
assert "0 panels" in empty.output, empty.output


# Panels alone are not proof of a working import. Every panel filters on
# `=~"$state"` and points at `${metrics}`/`${logs}`, so a variable Grafana
# declined to migrate leaves all five panels present and all five rendering
# nothing — a blank board that a panel count reports as a clean import. This is
# the check that was missing when a real import came back all "No data".
def loads_as(dashboard):
    def respond(request):
        if request.full_url.endswith("/api/dashboards/db"):
            return FakeResponse(json.dumps({"uid": DASHBOARD_UID, "status": "success"}).encode())
        return FakeResponse(json.dumps({"dashboard": dashboard}).encode())

    return respond


board = build_dashboard()
for dropped in ("state", "outcome", "metrics"):
    mangled = json.loads(json.dumps(board))
    mangled["templating"]["list"] = [
        v for v in mangled["templating"]["list"] if v["name"] != dropped
    ]
    lost, _ = run(CREDS, loads_as(mangled))
    assert lost.exit_code != 0, (dropped, lost.output)
    assert dropped in lost.output, (dropped, lost.output)

none_at_all = json.loads(json.dumps(board))
none_at_all["templating"] = {"list": []}
blank, _ = run(CREDS, loads_as(none_at_all))
assert blank.exit_code != 0, blank.output


# Presence by name is not enough — that is exactly how the first broken import
# passed. A picker stripped of its all-value, or repointed at the wrong
# datasource, resolves to nothing and blanks every panel that filters on it.
def mangled(name, key, value):
    copy = json.loads(json.dumps(board))
    for variable in copy["templating"]["list"]:
        if variable["name"] == name:
            variable[key] = value
    return copy


for name, key, value in (
    ("state", "allValue", ""),
    ("outcome", "datasource", {"type": "prometheus", "uid": "${metrics}"}),
):
    hollow, _ = run(CREDS, loads_as(mangled(name, key, value)))
    assert hollow.exit_code != 0, (name, key, hollow.output)
    assert name in hollow.output, (name, key, hollow.output)

intact, _ = run(CREDS, loads_as(board))
assert intact.exit_code == 0, intact.output + str(intact.exception)
assert f"{len(board['templating']['list'])} variables" in intact.output, intact.output
print("✓ check-dashboard: pushes by uid, reads back panels AND variables, fails on rejection, "
      "on a hollow import, on a dropped picker, and on one that survives in name only")
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

# The Loki ingest-window probe self-skips without credentials the same way, so a
# credential-free render stays offline; the real probe runs only with GRAFANA_LOGS_*.
probe_skip=$(env -u GRAFANA_LOGS_URL -u GRAFANA_LOGS_USER -u GRAFANA_LOGS_KEY \
  pipenv run python3 main.py probe-loki 2>&1)
if ! echo "$probe_skip" | grep -q "loki probe skipped"; then
  echo "✗ probe-loki without credentials should skip cleanly; got:"
  echo "$probe_skip"
  exit 1
fi
echo "✓ probe-loki: skips cleanly when credentials are absent"

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

# Same bargain for the dashboard import: it writes a real dashboard into a real
# stack, so a bare render never does it even on a machine with GRAFANA_DASHBOARD_*
# set. Opting in makes the render the automated import check.
if [ "${FLEET_MONITOR_DASHBOARD_CHECK:-}" = "1" ]; then
  pipenv run python3 main.py check-dashboard
else
  echo "· check-dashboard (real import) not run; opt in with FLEET_MONITOR_DASHBOARD_CHECK=1"
fi

# Alerting: built as data, committed rendered — the same bargain as the
# dashboard, and with the same oracle. There is no snapshot file because the
# committed alerting/*.yaml ARE the snapshot; the drift check below regenerates
# them and fails if the repo copies no longer match the builder.
pipenv run python3 - <<'EOF'
import ast
import re
from pathlib import Path

import yaml

from dashboard import (DASHBOARD_UID, LOOKBACK as LOOKBACK_WINDOW,
                       OBSERVED_MAX_SWEEP_GAP_HOURS, STALE_HOURS)
from alerting import (CONTACT_POINT, CONTACT_POINTS_FILE, COVERAGE_BASELINE,
                      COVERAGE_TOLERANCE, COVERAGE_UID, EVAL_INTERVAL, FOLDER,
                      HEARTBEAT_UID, PENDING_PERIOD, POLICY_FILE, ROUTE_LABEL,
                      RULES_FILE, RUN_FAILED_UID, STALE_UID,
                      build_contact_point, build_policy, build_rule_group,
                      placeholders, render_documents, UnresolvedPlaceholder)
from alerts_provision import _load, _resolve

group = build_rule_group()
rules = {r["uid"]: r for r in group["rules"]}
assert set(rules) == {RUN_FAILED_UID, STALE_UID, HEARTBEAT_UID, COVERAGE_UID}, sorted(rules)


def condition(rule):
    """The evaluator a rule fires on, found through the rule's own `condition`."""
    node = next(q for q in rule["data"] if q["refId"] == rule["condition"])
    assert node["model"]["type"] == "threshold", node["model"]
    return node["model"]["conditions"][0]["evaluator"]


# 1. Paused jurisdictions never page. An out-of-session state whose scrape fails
#    is the legislative calendar, not a fault — the PRD's whole reason the metric
#    carries a `paused` label at all. Filtered in the query, so a paused state
#    doesn't even reach the notification policy.
for uid in (RUN_FAILED_UID, STALE_UID):
    exprs = [q["model"]["expr"] for q in rules[uid]["data"] if "expr" in q.get("model", {})]
    assert exprs and all('paused="false"' in e for e in exprs), (uid, exprs)
# The heartbeat series carries no labels at all, so it filters on nothing.
dead_expr = rules[HEARTBEAT_UID]["data"][0]["model"]["expr"]
assert "paused" not in dead_expr and "state" not in dead_expr, dead_expr

# 2. Thresholds, as explicit expression nodes rather than numbers buried in a
#    PromQL string — the number a rule fires on is the thing a reviewer most
#    wants to see, and the thing that must not drift from the dashboard.
assert condition(rules[RUN_FAILED_UID]) == {"type": "lt", "params": [1]}, rules[RUN_FAILED_UID]
assert condition(rules[STALE_UID]) == {"type": "gt", "params": [STALE_HOURS]}, rules[STALE_UID]
assert condition(rules[HEARTBEAT_UID]) == {"type": "gt", "params": [0]}, rules[HEARTBEAT_UID]
assert condition(rules[COVERAGE_UID]) == {"type": "gt", "params": [COVERAGE_TOLERANCE]}, \
    rules[COVERAGE_UID]
for uid, rule in rules.items():
    types = [q["model"].get("type") for q in rule["data"]]
    assert types == [None, "reduce", "threshold"], (uid, types)

# 2b. The 48 is the dashboard's, IMPORTED and not restated. Asserting the value
#     proves nothing — `condition(...) == {"params": [STALE_HOURS]}` compares the
#     builder's output against the same constant the builder consumed, and passes
#     just as happily if alerting.py declares its own 48. (Nor does an identity
#     check help: CPython interns small ints, so a restated 48 `is` the imported
#     one.) So the assertion is on the source itself — alerting.py must import the
#     name and must never bind it.
source = Path("alerting.py").read_text()
tree = ast.parse(source)
imported = {
    alias.name
    for node in ast.walk(tree)
    if isinstance(node, ast.ImportFrom) and node.module == "dashboard"
    for alias in node.names
}
assert "STALE_HOURS" in imported, sorted(imported)
bound = {
    target.id
    for node in ast.walk(tree)
    if isinstance(node, ast.Assign)
    for target in node.targets
    if isinstance(target, ast.Name)
}
assert "STALE_HOURS" not in bound, "alerting.py restates STALE_HOURS instead of importing it"
assert STALE_HOURS == 48, STALE_HOURS
# The coverage rule's two numbers, pinned as literals for the same reason: an
# assertion that compares the built rule against the constant the builder used
# passes just as happily when the constant changes.
assert COVERAGE_TOLERANCE == 0, COVERAGE_TOLERANCE
assert COVERAGE_BASELINE == "24h", COVERAGE_BASELINE

# 3. When a rule fires, and what it does when the data isn't there.
assert group["interval"] == EVAL_INTERVAL == "5m", group["interval"]
for uid, rule in rules.items():
    assert rule["for"] == PENDING_PERIOD == "10m", (uid, rule["for"])
    # A missing series means the collector didn't ship it — the heartbeat rule's
    # job to report once, rather than 47 per-state pages saying it worse.
    assert rule["noDataState"] == "OK", (uid, rule["noDataState"])
    # An execution error is NOT no-data: a datasource that has gone away has to
    # be visible as a broken rule rather than a healthy one.
    assert rule["execErrState"] == "Error", (uid, rule["execErrState"])
    assert rule["isPaused"] is False, uid

# 3b. The dead-man window is sized against the MEASURED sweep gap, never the
#     workflow's cron expression. GitHub runs scheduled workflows best-effort and
#     25 consecutive sweeps showed a median of 2.0h and a max of 3.6h, so the
#     PRD's literal "3 hours" sits BELOW the routine worst case and would page on
#     an ordinary long gap. Asserted against the measurement, not against the
#     window constant — importing the constant under test would let it shrink
#     back to 3h and stay green.
window = re.search(r"\[(\d+)([smh])\]", dead_expr)
assert window, dead_expr
hours = int(window.group(1)) * {"s": 1 / 3600, "m": 1 / 60, "h": 1}[window.group(2)]
assert hours >= 1.5 * OBSERVED_MAX_SWEEP_GAP_HOURS, (dead_expr, hours)
assert OBSERVED_MAX_SWEEP_GAP_HOURS >= 3.6, OBSERVED_MAX_SWEEP_GAP_HOURS

# 3c. noDataState OK is right for a sweep that did not happen and WRONG for a
#     repo that silently stopped reporting — and the two are indistinguishable
#     per-series. The heartbeat only covers the collector's own series, so
#     without this fourth rule a repo with zero commits on its data path (the
#     most stale a repo can be: fleet_poller returns None on a 409 "Git
#     Repository is empty", and metrics_shipper then emits no age series at all)
#     stays green forever while the other 46 report normally.
coverage_expr = rules[COVERAGE_UID]["data"][0]["model"]["expr"]
assert "fleet_repo_data_commit_age_hours" in coverage_expr, coverage_expr
#     The fleet is compared against ITSELF a day ago, never against a count of
#     what someone expected it to be. A hardcoded size goes stale; the collector's
#     heartbeat (the version this replaced) counts paused repos too, so a paused
#     repo that reports nothing would page — breaking the one rule the whole
#     design turns on.
assert f"[{COVERAGE_BASELINE}]" in coverage_expr and f"[{LOOKBACK_WINDOW}]" in coverage_expr, \
    coverage_expr
#     The heartbeat appears only as the `unless` guard, never as the expected
#     count: counting against it needs every polled repo to have a data-path
#     commit (an assumption, not a measurement) and pages on a paused repo.
assert "count(last_over_time(fleet_collector_heartbeat_repos" not in coverage_expr, coverage_expr
assert coverage_expr.count("fleet_collector_heartbeat_repos") == 1, coverage_expr
assert re.search(r"\b112\b|\b47\b|\b56\b", coverage_expr) is None, \
    ("the fleet size is hardcoded in the coverage rule", coverage_expr)
#     Repos, not series: `paused` is a label, so a jurisdiction going out of
#     session starts a SECOND series for the same repo and both stay resolvable
#     for a whole look-back. Counting series would read the legislative calendar
#     turning over as coverage appearing and then vanishing, in batches.
assert coverage_expr.count("count by (state, org)") == 2, coverage_expr
#     A count over no series at all is an EMPTY vector, not zero, and an empty
#     right-hand side makes the whole subtraction empty — which noDataState
#     resolves to OK. Without this floor the rule is silent in exactly its worst
#     case: every repo gone at once.
#
#     Asserted as a SHAPE, not as a bag of ingredients. Both operand order and
#     the floor's placement are load-bearing and neither shows up in a substring
#     check: swap the windows and the difference is always ≤ 0, so the rule can
#     never fire; move `or vector(0)` to the left operand and the case it exists
#     for is silent again. Both mutations keep every ingredient present.
metric = "fleet_repo_data_commit_age_hours"
counted = f"count(count by (state, org) (last_over_time({metric}[%s])))"
assert coverage_expr == (
    f"({counted % COVERAGE_BASELINE} - ({counted % LOOKBACK_WINDOW} or vector(0))) "
    f"unless absent_over_time(fleet_collector_heartbeat_repos[{LOOKBACK_WINDOW}])"
), coverage_expr
#     A dead collector empties the [6h] side at the same instant the heartbeat
#     rule fires; without the `unless` guard `or vector(0)` floors it and this
#     rule reports the whole fleet as having "stopped reporting" — two Slack
#     messages for one outage, and the louder one wrong about the cause.
assert "unless absent_over_time" in coverage_expr, coverage_expr

# 4. Triage is one click: every alert carries a link into the board, filtered to
#    the jurisdiction that alerted. Absolute, because a notification is read in
#    Slack or an inbox — the relative path the board's own row links use resolves
#    against slack.com there.
for uid, rule in rules.items():
    assert rule["labels"] == dict([ROUTE_LABEL]), (uid, rule["labels"])
    link = rule["annotations"]["dashboard"]
    assert link.startswith(f"$GRAFANA_DASHBOARD_URL/d/{DASHBOARD_UID}"), (uid, link)
    # Pinned range: `${__url_time_range}` is a dashboard macro with nothing to
    # expand it in an annotation, and "the last 24h from whenever you click"
    # shows a different window to every reader.
    assert "from=now-24h&to=now" in link, (uid, link)
    assert "${__url_time_range}" not in link, (uid, link)
for uid in (RUN_FAILED_UID, STALE_UID):
    link = rules[uid]["annotations"]["dashboard"]
    assert "var-state={{ urlquery $labels.state }}" in link, (uid, link)
    # Not var-org — a jurisdiction has two repos, and naming one hides the other.
    assert "var-org=" not in link, (uid, link)
    # The state has to be in the message too: "a run failed" without saying whose
    # is not something anyone can act on at 3am.
    assert "{{ $labels.state }}" in rules[uid]["annotations"]["summary"], uid
# The fleet-wide rules have no state label to interpolate, so a var-state there
# would render `var-state=` — a filter matching nothing, on the alerts that fire
# when everything else has gone quiet.
for uid in (HEARTBEAT_UID, COVERAGE_UID):
    link = rules[uid]["annotations"]["dashboard"]
    assert "$labels" not in link, (uid, link)
    assert "var-state" not in link, (uid, link)

# 5. Slack and email as two integrations on ONE contact point, so the PRD's
#    later GitHub-issue delivery is a third entry rather than a second route to
#    keep in step forever.
point = build_contact_point()
kinds = {r["type"]: r for r in point["receivers"]}
assert set(kinds) == {"slack", "email"}, sorted(kinds)
assert kinds["slack"]["settings"]["url"] == "$SLACK_WEBHOOK_URL", kinds["slack"]
assert kinds["email"]["settings"]["addresses"] == "$ALERT_EMAIL", kinds["email"]
for receiver in point["receivers"]:
    # A channel that only ever fills with red and never visibly clears is a
    # channel people mute.
    assert receiver["disableResolveMessage"] is False, receiver
# Nothing that could only have come from a real workspace or a real inbox.
assert "hooks.slack.com" not in repr(point), repr(point)
assert "@" not in repr(point), repr(point)

# 6. 47 jurisdictions share the same scrapers, so one upstream break trips the
#    run-failed rule for dozens at once. Grouped by the rule that is ONE message
#    listing every affected state; grouped by state it is forty messages in a
#    minute, which is how people learn to mute a channel.
policy = build_policy()
assert policy["group_by"] == ["alertname"], policy["group_by"]
assert policy["receiver"] == CONTACT_POINT, policy
assert (policy["group_wait"], policy["group_interval"], policy["repeat_interval"]) \
    == ("30s", "5m", "24h"), policy
# The ROOT of a dedicated stack's tree, shape checked exactly: no matchers (the
# root matches everything by construction, and Grafana silently ignores matchers
# placed on it) and no children (a stray alert should land in the channel as a
# visible surprise, not vanish down a default receiver nobody reads).
assert "object_matchers" not in policy and "matchers" not in policy, policy
assert "routes" not in policy, policy

# 7. The committed documents. The policy one IS a real Grafana `policies:`
#    document — the entire tree of a stack dedicated to the fleet monitor, in
#    the same file-provisioning format as the other two artifacts.
documents = render_documents()
assert set(documents) == {RULES_FILE, CONTACT_POINTS_FILE, POLICY_FILE}, sorted(documents)
policy_doc = yaml.safe_load(documents[POLICY_FILE])
assert [p["receiver"] for p in policy_doc["policies"]] == [CONTACT_POINT], policy_doc
assert yaml.safe_load(documents[RULES_FILE])["groups"][0]["folder"] == FOLDER, documents[RULES_FILE]
for name, text in documents.items():
    # Reasoning survives in the artifact people actually open, not only in the
    # builder they may never look at.
    assert text.startswith("#"), (name, text[:40])
# Deterministic, or the committed copy is not a meaningful diff.
assert render_documents() == documents

# 8. Placeholders: exactly four, resolved at provision time. A committed webhook
#    URL is a committed credential; a committed datasource uid belongs to one
#    stack and makes the file unimportable anywhere else.
found = set()
for text in documents.values():
    found |= placeholders(text)
assert found == {"GRAFANA_METRICS_DATASOURCE_UID", "GRAFANA_DASHBOARD_URL",
                 "SLACK_WEBHOOK_URL", "ALERT_EMAIL"}, sorted(found)
# ...and the resolver that actually runs in provisioning is the one asserted
# against — not a text-level helper the production path no longer calls, which is
# how a contract stays green while the code under it rots.
resolved = _resolve(
    {"url": "$SLACK_WEBHOOK_URL", "summary": "{{ $labels.state }}", "to": "$ALERT_EMAIL"},
    {"SLACK_WEBHOOK_URL": "https://hooks.example/x", "ALERT": "x", "ALERT_EMAIL": "right"},
    set(),
)
# Grafana's own templating is lower-case and survives untouched — expanding it
# would turn every alert message into a literal.
assert resolved["summary"] == "{{ $labels.state }}", resolved
# A prefix is not a partial match: $ALERT must not eat $ALERT_EMAIL.
assert resolved["to"] == "right", resolved
assert resolved["url"] == "https://hooks.example/x", resolved
# A placeholder nobody supplied is a hard stop, not an empty string: Grafana
# accepts a contact point with a blank webhook URL, then accepts alerts routed to
# it and drops them — a setup that looks provisioned and never reaches anyone.
# Asserted through _load, so the refusal is proven on the real file, not a stub.
try:
    _load(Path("alerting"), CONTACT_POINTS_FILE, {})
except UnresolvedPlaceholder as e:
    assert "SLACK_WEBHOOK_URL" in str(e), str(e)
else:
    raise AssertionError("an unresolved placeholder was substituted away silently")
# An empty string is not a supplied value. Grafana accepts a contact point whose
# webhook URL is empty, then accepts alerts routed to it and drops them — a setup
# that looks provisioned, reports healthy, and never reaches anyone. The CLI's
# credential gate refuses an empty env var; this is the same refusal one layer
# down, for any other caller of provision().
seen = set()
resolved_empty = _resolve({"url": "$SLACK_WEBHOOK_URL"}, {"SLACK_WEBHOOK_URL": ""}, seen)
assert seen == {"SLACK_WEBHOOK_URL"}, seen
assert resolved_empty["url"] == "$SLACK_WEBHOOK_URL", resolved_empty

# 8b. Positive, not a blacklist: every credential-bearing setting in the
#     committed contact point must STILL be a bare placeholder. The blacklist
#     this replaced (a handful of hosts and four TLDs) missed .gov, .io, any
#     upper-case address, and any non-Slack webhook — and advertising it as a
#     guard is how a weak check becomes a reason not to look.
committed = yaml.safe_load(Path("alerting", CONTACT_POINTS_FILE).read_text())
settings = [
    value
    for contact_point in committed["contactPoints"]
    for receiver in contact_point["receivers"]
    for value in receiver["settings"].values()
]
assert settings, committed
for value in settings:
    assert re.fullmatch(r"\$[A-Z][A-Z0-9_]*", str(value)), (
        "a committed contact-point setting is not a bare placeholder", value
    )

print(f"✓ alerting: {len(rules)} rules, paused filtered out, thresholds shared with the "
      "dashboard, dead-man sized on the measured sweep gap, no credentials committed")
EOF

# The committed alerting files must be exactly what the builder produces —
# otherwise the YAML people provision and the code reviewers read have diverged.
# stderr is kept rather than discarded: under `set -e` a crash in the builder
# would otherwise kill the whole render with no diagnostic at all.
alerts_tmp=$(mktemp -d)
alerts_err=$(mktemp)
if ! pipenv run python3 main.py alerts --out-dir "$alerts_tmp" 2>"$alerts_err"; then
  echo "✗ main.py alerts failed:"
  cat "$alerts_err"
  rm -rf "$alerts_tmp" "$alerts_err"
  exit 1
fi
if ! diff -ru alerting "$alerts_tmp"; then
  echo "✗ alerting/ is stale; regenerate it:"
  echo "    pipenv run python3 main.py alerts --out-dir alerting"
  rm -rf "$alerts_tmp" "$alerts_err"
  exit 1
fi
rm -rf "$alerts_tmp" "$alerts_err"
echo "✓ alerting: committed alerting/*.yaml matches the builder"

# Provisioning writes to a real stack, so like every other live path it must
# self-skip without credentials; the offline suite locks that skip. Explicitly
# unset rather than merely absent — a developer machine may export its own
# SLACK_WEBHOOK_URL, and at least one does.
alerts_skip=$(env -u GRAFANA_ALERTS_URL -u GRAFANA_ALERTS_KEY -u SLACK_WEBHOOK_URL \
  -u ALERT_EMAIL pipenv run python3 main.py provision-alerts 2>&1)
if ! echo "$alerts_skip" | grep -q "alert provisioning skipped"; then
  echo "✗ provision-alerts without credentials should skip cleanly; got:"
  echo "$alerts_skip"
  exit 1
fi
echo "✓ provision-alerts: skips cleanly when credentials are absent"

# Offline proof of provisioning itself: a fake Grafana answers every read and
# accepts every write, so the request shapes (verbs, bearer auth, the
# provenance header, placeholder resolution, the replaced policy tree) and the
# refusal paths are all tested without an account. Every scenario drives the CLI
# and passes --deadline-seconds 0, so the poll runs exactly once and the suite
# never waits on a real clock. The real run is credential-gated below.
pipenv run python3 - <<'EOF'
import datetime
import json
import shutil
import tempfile
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

from click.testing import CliRunner

import yaml

import main
from alerting import (CONTACT_POINT, COVERAGE_UID, HEARTBEAT_UID, PLACEHOLDER,
                      ROUTE_LABEL, RULES_FILE, RUN_FAILED_UID, STALE_UID)
from alerts_provision import CONFIRM_DEADLINE_SECONDS, _seconds

CREDS = {
    "GRAFANA_ALERTS_URL": "https://stack.grafana.net/",
    "GRAFANA_ALERTS_KEY": "tok",
    "SLACK_WEBHOOK_URL": "https://hooks.example/x",
    "ALERT_EMAIL": "alerts@example.org",
}
PROMETHEUS = {"uid": "prom-uid", "type": "prometheus", "name": "grafanacloud-govbot-prom"}
LOKI = {"uid": "loki-uid", "type": "loki", "name": "grafanacloud-govbot-logs"}
UIDS = [RUN_FAILED_UID, STALE_UID, HEARTBEAT_UID, COVERAGE_UID]
LATER = (
    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
).isoformat().replace("+00:00", "Z")


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


EARLIER = (
    datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
).isoformat().replace("+00:00", "Z")


def evaluated(health="ok", when=LATER, **extra):
    """The ruler API's view of rules this stack has actually run."""
    return {"data": {"groups": [{"rules": [
        {"uid": uid, "health": health, "lastEvaluation": when, **extra} for uid in UIDS
    ]}]}}


NEVER_EVALUATED = {"data": {"groups": []}}


UNSET = object()


def stack(datasources=(PROMETHEUS, LOKI), policies=UNSET, contact_points=None, rules=None,
          missing_policies=False, baseline_rules=NEVER_EVALUATED, folder=None, others=()):
    """A Grafana that answers reads and accepts every write.

    The FIRST ruler read is the pre-write baseline; every read after it is the
    confirmation poll. That ordering is the point of the check under test, so the
    fake has to reproduce it rather than serve one answer forever.
    """
    reads = []

    def respond(request):
        url = request.full_url
        if request.get_method() != "GET":
            return FakeResponse(b"{}")
        if url.endswith("/api/datasources"):
            return FakeResponse(json.dumps(list(datasources)).encode())
        if "/api/v1/provisioning/contact-points" in url:
            return FakeResponse(json.dumps(contact_points or []).encode())
        if url.endswith("/api/v1/provisioning/policies") and not missing_policies:
            # A fresh stack's untouched default — the exact receiver name
            # Grafana creates, which is the only foreign tree ever adopted.
            tree = {"receiver": "grafana-default-email"} if policies is UNSET else policies
            return FakeResponse(json.dumps(tree).encode())
        if "/api/folders/" in url:
            if folder is None:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return FakeResponse(json.dumps(folder).encode())
        if "/api/prometheus/grafana/api/v1/rules" in url:
            reads.append(url)
            if len(reads) == 1:
                return FakeResponse(json.dumps(baseline_rules).encode())
            answer = json.loads(json.dumps(rules or evaluated()))
            answer["data"]["groups"] = list(answer["data"]["groups"]) + list(others)
            return FakeResponse(json.dumps(answer).encode())
        # Folders, an unreadable policy tree, anything else: not there.
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    return respond


def run(env, respond, extra_args=("--deadline-seconds", "0")):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return respond(request)

    real, urllib.request.urlopen = urllib.request.urlopen, fake_urlopen
    try:
        result = CliRunner().invoke(main.cli, ["provision-alerts", *extra_args], env=env)
    finally:
        urllib.request.urlopen = real
    return result, calls


def written(calls, fragment, method=None):
    return [
        c for c in calls
        if c.data is not None and fragment in c.full_url
        and (method is None or c.get_method() == method)
    ]


# A skipped run must touch nothing at all, not merely exit 0.
# Unset AND empty: an unset CI secret renders as the empty string, not as an
# absent variable, so both have to reach the same clean skip.
for absent, blanked in [(k, v) for k in CREDS for v in (None, "")]:
    skipped, calls = run({**CREDS, absent: blanked}, stack())
    assert skipped.exit_code == 0, (absent, skipped.output)
    assert absent in skipped.output, (absent, skipped.output)
    assert not calls, (absent, "a skipped run still talked to the stack")

ok, ok_calls = run(CREDS, stack())
assert ok.exit_code == 0, ok.output + str(ok.exception)
for call in [c for c in ok_calls if c.data is not None]:
    assert call.get_header("Authorization") == "Bearer tok", call.full_url
    # Without this header Grafana marks everything it provisions read-only, and
    # the first maintainer who tries to silence a rule meets a greyed-out form.
    assert call.get_header("X-disable-provenance") == "true", call.full_url
    # Nothing ships with an unresolved placeholder — checked against the pattern
    # the module itself defines, not three literal prefixes: a fifth placeholder
    # the provisioner forgets to resolve has to fail this, not slip past it.
    left = PLACEHOLDER.findall(call.data.decode())
    assert not left, (call.full_url, left)

# The rules live in their own folder, so a maintainer can find — and remove —
# all of them by finding one thing. Without the POST the rule-group PUT to
# /api/v1/provisioning/folder/fleet-monitor/... 404s on a real stack.
folders = written(ok_calls, "/api/folders")
assert [json.loads(c.data) for c in folders] == [{"uid": "fleet-monitor", "title": "Fleet Monitor"}], \
    [c.full_url for c in folders]
# ...and a stack that already has it creates nothing.
existing_folder, folder_calls = run(CREDS, stack(folder={"uid": "fleet-monitor"}))
assert existing_folder.exit_code == 0, existing_folder.output
assert not written(folder_calls, "/api/folders"), [c.full_url for c in folder_calls]
assert "folder: present" in existing_folder.output, existing_folder.output

# The datasource uid is the one thing that cannot be committed, so it is
# discovered from the stack being provisioned.
group = json.loads(written(ok_calls, "rule-groups")[0].data)
assert [r["data"][0]["datasourceUid"] for r in group["rules"]] == ["prom-uid"] * len(UIDS), group
# The whole group in one idempotent PUT: separate creates would duplicate on a
# second run, and a rule dropped from the committed file would linger on the
# stack as an orphan nobody remembers creating.
assert len(written(ok_calls, "rule-groups")) == 1, [c.full_url for c in written(ok_calls, "rule-groups")]
assert written(ok_calls, "rule-groups")[0].get_method() == "PUT"
assert [r["uid"] for r in group["rules"]] == UIDS, group
# Seconds, not "5m" — the group API takes a number.
assert group["interval"] == 300, group["interval"]
# Grafana's provisioning API requires these per rule, not just on the group.
assert all(r["folderUID"] == "fleet-monitor" for r in group["rules"]), group["rules"]
assert all(r["ruleGroup"] == "fleet-monitor" for r in group["rules"]), group["rules"]

# The policy is written BEFORE the rules. Ordering, not taste: the policy PUT is
# the one that can still fail after every read has passed — Grafana 11 splits
# alert.rules:write from alert.notifications:write, so a token holding only the
# first gets through all the checks here and then 403s. Rules-first leaves them
# live and delivering to whatever receiver was there, reproduced on every retry.
# Policy-first fails with a tree routing alerts that do not exist yet, which is
# inert.
order = [c.full_url for c in ok_calls if c.data is not None]
assert next(i for i, u in enumerate(order) if "policies" in u) \
    < next(i for i, u in enumerate(order) if "rule-groups" in u), order
# Grafana's own templating survives substitution untouched.
assert "{{ $labels.state }}" in json.dumps(group), group

# The deep link resolves to a real absolute URL on the stack being provisioned —
# asserted on the RESOLVED value, not just on the placeholder's presence. A link
# that resolves to the empty string, to a trailing double slash, or to some other
# host is still a link, and still passes an unresolved-placeholder scan.
links = {r["annotations"]["dashboard"] for r in group["rules"]}
assert all(link.startswith("https://stack.grafana.net/d/fleet-monitor-overview?") for link in links), \
    links
# GRAFANA_ALERTS_URL carries a trailing slash in these credentials; the join must
# not double it.
assert not any("net//d/" in link for link in links), links
# ...and an explicit dashboard URL overrides the stack URL, for a UI served
# elsewhere.
elsewhere, calls = run({**CREDS, "GRAFANA_DASHBOARD_URL": "https://ui.example/"}, stack())
overridden = json.loads(written(calls, "rule-groups")[0].data)["rules"][0]
assert overridden["annotations"]["dashboard"].startswith("https://ui.example/d/"), overridden
# An unset CI secret renders as the EMPTY STRING, not as an absent variable, and
# an empty base would make every alert link relative — resolving against
# slack.com wherever the notification is read.
blank, calls = run({**CREDS, "GRAFANA_DASHBOARD_URL": ""}, stack())
fallback = json.loads(written(calls, "rule-groups")[0].data)["rules"][0]
assert fallback["annotations"]["dashboard"].startswith("https://stack.grafana.net/d/"), fallback

# What gets applied is the file on disk, not a fresh render of the builder —
# which is what the README promises and what makes reviewing the committed YAML
# worth anything. Proven with a sentinel only present in the file.
with tempfile.TemporaryDirectory() as tmp:
    for name in Path("alerting").iterdir():
        shutil.copy(name, tmp)
    doctored = Path(tmp, RULES_FILE)
    doctored.write_text(doctored.read_text().replace('paused="false"', 'paused="SENTINEL"'))
    sentinel, calls = run(CREDS, stack(), ("--alerting-dir", tmp, "--deadline-seconds", "0"))
    assert sentinel.exit_code == 0, sentinel.output + str(sentinel.exception)
    applied = json.loads(written(calls, "rule-groups")[0].data)
    exprs = [q["model"].get("expr", "") for r in applied["rules"] for q in r["data"]]
    assert any('paused="SENTINEL"' in expr for expr in exprs), \
        ("provision-alerts re-rendered the rules instead of applying the committed file", exprs)

# The stdout form the README documents, not only --out-dir.
printed = CliRunner().invoke(main.cli, ["alerts"])
assert printed.exit_code == 0, printed.output + str(printed.exception)
for name in (RULES_FILE, "fleet-contact-points.yaml", "fleet-notification-policy.yaml"):
    assert f"# ===== {name} =====" in printed.output, name
assert len([d for d in yaml.safe_load_all(
    "\n".join(l for l in printed.output.splitlines() if not l.startswith("# ====="))
)]) >= 1, printed.output

# The committed directory belongs to the module, not the caller's cwd. Click
# validates a path default BEFORE the command body, so a cwd-relative
# `exists=True` default made provision-alerts exit 2 with a path error from
# anywhere else instead of the documented credential-free skip.
import os
here = os.getcwd()
with tempfile.TemporaryDirectory() as elsewhere:
    os.chdir(elsewhere)
    try:
        away = CliRunner().invoke(
            main.cli, ["provision-alerts"], env={k: None for k in CREDS}
        )
    finally:
        os.chdir(here)
assert away.exit_code == 0, away.output + str(away.exception)
assert "alert provisioning skipped" in away.output, away.output

# ...and with credentials, from that same foreign cwd, it still applies the
# module's own committed files rather than looking for `alerting/` beside the
# caller. The skip above alone proves nothing: it returns before the default is
# ever dereferenced.
with tempfile.TemporaryDirectory() as elsewhere:
    os.chdir(elsewhere)
    try:
        far, far_calls = run(CREDS, stack())
    finally:
        os.chdir(here)
assert far.exit_code == 0, far.output + str(far.exception)
applied_far = json.loads(written(far_calls, "rule-groups")[0].data)
assert [r["uid"] for r in applied_far["rules"]] == UIDS, applied_far
assert 'paused="false"' in applied_far["rules"][0]["data"][0]["model"]["expr"], applied_far

# Every group in the committed file, not just the first — a second group would
# otherwise render, pass the drift check, and exist in git and nowhere else while
# provisioning reported success.
with tempfile.TemporaryDirectory() as tmp:
    for name in Path("alerting").iterdir():
        shutil.copy(name, tmp)
    doc = yaml.safe_load(Path(tmp, RULES_FILE).read_text())
    second = json.loads(json.dumps(doc["groups"][0]))
    second["name"] = "fleet-monitor-slow"
    second["rules"] = second["rules"][:1]
    second["rules"][0]["uid"] = "fleet-second-group"
    doc["groups"].append(second)
    Path(tmp, RULES_FILE).write_text(yaml.safe_dump(doc, sort_keys=False))
    multi, calls = run(CREDS, stack(), ("--alerting-dir", tmp, "--deadline-seconds", "0"))
    groups_put = [c.full_url.rsplit("/", 1)[-1] for c in written(calls, "rule-groups")]
    assert groups_put == ["fleet-monitor", "fleet-monitor-slow"], groups_put

# A credential carrying a YAML metacharacter must still provision. Placeholders
# are resolved into the PARSED document precisely so this cannot become a parse
# error — whose message would quote a window of the offending line, i.e. print
# the resolved Slack webhook URL to stderr and into the CI log that keeps it.
awkward = {**CREDS, "SLACK_WEBHOOK_URL": "https://hooks.example/x: {y} #z",
           "ALERT_EMAIL": "Ops: oncall@example.org"}
metachar, calls = run(awkward, stack())
assert metachar.exit_code == 0, metachar.output + str(metachar.exception)
sent = [json.loads(c.data) for c in written(calls, "contact-points")]
assert any(b["settings"].get("url") == awkward["SLACK_WEBHOOK_URL"] for b in sent), sent
assert any(b["settings"].get("addresses") == awkward["ALERT_EMAIL"] for b in sent), sent

# The base URL carries a bearer token and, in the contact-point body, the Slack
# webhook URL. Four ways that goes wrong, all refused before a single request:
for bad, why in (
    # Plain http puts the token and the webhook on the wire in the clear.
    ("http://stack.grafana.net", "https"),
    ("stack.grafana.net", "https"),
    # A file:// base with a loopback host would otherwise slip through the
    # loopback exemption and make urlopen read local files as API responses.
    ("file://localhost/etc/passwd", "https"),
    # Credentials in the URL reach the CI log: every RequestFailed message
    # embeds the URL it failed on.
    ("https://svc:GLSA_secret@stack.grafana.net", "credentials in the URL"),
    # A query swallows the API path: https://stack/?x + /api/folders.
    ("https://stack.grafana.net/?x", "bare origin"),
    # A trailing "?" parses as an EMPTY query, so the guard has to look at the
    # raw string too — otherwise it survives into every request URL.
    ("https://stack.grafana.net?", "bare origin"),
    # A truncated CI secret: scheme fine, everything else empty.
    ("https://", "no host"),
    # A path prefix 404s every GET, which find() reads as "not there yet" — a
    # stack that looks empty and gets overwritten.
    ("https://stack.grafana.net/grafana", "bare origin"),
):
    refused, calls = run({**CREDS, "GRAFANA_ALERTS_URL": bad}, stack())
    assert refused.exit_code != 0, (bad, refused.output)
    assert why in refused.output, (bad, refused.output)
    assert not calls, (bad, "sent a request before rejecting the base URL")
    assert "GLSA_secret" not in refused.output, refused.output
# The loopback exemption assumes nothing leaves the machine, and urllib has no
# implicit localhost proxy bypass — with http_proxy set and no_proxy not covering
# it, the token and the webhook go to the proxy host in cleartext.
proxied, calls = run({**CREDS, "GRAFANA_ALERTS_URL": "http://localhost:3000",
                      "http_proxy": "http://proxy.example:8080", "no_proxy": None}, stack())
assert proxied.exit_code != 0 and "http_proxy" in proxied.output, proxied.output
assert not calls, "sent a request through a proxy before refusing"

# A plain-http Slack webhook is refused: Grafana would re-POST the hook path
# itself in cleartext on every alert, from its own egress.
cleartext_hook, calls = run({**CREDS, "SLACK_WEBHOOK_URL": "http://hooks.example/x"}, stack())
assert cleartext_hook.exit_code != 0 and "SLACK_WEBHOOK_URL" in cleartext_hook.output, \
    cleartext_hook.output
assert "hooks.example" not in cleartext_hook.output, cleartext_hook.output

# An explicit dashboard URL gets the same treatment — it is never contacted, so
# a wrong value provisions cleanly and misdirects on-call staff indefinitely.
bad_link, calls = run({**CREDS, "GRAFANA_DASHBOARD_URL": "http://ui.example"}, stack())
assert bad_link.exit_code != 0 and "https" in bad_link.output, bad_link.output
# ...and a local test stack over plain http is still allowed.
from alerts_provision import check_stack_url
assert check_stack_url("http://localhost:3000/", "X") == "http://localhost:3000"

# The document's own shape is checked before the first write. Checking only the
# top-level key is not enough: the writers reach rule["uid"] and receiver["type"],
# and a bare KeyError from there escapes the CLI's handler and prints a traceback
# over a stack that already has its folder, contact point, and route.
for filename, mangle in (
    (RULES_FILE, lambda d: d.update(groups=[{"name": "g", "rules": [{"title": "t"}]}])),
    (RULES_FILE, lambda d: d.update(groups="oops")),
    (RULES_FILE, lambda d: d.update(groups=[{"name": "g", "rules": [{"uid": "u"}]}])),
    ("fleet-contact-points.yaml",
     lambda d: d.update(contactPoints=[{"name": CONTACT_POINT, "receivers": [{"type": "slack"}]}])),
    ("fleet-contact-points.yaml",
     lambda d: d.update(contactPoints=[{"name": "renamed", "receivers": []}])),
    ("fleet-notification-policy.yaml",
     lambda d: d.update(policies=[{"receiver": "somewhere-else"}])),
    # The root matches every alert by construction and Grafana silently ignores
    # matchers placed on it — a file carrying them promises a filter that does
    # not exist, and provisioning it would report success.
    ("fleet-notification-policy.yaml",
     lambda d: d["policies"][0].update(object_matchers=[["service", "=", "fleet-monitor"]])),
    # One tree per stack: a second entry, or a child route, means somebody is
    # trying to route a stack that is supposed to be dedicated — a design
    # change, not a provisioning input.
    ("fleet-notification-policy.yaml",
     lambda d: d["policies"].append({"receiver": CONTACT_POINT})),
    ("fleet-notification-policy.yaml",
     lambda d: d["policies"][0].update(routes=[{"receiver": "their-pager"}])),
):
    with tempfile.TemporaryDirectory() as tmp:
        for f in Path("alerting").iterdir():
            shutil.copy(f, tmp)
        doc = yaml.safe_load(Path(tmp, filename).read_text())
        mangle(doc)
        Path(tmp, filename).write_text(yaml.safe_dump(doc, sort_keys=False))
        broken_doc, broken_calls = run(
            CREDS, stack(), ("--alerting-dir", tmp, "--deadline-seconds", "0")
        )
        assert broken_doc.exit_code != 0, (filename, broken_doc.output)
        assert filename in broken_doc.output, (filename, broken_doc.output)
        assert not isinstance(broken_doc.exception, KeyError), broken_doc.exception
        assert not [c for c in broken_calls if c.data is not None], \
            (filename, "wrote to the stack before rejecting a malformed document")

# A uid that would escape its path segment never reaches a URL: `..` and `/` are
# refused outright, before quoting.
with tempfile.TemporaryDirectory() as tmp:
    for f in Path("alerting").iterdir():
        shutil.copy(f, tmp)
    doc = yaml.safe_load(Path(tmp, "fleet-contact-points.yaml").read_text())
    doc["contactPoints"][0]["receivers"][0]["uid"] = "../../../../api/folders/theirs"
    Path(tmp, "fleet-contact-points.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    # Present on the stack, so the write takes the update path — where the uid
    # becomes a URL segment rather than living only in the body.
    traversal, traversal_calls = run(
        CREDS,
        stack(contact_points=[{"uid": "../../../../api/folders/theirs", "name": CONTACT_POINT}]),
        ("--alerting-dir", tmp, "--deadline-seconds", "0"),
    )
    assert traversal.exit_code != 0, traversal.output
    assert "path separator" in traversal.output, traversal.output
    assert not any("folders/theirs" in c.full_url for c in traversal_calls), \
        [c.full_url for c in traversal_calls]

# ...including a bare `..`, which survives quoting untouched and which Grafana's
# router would normalise into a write on the collection itself.
with tempfile.TemporaryDirectory() as tmp:
    for f in Path("alerting").iterdir():
        shutil.copy(f, tmp)
    doc = yaml.safe_load(Path(tmp, "fleet-contact-points.yaml").read_text())
    doc["contactPoints"][0]["receivers"][0]["uid"] = ".."
    Path(tmp, "fleet-contact-points.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    dotdot, _ = run(CREDS, stack(contact_points=[{"uid": "..", "name": CONTACT_POINT}]),
                    ("--alerting-dir", tmp, "--deadline-seconds", "0"))
    assert dotdot.exit_code != 0 and "path separator" in dotdot.output, dotdot.output

# A receiver the API returns without a uid must not become a DELETE to `.../None`
# — nor make the removal sort raise on a mix of None and real uids.
uidless = [
    {"uid": "fleet-monitor-slack", "name": CONTACT_POINT, "type": "slack"},
    {"name": CONTACT_POINT, "type": "webhook"},
]
odd, odd_calls = run(CREDS, stack(contact_points=uidless))
assert odd.exit_code == 0, odd.output + str(odd.exception)
assert not [c for c in odd_calls if c.get_method() == "DELETE" and c.full_url.endswith("None")], \
    [c.full_url for c in odd_calls if c.get_method() == "DELETE"]

# An explicit uid wins, for a stack with more than one Prometheus.
pinned, pinned_calls = run({**CREDS, "GRAFANA_METRICS_DATASOURCE_UID": "chosen"}, stack())
assert json.loads(written(pinned_calls, "rule-groups")[0].data)["rules"][0]["data"][0]["datasourceUid"] \
    == "chosen"
assert not any(c.full_url.endswith("/api/datasources") for c in pinned_calls), \
    "asked the stack for a datasource it was already told about"

# Two Prometheus datasources and no instruction is a stop, not a coin flip: the
# wrong one provisions rules that evaluate against nothing forever while
# reporting perfect health.
usage = {"uid": "other", "type": "prometheus", "name": "grafanacloud-usage"}
confused, _ = run(CREDS, stack(datasources=(PROMETHEUS, LOKI, usage)))
assert confused.exit_code != 0 and "grafanacloud-usage" in confused.output, confused.output
assert "GRAFANA_METRICS_DATASOURCE_UID" in confused.output, confused.output
none_at_all, _ = run(CREDS, stack(datasources=(LOKI,)))
assert none_at_all.exit_code != 0 and "no Prometheus datasource" in none_at_all.output

# Integrations are created once and updated in place after that, keyed by their
# stable uids — never a second copy of the same Slack webhook.
points = written(ok_calls, "contact-points")
assert [c.get_method() for c in points] == ["POST", "POST"], [c.get_method() for c in points]
bodies = [json.loads(c.data) for c in points]
assert {b["type"] for b in bodies} == {"slack", "email"}, bodies
assert any(b["settings"].get("url") == CREDS["SLACK_WEBHOOK_URL"] for b in bodies), bodies
assert any(b["settings"].get("addresses") == CREDS["ALERT_EMAIL"] for b in bodies), bodies
existing = [
    {"uid": "fleet-monitor-slack", "name": CONTACT_POINT, "type": "slack"},
    {"uid": "fleet-monitor-email", "name": CONTACT_POINT, "type": "email"},
]
again, again_calls = run(CREDS, stack(contact_points=existing))
assert [c.get_method() for c in written(again_calls, "contact-points")] == ["PUT", "PUT"], again.output

# An integration dropped from the committed file has to disappear from the stack
# too, or removing the email receiver leaves it emailing the old address forever
# with nothing left in the repo to explain why. Another contact point's
# receivers are none of our business and must survive.
stale = existing + [
    {"uid": "fleet-monitor-webhook", "name": CONTACT_POINT, "type": "webhook"},
    {"uid": "someone-elses", "name": "their-oncall", "type": "slack"},
]
stale = stale + [
    {"uid": "abc123xyz", "name": CONTACT_POINT, "type": "pagerduty"},
    # Another contact point's receiver, carrying a uid that looks like ours and
    # absent from our document — so only the NAME filter keeps it alive. The uid
    # prefix would happily prune it, and deleting somebody else's delivery is
    # the worst thing this command could do quietly.
    {"uid": "fleet-monitor-pager", "name": "their-oncall", "type": "pagerduty"},
]
pruned, pruned_calls = run(CREDS, stack(contact_points=stale))
assert pruned.exit_code == 0, pruned.output
deletes = [c for c in pruned_calls if c.get_method() == "DELETE"]
assert [c.full_url.rsplit("/", 1)[-1] for c in deletes] == ["fleet-monitor-webhook"], \
    [c.full_url for c in deletes]
assert "webhook removed" in pruned.output, pruned.output
# ...but an integration this module did not create is KEPT. X-Disable-Provenance
# exists so a maintainer can add one through the UI; deleting it on the next run
# would make this command undo the editing that header is for.
assert "pagerduty kept" in pruned.output, pruned.output
assert not any("their-oncall" in str(c.full_url) for c in pruned_calls
               if c.get_method() == "DELETE"), [c.full_url for c in deletes]
assert len(deletes) == 1, [c.full_url for c in deletes]

# The resolved webhook URL and address must never reach the terminal or an
# exception message — the module's stated primary threat. Nothing leaks today;
# this is what keeps a debug echo of a request body from ever passing.
for result in (ok, again, pruned, confused, none_at_all, blank):
    for secret in (CREDS["SLACK_WEBHOOK_URL"], CREDS["ALERT_EMAIL"]):
        assert secret not in result.output, (secret, result.output)
        assert secret not in str(result.exception or ""), secret

print("✓ provision-alerts: applies the committed file, one idempotent rule-group PUT, "
      "integrations created, updated, and pruned in place; no credential reaches the output")

# The notification policy is REPLACED WHOLE, never merged. The stack is
# dedicated to the fleet monitor, so the committed tree is the entire root — and
# the PUT only ever lands on a tree the module recognises: its own, or a fresh
# stack's untouched default. (The fake serves that default.)
fresh, fresh_calls = run(CREDS, stack())
assert fresh.exit_code == 0, fresh.output + str(fresh.exception)
tree = json.loads(written(fresh_calls, "policies")[0].data)
assert tree["receiver"] == CONTACT_POINT, tree
assert tree["group_by"] == ["alertname"], tree
assert (tree["group_wait"], tree["group_interval"], tree["repeat_interval"]) \
    == ("30s", "5m", "24h"), tree
# The committed shape, exactly: no matchers, no children, and no orgId leaking
# out of the file-provisioning wrapper into the API body.
assert "object_matchers" not in tree and "matchers" not in tree, tree
assert "routes" not in tree and "orgId" not in tree, tree
assert "adopted" in fresh.output, fresh.output

# The contact point is written BEFORE the policy: Grafana refuses a root
# receiver that does not exist, so on a fresh stack the reverse order 400s.
sequence = [c.full_url for c in fresh_calls if c.data is not None]
assert next(i for i, u in enumerate(sequence) if "contact-points" in u) \
    < next(i for i, u in enumerate(sequence) if "policies" in u), sequence

# Re-running over our own unchanged tree is idempotent and quiet about it...
rerun, rerun_calls = run(CREDS, stack(policies=json.loads(json.dumps(tree))))
assert rerun.exit_code == 0, rerun.output
assert "replaced" in rerun.output and "resetting" not in rerun.output, rerun.output
assert json.loads(written(rerun_calls, "policies")[0].data) == tree, rerun.output

# ...and a UI edit — the editing X-Disable-Provenance exists to allow — is
# overwritten and NAMED, so the operator learns the lasting place for a change
# is alerting.py, not the browser.
edited = {**tree, "group_wait": "5m",
          "routes": [{"receiver": CONTACT_POINT,
                      "object_matchers": [["severity", "=", "critical"]]}]}
drifted, drifted_calls = run(CREDS, stack(policies=edited))
assert drifted.exit_code == 0, drifted.output
assert "resetting" in drifted.output, drifted.output
assert "group_wait" in drifted.output and "routes" in drifted.output, drifted.output
# What lands is the committed tree, exactly — the drift is gone, not merged.
assert json.loads(written(drifted_calls, "policies")[0].data) == tree, drifted.output

# A tree this module does not recognise is a hard stop BEFORE any write — never
# a merge target. The PUT swaps the whole root, so "replace" against somebody
# else's tree would destroy routing there is no local copy of. The
# dedicated-stack assumption is checked on every run, not assumed.
for foreign in (
    # The default receiver WITH routes is not a fresh stack: somebody routed it.
    {"receiver": "grafana-default-email",
     "routes": [{"receiver": "their-oncall", "object_matchers": [["team", "=", "data"]]}]},
    # A root receiver that is neither ours nor the untouched default.
    {"receiver": "their-default"},
    {"receiver": "their-default", "routes": [{"receiver": "their-oncall"}]},
):
    occupied, occupied_calls = run(CREDS, stack(policies=foreign))
    assert occupied.exit_code != 0, (foreign, occupied.output)
    assert "not this module's to replace" in occupied.output, occupied.output
    assert not [c for c in occupied_calls if c.data is not None], \
        (foreign, [c.full_url for c in occupied_calls if c.data is not None])
# The refusal names what it found — the operator decides from the message, not
# from a second visit to the API.
assert "their-default" in occupied.output, occupied.output
assert "their-oncall" in occupied.output, occupied.output

# A policy tree that cannot be READ is a hard stop, not an empty tree. A 404 here
# means the token lacks notification-policy read scope, or the base URL carries a
# path prefix — cases where writes may still land. Treating it as empty would PUT
# the fleet's own receiver over a root nobody ever read, sending every unmatched
# alert on that stack to this Slack webhook with no copy of what was destroyed.
blind, blind_calls = run(CREDS, stack(missing_policies=True))
assert blind.exit_code != 0, blind.output
assert "notification policy" in blind.output, blind.output
assert not written(blind_calls, "policies"), "wrote a policy tree it could not read first"
# ...and it refuses BEFORE writing any rules. A refusal after they land leaves
# four enabled rules on the stack with no route matching them, so every fleet
# alert falls through to the stack owner's own receiver — and each retry
# reproduces the same half-applied state.
# No write of any kind, rather than three named endpoints — the folder POST is
# a write too, and enumerating endpoints lets a new one slip in ahead of the read.
assert not [c for c in blind_calls if c.data is not None], \
    [c.full_url for c in blind_calls if c.data is not None]

# A tree that reads back with children but no root receiver is not an empty
# tree — it could be a proxy's JSON error body, or a build that omits the field.
# Synthesising a root over it destroys those children with no local copy.
# The rule is POSITIVE: recognisable as a policy tree, or we do not touch it.
# Refusing only "children but no receiver" let every OTHER unrecognised 200 body
# through as "genuinely empty" — a proxy's error JSON, a maintenance page, a
# build that renamed the field — and the fleet's own receiver was then PUT over a
# root nobody had read. Every real Grafana ships a default root receiver, so
# "neither key" is far likelier to be a body we don't understand.
for unrecognised in (
    {"routes": [{"receiver": "their-oncall"}]},
    {"status": "error", "message": "upstream unavailable"},
    {"group_by": ["alertname"]},
    [],
    # No adoption path at all: every Grafana ships a default root receiver, so an
    # empty body is far likelier to be a proxy or a gateway stub than a stack
    # without one — and adopting it makes the fleet's webhook that stack's
    # catch-all for every alert it already runs.
    {},
):
    headless, headless_calls = run(CREDS, stack(policies=unrecognised))
    assert headless.exit_code != 0, (unrecognised, headless.output)
    assert "no root receiver" in headless.output, headless.output
    # ...and it refuses before writing anything at all, same as the 404 path.
    assert not [c for c in headless_calls if c.data is not None], \
        (unrecognised, [c.full_url for c in headless_calls if c.data is not None])


print("✓ provision-alerts: whole policy tree owned — a fresh default adopted, our own tree "
      "replaced with UI drift named, and any other tree refused before a single write")

# Storing a rule is not the same as being able to run it. Grafana accepts a rule
# whose datasource uid points at nothing, serves it back intact, and only reports
# the failure once evaluation runs — so a check that stops at the 200 is a check
# that passes while nothing works.
broken = evaluated(health="error", lastError="datasource not found")
failed, _ = run(CREDS, stack(rules=broken))
assert failed.exit_code != 0, failed.output
assert UIDS[0] in failed.output and "datasource not found" in failed.output, failed.output

# ...and health alone is not that evidence. A rule the stack has merely STORED
# reports health "unknown" — older builds default it to "ok" — with a zeroed
# lastEvaluation, seconds after the PUT and long before the group's first tick.
# This is the case that made the original check useless: it passed instantly on
# rules pointing at a datasource that did not exist.
for stored in (
    evaluated(health="unknown", when=LATER),
    evaluated(health="ok", when="0001-01-01T00:00:00Z"),
    evaluated(health="ok", when=None),
):
    unevaluated, _ = run(CREDS, stack(rules=stored))
    assert unevaluated.exit_code != 0, (stored["data"]["groups"][0]["rules"][0], unevaluated.output)
    assert f"0 of {len(UIDS)} rules had evaluated" in unevaluated.output, unevaluated.output

# The baseline is the stack's OWN last-evaluation time, read before the write,
# and the confirmation must be strictly newer than it. Comparing against this
# host's clock instead needs a skew tolerance, and any tolerance wide enough for
# a laptop a few minutes fast is also wide enough to accept the evaluation that
# ran just BEFORE the write — the previous rule definitions, which is the exact
# false pass this check exists to prevent.
unchanged, _ = run(CREDS, stack(baseline_rules=evaluated(when=LATER), rules=evaluated(when=LATER)))
assert unchanged.exit_code != 0, unchanged.output
assert f"0 of {len(UIDS)} rules had evaluated" in unchanged.output, unchanged.output
# ...and one tick later, the same stack passes.
ticked, _ = run(CREDS, stack(baseline_rules=evaluated(when=EARLIER), rules=evaluated(when=LATER)))
assert ticked.exit_code == 0, ticked.output + str(ticked.exception)

# The guard the other way round: a `health: error` left over from the previous
# configuration must not fail the run that corrected it. Its stamp is the
# baseline's, so it is not evidence about the rules this run just wrote.
stale_error = evaluated(health="error", when=EARLIER, lastError="datasource not found")
corrected, _ = run(CREDS, stack(baseline_rules=stale_error, rules=stale_error))
assert "provisioned, but the stack cannot evaluate" not in corrected.output, corrected.output
# ...but the same error re-recorded AFTER the write is real, and fails.
still_broken, _ = run(CREDS, stack(
    baseline_rules=stale_error,
    rules=evaluated(health="error", when=LATER, lastError="datasource not found"),
))
assert still_broken.exit_code != 0, still_broken.output
assert "datasource not found" in still_broken.output, still_broken.output

from alerting import build_rule_group

named = [
    {"name": rule["title"], "health": "ok", "lastEvaluation": LATER}
    for rule in build_rule_group()["rules"]
]

# A rule the pre-write read did not LIST is not the same as one it listed as
# never evaluated. The ruler API transiently answers with no groups while the
# scheduler reloads, and reading that as "never evaluated" would let a stamp left
# over from the previous definitions count as proof of this write.
# The reference for that case is the STACK's own clock — its freshest evaluation
# anywhere — not this host's. A host-clock comparison needs a skew tolerance, and
# NOT_LISTED is the normal state on a first-ever run, so that fallback would be
# the common path. Here an unrelated rule on the stack evaluated an hour ahead of
# this host, and ours are stamped half an hour ahead: newer than the host clock,
# older than the stack's, so only a stack-clock comparison refuses them.
MID = (
    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
).isoformat().replace("+00:00", "Z")
# Two pre-write stamps of clearly different ages, and ours falls between them:
# the reference has to be the FRESHEST, not just "some stamp the stack had".
OLDER = (
    datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
).isoformat().replace("+00:00", "Z")
not_listed, _ = run(CREDS, stack(
    baseline_rules={"data": {"groups": [{"file": "Theirs", "rules": [
        {"uid": "slow", "health": "ok", "lastEvaluation": OLDER},
        {"uid": "unrelated", "health": "ok", "lastEvaluation": LATER}]}]}},
    rules=evaluated(when=MID),
))
assert not_listed.exit_code != 0, not_listed.output
assert f"0 of {len(UIDS)} rules had evaluated" in not_listed.output, not_listed.output

# Partial is not success: the failure message reports the ratio, so the boundary
# between "some" and "all" has to be exercised.
half = {"data": {"groups": [{"file": "Fleet Monitor", "rules": [
    {"uid": uid, "health": "ok", "lastEvaluation": LATER if i < 2 else "0001-01-01T00:00:00Z"}
    for i, uid in enumerate(UIDS)
]}]}}
partial, _ = run(CREDS, stack(rules=half))
assert partial.exit_code != 0, partial.output
assert f"2 of {len(UIDS)} rules had evaluated" in partial.output, partial.output

# Two rules sharing a title are not an identity — last-wins would silently
# confirm off whichever came second.
twins = [dict(r, uid=None) for r in named] + [
    {"name": named[0]["name"], "health": "ok", "lastEvaluation": LATER}
]
ambiguous_titles = {"data": {"groups": [{"file": "Fleet Monitor", "rules": [
    {k: v for k, v in r.items() if v is not None} for r in twins
]}]}}
ambiguous_run, _ = run(CREDS, stack(rules=ambiguous_titles))
assert ambiguous_run.exit_code != 0, ambiguous_run.output
assert "never appeared" in ambiguous_run.output, ambiguous_run.output

# A rule the stack never lists at all is named in the failure.
absent, _ = run(CREDS, stack(rules={"data": {"groups": []}}))
assert absent.exit_code != 0 and "never appeared" in absent.output, absent.output
assert UIDS[0] in absent.output, absent.output

# A stack whose ruler response omits the per-rule uid is identified by title
# instead — the `__alert_rule_uid__` fallback this replaced looked in rule-level
# labels, where Grafana never puts it (it is an alert *instance* label), so it
# could never have rescued anything.

# Each namespace shape a Grafana build might serve has to carry the scoping on
# its own, or one arm is dead code the day the others change.
for namespace in ({"file": "Fleet Monitor"}, {"file": "fleet-monitor"},
                  {"folderUid": "fleet-monitor"}):
    by_title = {"data": {"groups": [{**namespace, "rules": named}]}}
    titled, _ = run(CREDS, stack(rules=by_title))
    assert titled.exit_code == 0, (namespace, titled.output + str(titled.exception))

# ...but only inside OUR folder. A maintainer-authored rule titled "Fleet data
# stale" elsewhere on the stack — a plausible name for someone watching the same
# fleet — must not stand in for one of ours the stack never scheduled.
# `file` is the namespace field the Prometheus-compat API actually returns; a
# group NAME of "Fleet Monitor" must not count, since ours is named
# "fleet-monitor" and that arm could only ever match somebody else's group.
elsewhere_titled = {"data": {"groups": [
    {"file": "Their Dashboards", "name": "Fleet Monitor", "rules": named}
]}}
foreign, _ = run(CREDS, stack(rules=elsewhere_titled))
assert foreign.exit_code != 0, foreign.output
assert "never appeared" in foreign.output, foreign.output

# The default deadline has to outlast a freshly written group's first tick, or
# every healthy provisioning run times out.
assert CONFIRM_DEADLINE_SECONDS > _seconds("5m"), CONFIRM_DEADLINE_SECONDS

# An evaluation interval that cannot be parsed names itself, rather than dying of
# a KeyError or a TypeError from mid-parse — this runs after the folder and the
# contact points are already written, so the message is all a maintainer has.
assert _seconds(60) == 60 and _seconds("90s") == 90 and _seconds("2h") == 7200
for bad in ("300", "1h30m", "", "5 m", None):
    try:
        _seconds(bad)
    except RuntimeError as e:
        assert repr(bad) in str(e), (bad, str(e))
    else:
        raise AssertionError(f"_seconds({bad!r}) silently accepted a value it cannot read")

print("✓ provision-alerts: waits for an evaluation stamped after its own write — a stored-only "
      "rule, a stale pass, and a stale failure are all refused")
EOF

# Same bargain as live-check and check-dashboard: the real run writes rules, a
# contact point, and the notification policy into a real stack — and the next
# evaluation can deliver to a real Slack channel — so a bare render never does it
# even on a machine that happens to have the credentials set. Opting in makes the
# render the automated provisioning check.
#
# Idempotent is not side-effect-free, which is why this is opt-IN despite
# converging on exactly what is committed.
if [ "${FLEET_MONITOR_ALERT_CHECK:-}" = "1" ]; then
  pipenv run python3 main.py provision-alerts
else
  echo "· provision-alerts (real provisioning) not run; opt in with FLEET_MONITOR_ALERT_CHECK=1"
fi

echo "✓ Snapshot generation complete. Output in $output_dir"
