#!/bin/bash
# Snapshots for pipeline-manager: every session pair in jurisdictions.yml, rendered by
# jurisdictions.py. Verified in CI by scripts/verify-snapshots.sh (git diff against the
# committed snapshots).
set -e

output_dir="./__snapshots__"
mkdir -p "$output_dir"
rm -rf "$output_dir/jurisdictions"
python3 jurisdictions.py render -o "$output_dir/jurisdictions" > /dev/null
echo "✓ Rendered session pairs into $output_dir/jurisdictions"
