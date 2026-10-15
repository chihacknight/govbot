#!/usr/bin/env bash
# Build govbot.mcpb — the one-file install for Claude Desktop.
#
# The bundle has to run without an `npm install` on the far side, so production
# dependencies are staged into it. Source maps and tests are left out; they only
# make the download bigger.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
OUT="${1:-$ROOT/govbot.mcpb}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# package.json is the version source of truth: the server reads it at runtime
# and the release publishes it. The manifest is what Claude Desktop shows, so a
# mismatch would make the bundle claim one version and report another.
PKG_VERSION=$(node -p 'require("./package.json").version')
MANIFEST_VERSION=$(node -p 'require("./mcpb/manifest.json").version')
if [ "$PKG_VERSION" != "$MANIFEST_VERSION" ]; then
  echo "Version mismatch: package.json is $PKG_VERSION but mcpb/manifest.json is $MANIFEST_VERSION." >&2
  echo "Bump both together." >&2
  exit 1
fi

# The version the bundle ships as. Locally that is package.json's version. The
# nightly release passes GOVBOT_MCP_VERSION=<that version>-nightly.<UTC
# YYYYMMDDHHMM> so each night's bundle is newer than the last; without it every
# nightly would be "0.1.0" and nobody would ever see an update. Only a
# pre-release of package.json's own version is accepted, so the stamp can never
# drift from the source of truth. It is written into the staged copies of
# manifest.json and package.json only; the checked-in files are not touched.
VERSION="${GOVBOT_MCP_VERSION:-$PKG_VERSION}"
if [ "$VERSION" != "$PKG_VERSION" ]; then
  case "$VERSION" in
    "$PKG_VERSION"-*) ;;
    *) echo "GOVBOT_MCP_VERSION=$VERSION must be $PKG_VERSION or a pre-release of it ($PKG_VERSION-...)." >&2; exit 1 ;;
  esac
  if ! printf '%s' "${VERSION#"$PKG_VERSION"-}" | grep -Eq '^[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*$'; then
    echo "GOVBOT_MCP_VERSION=$VERSION has an invalid pre-release part." >&2
    exit 1
  fi
fi

echo "Building..." >&2
npm install --silent
npm run build --silent

mkdir -p "$STAGE/server"
cp -R dist/. "$STAGE/server/"
rm -f "$STAGE/server"/*.map "$STAGE/server"/*.test.js
cp mcpb/manifest.json "$STAGE/manifest.json"
cp package.json "$STAGE/server/package.json"
STAGE="$STAGE" VERSION="$VERSION" node -e '
  const fs = require("fs");
  for (const file of [process.env.STAGE + "/manifest.json", process.env.STAGE + "/server/package.json"]) {
    const json = JSON.parse(fs.readFileSync(file, "utf8"));
    json.version = process.env.VERSION;
    fs.writeFileSync(file, JSON.stringify(json, null, 2) + "\n");
  }
'

echo "Staging production dependencies..." >&2
(cd "$STAGE/server" && npm install --silent --omit=dev --no-package-lock)

npx --yes @anthropic-ai/mcpb@2.1.2 validate "$STAGE/manifest.json"

# A bundle that cannot answer tools/list is not worth shipping, so prove it runs
# from the staging directory before packing it.
echo "Verifying the staged server starts..." >&2
# Collected rather than piped into grep: `grep -q` exits on its first match, and
# under `pipefail` the resulting SIGPIPE on node would fail the whole pipeline.
PROBE=$(printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"build","version":"1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | GOVBOT_WORKSPACE="$(mktemp -d)" GOVBOT_NO_UPDATE_CHECK=1 node "$STAGE/server/index.js" 2>/dev/null)

case "$PROBE" in
  *'"tools"'*) ;;
  *) echo "The staged server did not answer tools/list." >&2; exit 1 ;;
esac
# The update check compares against the version the server reports, so it must
# be the stamped one, not whatever package.json said before staging.
case "$PROBE" in
  *'"name":"govbot","version":"'"$VERSION"'"'*) ;;
  *) echo "The staged server does not report version $VERSION." >&2; exit 1 ;;
esac

npx --yes @anthropic-ai/mcpb@2.1.2 pack "$STAGE" "$OUT"
echo "Wrote $OUT (version $VERSION)" >&2
