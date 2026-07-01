#!/usr/bin/env bash
set -euo pipefail

# Usage: scrape.sh <state> [DOCKER_IMAGE] [working_dir] [output_dir] [api_keys_json]
#   state: State abbreviation (e.g., "id", "il", "tx", "ny", or "usa")
#   DOCKER_IMAGE: Full Docker image reference (defaults to "openstates/scrapers:latest")
#   working_dir: Optional working directory (defaults to current directory)
#   output_dir: Optional output directory for tarball (defaults to current directory)
#   api_keys_json: Optional JSON object with API keys (defaults to "{}")

STATE="${1:-}"
DOCKER_IMAGE="${2:-openstates/scrapers:latest}"
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
  docker pull ${DOCKER_IMAGE} || true
  # Capture output to log file while still displaying it
  # Virginia uses csv_bills scraper (no API key needed)
  if [ "${STATE}" = "va" ]; then
    if docker run \
        --dns 8.8.8.8 --dns 1.1.1.1 \
        -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
        -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
        "${DOCKER_ENV_FLAGS[@]+"${DOCKER_ENV_FLAGS[@]}"}" \
        ${DOCKER_IMAGE} \
        ${STATE} csv_bills --session=2026 --scrape --fastmode 2>&1 | tee -a "$SCRAPE_LOG"
    then
      exit_code=0
      break
    fi
  elif docker run \
      --dns 8.8.8.8 --dns 1.1.1.1 \
      -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
      -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
      "${DOCKER_ENV_FLAGS[@]+"${DOCKER_ENV_FLAGS[@]}"}" \
      ${DOCKER_IMAGE} \
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

# Classify failure type (see scrape-failure-types.md for full reference)
# Grep the log file directly — avoids broken-pipe errors from piping large variables through echo.
IS_ACTIVE_BLOCK="false"

if [ "$exit_code" -eq 0 ]; then
  FAILURE_TYPE="NONE"
elif grep -qE "ConnectionRefusedError|Errno 111" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="N1_ACTIVE_BLOCK"
  IS_ACTIVE_BLOCK="true"
elif grep -qE "ConnectionResetError" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="N3_ACTIVE_BLOCK"
  IS_ACTIVE_BLOCK="true"
elif grep -qE "403.*(Forbidden|forbidden)|Forbidden.*403" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="H1_ACTIVE_BLOCK"
  IS_ACTIVE_BLOCK="true"
elif grep -qE "Name or service not known|nodename nor servname provided|EAI_NONAME" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="N4_DNS_FAILURE"
  IS_ACTIVE_BLOCK="true"
elif grep -qE "429|Too Many Requests" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="H3_RATE_LIMITED"
elif grep -qE "TimeoutError|ConnectTimeoutError|timed out|Errno 110|RemoteDisconnected|Connection aborted" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="N2_CONNECTIVITY"
elif grep -qE "503|Service Unavailable" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="H4_SERVER_DOWN"
elif grep -qE "ScrapeValueError|validation.*failed|failed.*validation" "$SCRAPE_LOG" 2>/dev/null; then
  # Check before H2 — ScrapeValueError is a specific openstates schema failure, not an auth issue.
  # Logs can contain "401" or "Unauthorized" incidentally (e.g. DC uses Authorization header)
  # and would otherwise be misclassified as H2_AUTH_FAILURE.
  FAILURE_TYPE="S6_VALIDATION"
elif grep -qE "401|Unauthorized" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="H2_AUTH_FAILURE"
elif grep -qE "ScrapeError.*no objects returned|no objects returned" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="S1_OUT_OF_SESSION"
elif grep -qE "contains no matching files" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="S2_OUT_OF_SESSION"
elif grep -qE "AssertionError.*[Ss]ession" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="S3_SESSION_CONFIG"
elif grep -qE "KeyError" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="S4_SITE_STRUCTURE"
elif grep -qE "ValueError|IndexError" "$SCRAPE_LOG" 2>/dev/null; then
  FAILURE_TYPE="S5_SITE_STRUCTURE"
else
  FAILURE_TYPE="UNKNOWN"
fi

# Write summary JSON
cat > "$SUMMARY_FILE" <<EOF
{
  "state": "${STATE}",
  "exit_code": ${exit_code},
  "failure_type": "${FAILURE_TYPE}",
  "is_active_block": ${IS_ACTIVE_BLOCK},
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

# Export to GITHUB_ENV so downstream steps can read these without re-parsing the JSON file
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "SCRAPE_FAILURE_TYPE=${FAILURE_TYPE}" >> "$GITHUB_ENV"
  echo "SCRAPE_IS_ACTIVE_BLOCK=${IS_ACTIVE_BLOCK}" >> "$GITHUB_ENV"
  echo "SCRAPE_EXIT_CODE=${exit_code}" >> "$GITHUB_ENV"
fi

exit $exit_code

