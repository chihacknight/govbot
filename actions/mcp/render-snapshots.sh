#!/usr/bin/env bash
# Render the MCP server's snapshots.
#
# The tool surface is the contract with Claude Desktop, and the tool descriptions
# are shown to the person being asked for permission. Snapshotting both means a
# reworded description shows up as a reviewable diff rather than slipping out
# unnoticed.
set -euo pipefail

cd "$(dirname "$0")"
OUT="${1:-__snapshots__}"

if [ ! -d node_modules ]; then
  echo "Installing dependencies..." >&2
  npm install --silent
fi
npm run build --silent

echo "Rendering tool surface..." >&2
# A throwaway workspace, so snapshots never depend on the machine they ran on.
GOVBOT_WORKSPACE="$(mktemp -d)" \
  node scripts/mcp-session.mjs "$OUT/requests-surface.jsonl" \
  | python3 scripts/normalize-snapshot.py > "$OUT/surface.json"

echo "Wrote $OUT/surface.json" >&2
