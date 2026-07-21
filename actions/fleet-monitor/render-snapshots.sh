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

# Smoke: the real pipeline-manager config must parse and be non-empty.
# Not snapshotted — the real config churns; this only locks "it still works".
real_count=$(pipenv run python3 main.py list-fleet --config-dir ../pipeline-manager | wc -l | tr -d ' ')
if [ "$real_count" -lt 1 ]; then
  echo "✗ real-config smoke failed: no records from ../pipeline-manager"
  exit 1
fi
echo "✓ real-config smoke: $real_count records from ../pipeline-manager"

echo "✓ Snapshot generation complete. Output in $output_dir"
