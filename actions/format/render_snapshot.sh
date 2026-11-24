#!/usr/bin/env bash
# Local snapshot renderer - uses main.sh for common logic
set -euo pipefail

# Configuration
STATE="wy"
INPUT_DIR="../scrape/prod-mocks-2025-11-25/_working/_data"
TMP_DIR="./tmp/sanitize"
OUTPUT_DIR="./snapshots/$STATE"

# Get the script directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Reset snapshots
echo "🧹 Cleaning output directory..."
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy the production mocks to temporary directory
echo "📂 Copying input data..."
if [ ! -d "$INPUT_DIR" ]; then
    echo "❌ Input directory not found: $INPUT_DIR"
    exit 1
fi
cp -r "$INPUT_DIR" "$TMP_DIR"

# Run the main formatter script. first_seen is pinned to the mock scrape's date
# (prod-mocks-2025-11-25) so the snapshot doesn't change with the day it's rendered.
OSDF_FIRST_SEEN="2025-11-25T00:00:00+00:00" "$SCRIPT_DIR/main.sh" "$STATE" "$TMP_DIR" "$OUTPUT_DIR"


