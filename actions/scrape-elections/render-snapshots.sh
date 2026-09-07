#!/usr/bin/env bash
# Regenerate the offline expected snapshot from the raw fixtures. Run this after
# an intentional parser/output change, then review the diff before committing.
set -euo pipefail
cd "$(dirname "$0")"
python3 main.py \
  --from-fixtures __snapshots__/raw \
  --now 2026-09-07T00:00:00Z \
  --output __snapshots__/expected_elections.json
echo "rendered __snapshots__/expected_elections.json"
