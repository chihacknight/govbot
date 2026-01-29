#!/usr/bin/env bash
set -euo pipefail

# Usage: scrape.sh <state> [DOCKER_IMAGE_TAG] [working_dir] [output_dir] [api_keys_json]
#   state: State abbreviation (e.g., "id", "il", "tx", "ny", or "usa")
#   DOCKER_IMAGE_TAG: Docker image tag to use (defaults to "latest")
#   working_dir: Optional working directory (defaults to current directory)
#   output_dir: Optional output directory for tarball (defaults to current directory)
#   api_keys_json: Optional JSON object with API keys (defaults to "{}")

STATE="${1:-}"
DOCKER_IMAGE_TAG="${2:-latest}"
WORKING_DIR="${3:-$(pwd)}"
OUTPUT_DIR="${4:-$(pwd)}"
API_KEYS_JSON="${5:-{}}"

if [ -z "$STATE" ]; then
  echo "Error: State argument is required" >&2
  exit 1
fi

cd "$WORKING_DIR"
mkdir -p _working/_data _working/_cache

# Log file to capture Docker output for summary
SCRAPE_LOG="${OUTPUT_DIR}/scrape-output.log"
> "$SCRAPE_LOG"  # Clear/create log file

# Parse API keys from JSON and build Docker env flags
# Use array to properly handle values with spaces/special chars
DOCKER_ENV_FLAGS=()
if [ -n "$API_KEYS_JSON" ] && [ "$API_KEYS_JSON" != "{}" ]; then
  echo "🔑 Parsing API keys..."
  # Extract all keys from JSON and build -e flags for Docker
  # List of known API key environment variables
  API_KEY_NAMES=(
    "DC_API_KEY"
    "NEW_YORK_API_KEY"
    "INDIANA_API_KEY"
    "USER_AGENT"
  )

  for key_name in "${API_KEY_NAMES[@]}"; do
    # Try to extract key value from JSON using jq (if available) or fallback to grep
    if command -v jq >/dev/null 2>&1; then
      key_value=$(echo "$API_KEYS_JSON" | jq -r ".${key_name} // empty" 2>/dev/null || echo "")
    else
      # Fallback: use grep/sed to extract (basic parsing)
      key_value=$(echo "$API_KEYS_JSON" | grep -o "\"${key_name}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed 's/.*"\([^"]*\)"$/\1/' || echo "")
    fi

    if [ -n "$key_value" ] && [ "$key_value" != "null" ]; then
      # Add to array with proper quoting for values with spaces
      DOCKER_ENV_FLAGS+=(-e "${key_name}=${key_value}")
      echo "  ✓ Set ${key_name}"
    fi
  done
fi

echo "🕷️ Scraping ${STATE} (with retries + DNS override)..."
exit_code=1
for i in 1 2 3; do
  docker pull openstates/scrapers:${DOCKER_IMAGE_TAG} || true
  # Capture output to log file while still displaying it
  # Virginia uses csv_bills scraper (no API key needed)
  # NOTE: VA 2026 session starts Jan 14, 2026. Will fail until openstates-scrapers
  # Docker image is updated with 2026 session mapping. Code is correct and ready.
  if [ "${STATE}" = "va" ]; then
    if docker run \
        --dns 8.8.8.8 --dns 1.1.1.1 \
        -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
        -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
        "${DOCKER_ENV_FLAGS[@]+"${DOCKER_ENV_FLAGS[@]}"}" \
        openstates/scrapers:${DOCKER_IMAGE_TAG} \
        ${STATE} --session=2025 csv_bills --scrape --fastmode 2>&1 | tee -a "$SCRAPE_LOG"
    then
      exit_code=0
      break
    fi
  elif docker run \
      --dns 8.8.8.8 --dns 1.1.1.1 \
      -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
      -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
      "${DOCKER_ENV_FLAGS[@]+"${DOCKER_ENV_FLAGS[@]}"}" \
      openstates/scrapers:${DOCKER_IMAGE_TAG} \
      ${STATE} bills --scrape --fastmode 2>&1 | tee -a "$SCRAPE_LOG"
  then
    exit_code=0
    break
  fi
  echo "⚠️ scrape attempt $i failed; sleeping 20s..." | tee -a "$SCRAPE_LOG"
  sleep 20
done

# If anything was scraped, stage a tarball; otherwise fall back later
JSON_DIR="_working/_data/${STATE}"
if [ -d "$JSON_DIR" ]; then
  COUNT_JSON=$(find "$JSON_DIR" -type f -name '*.json' | wc -l | tr -d ' ')
else
  COUNT_JSON=0
fi
echo "Found ${COUNT_JSON} JSON files in $JSON_DIR"
if [ "$COUNT_JSON" -gt 0 ]; then
  # Copy files directly to workspace _data directory
  # Clean the directory first to avoid accumulating stale files with different UUIDs
  mkdir -p "${OUTPUT_DIR}/_data/${STATE}"

  # Copy all files from JSON_DIR to output directory
  if [ -d "$JSON_DIR" ]; then
    # Delete entire directory first for clean state, then copy all new files
    echo "🧹 Cleaning _data/${STATE}/ directory..."
    rm -rf "${OUTPUT_DIR}/_data/${STATE}"
    mkdir -p "${OUTPUT_DIR}/_data/${STATE}"

    # Copy all files (use rsync if available for better performance, otherwise cp)
    if command -v rsync >/dev/null 2>&1; then
      rsync -a "$JSON_DIR/" "${OUTPUT_DIR}/_data/${STATE}/"
    else
      cp -r "$JSON_DIR"/* "${OUTPUT_DIR}/_data/${STATE}/" 2>/dev/null || true
    fi

    # Verify files were copied
    COPIED_COUNT=$(find "${OUTPUT_DIR}/_data/${STATE}" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
    echo "✅ ${COPIED_COUNT} scraped files in ${OUTPUT_DIR}/_data/${STATE}/"
  fi

  # Also create tarball for artifacts/releases
  tar zcf scrape-snapshot-nightly.tgz --mode=755 -C "$JSON_DIR" .
  cp scrape-snapshot-nightly.tgz "${OUTPUT_DIR}/scrape-snapshot-nightly.tgz"
  echo "✅ Created local scrape tarball"
else
  echo "ℹ️ No new files found; will use nightly fallback."
fi

# Do not fail the job; proceed with fallback or partial data
if [ $exit_code -ne 0 ]; then
  echo "Warning: Scrape step exited non-zero; continuing with fallback/nightly artifact." >&2
fi

# Parse scrape log and create summary JSON
SUMMARY_FILE="${OUTPUT_DIR}/scrape-summary.json"

# Extract object counts from "object_type: N" patterns
# Main data objects
BILL_COUNT=$(grep -oP '^\s*bill:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")
VOTE_EVENT_COUNT=$(grep -oP '^\s*vote_event:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")
EVENT_COUNT=$(grep -oP '^\s*event:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")

# Metadata objects
JURISDICTION_COUNT=$(grep -oP '^\s*jurisdiction:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")
ORG_COUNT=$(grep -oP '^\s*organization:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")

# Extract duration from "duration: H:MM:SS" pattern (bills scrape)
DURATION=$(grep -A2 'bills scrape:' "$SCRAPE_LOG" 2>/dev/null | grep -oP 'duration:\s*\K[\d:\.]+' || echo "unknown")

# Extract errors - look for Python tracebacks and exceptions
# First, find traceback blocks (multi-line)
TRACEBACKS=$(grep -A 10 '^Traceback (most recent call last):' "$SCRAPE_LOG" 2>/dev/null | head -30 || echo "")

# Find exception lines (but exclude common retry/resolved messages and INFO level logs)
EXCEPTIONS=$(grep -iE '^\w+Error:|^\w+Exception:|^\w+Warning:' "$SCRAPE_LOG" 2>/dev/null | \
  grep -vE '(retry|retrying|resolved|recovered|succeeded after|^\d+:\d+:\d+ INFO)' | head -10 || echo "")

# Find other error indicators (ERROR/EXCEPTION/TRACEBACK in caps, exclude INFO logs and "failed" in vote messages)
# Only match actual error keywords in caps, not "failed" in vote outcomes
# Exclude ALL lines that contain " INFO " (case-insensitive) to filter out informational logs
OTHER_ERRORS=$(grep -E '(ERROR|EXCEPTION|TRACEBACK|AssertionError|TimeoutError|ConnectionError|HTTPError)' "$SCRAPE_LOG" 2>/dev/null | \
  grep -viE '( INFO |scrape attempt|retry|retrying|resolved|recovered|succeeded)' | \
  head -10 || echo "")

# Combine errors, prioritizing tracebacks
if [ -n "$TRACEBACKS" ]; then
  ERRORS="$TRACEBACKS"
elif [ -n "$EXCEPTIONS" ]; then
  ERRORS="$EXCEPTIONS"
else
  ERRORS="$OTHER_ERRORS"
fi

# Count unique error occurrences (rough estimate)
if [ -n "$TRACEBACKS" ]; then
  ERROR_COUNT=$(echo "$TRACEBACKS" | grep -c 'Traceback\|Error\|Exception' 2>/dev/null || echo "1")
elif [ -n "$EXCEPTIONS" ]; then
  ERROR_COUNT=$(echo "$EXCEPTIONS" | wc -l | tr -d ' ')
else
  ERROR_COUNT=$(echo "$OTHER_ERRORS" | wc -l | tr -d ' ')
fi

# Write summary JSON
cat > "$SUMMARY_FILE" <<EOF
{
  "state": "${STATE}",
  "exit_code": ${exit_code},
  "objects": {
    "bill": ${BILL_COUNT:-0},
    "vote_event": ${VOTE_EVENT_COUNT:-0},
    "event": ${EVENT_COUNT:-0}
  },
  "metadata": {
    "jurisdiction": ${JURISDICTION_COUNT:-0},
    "organization": ${ORG_COUNT:-0}
  },
  "json_files": ${COUNT_JSON:-0},
  "duration": "${DURATION}",
  "error_count": ${ERROR_COUNT},
  "errors": $(echo "$ERRORS" | head -5 | jq -R -s 'split("\n") | map(select(. != ""))')
}
EOF

echo "📊 Scrape summary written to $SUMMARY_FILE"

exit $exit_code

