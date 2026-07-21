#!/usr/bin/env bash
set -euo pipefail

# Usage: scrape.sh <state> [DOCKER_IMAGE] [working_dir] [output_dir] [api_keys_json] [branch]
#   state: State abbreviation (e.g., "id", "il", "tx", "ny", or "usa")
#   DOCKER_IMAGE: Full Docker image reference (defaults to "openstates/scrapers:latest")
#   working_dir: Optional working directory (defaults to current directory)
#   output_dir: Optional output directory for tarball (defaults to current directory)
#   api_keys_json: Optional JSON object with API keys (defaults to "{}")
#   branch: Git branch the incremental auto-save should push to (defaults to "main",
#           should match whatever branch the caller's later "Commit and push" step uses)

STATE="${1:-}"
DOCKER_IMAGE="${2:-openstates/scrapers:latest}"
WORKING_DIR="${3:-$(pwd)}"
OUTPUT_DIR="${4:-$(pwd)}"
API_KEYS_JSON="${5:-{}}"
BRANCH="${6:-main}"

if [ -z "$STATE" ]; then
  echo "Error: State argument is required" >&2
  exit 1
fi

cd "$WORKING_DIR"
mkdir -p _working/_data _working/_cache

# Log file to capture Docker output for summary
SCRAPE_LOG="${OUTPUT_DIR}/scrape-output.log"
> "$SCRAPE_LOG"  # Clear/create log file

# --- Incremental auto-commit, mirroring actions/extract's 30-minute auto-save ---
#
# The scraper writes into $WORKING_DIR/_working/_data/${STATE}, a Docker-mounted
# temp directory outside the git checkout -- nothing lands in $OUTPUT_DIR (the
# git repo) or gets committed until the whole scrape finishes and the wipe/copy
# block below runs. For a state that can take many hours (e.g. FL), that means
# a runner crash or lost-connection mid-scrape loses everything, not just the
# most recent bit of progress -- discovered the hard way after a 21-hour FL
# run died to "runner lost communication" with nothing to show for it.
#
# This loop periodically copies whatever's landed so far into $OUTPUT_DIR and
# commits it, same spirit as extract's background loop. Unlike the final
# wipe-then-replace block below, this is additive only (rsync without
# --delete) -- the scrape is still in progress, so the full/correct file set
# doesn't exist yet, and deleting anything here could discard real data still
# mid-write. The final block still does the authoritative wipe + rebuild once
# the scrape actually completes, which naturally cleans up anything stale left
# behind by these incremental saves (e.g. a bill whose UUID changed between an
# auto-save and the final commit).
AUTOSAVE_INTERVAL="${SCRAPE_AUTOSAVE_INTERVAL:-1800}"  # 30 minutes, overridable for tests
AUTOSAVE_FLAG="$(mktemp -d)/scrape_running_${STATE}"
touch "$AUTOSAVE_FLAG"

(
  while [ -f "$AUTOSAVE_FLAG" ]; do
    sleep "$AUTOSAVE_INTERVAL"
    [ -f "$AUTOSAVE_FLAG" ] || break

    SRC_DIR="${WORKING_DIR}/_working/_data/${STATE}"
    [ -d "$SRC_DIR" ] || continue
    SRC_COUNT=$(find "$SRC_DIR" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
    [ "$SRC_COUNT" -gt 0 ] || continue

    echo "⏰ [$(date -u +%Y-%m-%dT%H:%M:%SZ)] Auto-saving ${SRC_COUNT} in-progress ${STATE} files..."

    mkdir -p "${OUTPUT_DIR}/_data/${STATE}"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a "$SRC_DIR/" "${OUTPUT_DIR}/_data/${STATE}/"
    else
      cp -rn "$SRC_DIR"/* "${OUTPUT_DIR}/_data/${STATE}/" 2>/dev/null || true
    fi

    (
      cd "$OUTPUT_DIR"
      git config --local user.email "action@github.com" 2>/dev/null || true
      git config --local user.name "GitHub Action" 2>/dev/null || true
      git add "_data/${STATE}/" 2>/dev/null || true
      if ! git diff --staged --quiet; then
        git commit -m "🔄 Auto-save in-progress scrape for ${STATE} - $(date -u +%Y-%m-%dT%H:%M:%SZ)" || true
        for i in 1 2 3; do
          if git pull --no-rebase origin "${BRANCH}" 2>&1 && \
             git push origin "${BRANCH}" 2>&1; then
            echo "✅ Auto-saved progress (attempt $i)"
            break
          fi
          echo "⚠️ Auto-save push failed (attempt $i), retrying..."
          sleep 5
        done
      fi
    )
  done
) &
AUTOSAVE_PID=$!
echo "🔄 Incremental auto-save started (PID: $AUTOSAVE_PID, every ${AUTOSAVE_INTERVAL}s)"

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
    "HTTPS_PROXY"
    "HTTP_PROXY"
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

if [ "${STATE}" = "va" ]; then
  # Virginia uses csv_bills scraper for two sessions; run each independently with retries
  va_regular_exit=1
  for i in 1 2 3; do
    docker pull ${DOCKER_IMAGE} || true
    if docker run \
        --dns 8.8.8.8 --dns 1.1.1.1 \
        -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
        -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
        "${DOCKER_ENV_FLAGS[@]+"${DOCKER_ENV_FLAGS[@]}"}" \
        ${DOCKER_IMAGE} \
        ${STATE} csv_bills --scrape session=2026 --fastmode 2>&1 | tee -a "$SCRAPE_LOG"
    then
      va_regular_exit=0
      break
    fi
    echo "⚠️ VA 2026 scrape attempt $i failed; sleeping 20s..." | tee -a "$SCRAPE_LOG"
    sleep 20
  done

  va_special_exit=1
  for i in 1 2 3; do
    docker pull ${DOCKER_IMAGE} || true
    if docker run \
        --dns 8.8.8.8 --dns 1.1.1.1 \
        -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
        -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
        "${DOCKER_ENV_FLAGS[@]+"${DOCKER_ENV_FLAGS[@]}"}" \
        ${DOCKER_IMAGE} \
        ${STATE} csv_bills --scrape session=2026S1 --fastmode 2>&1 | tee -a "$SCRAPE_LOG"
    then
      va_special_exit=0
      break
    fi
    echo "⚠️ VA 2026S1 scrape attempt $i failed; sleeping 20s..." | tee -a "$SCRAPE_LOG"
    sleep 20
  done

  if [ $va_regular_exit -eq 0 ] && [ $va_special_exit -eq 0 ]; then
    exit_code=0
  fi
else
  for i in 1 2 3; do
    docker pull ${DOCKER_IMAGE} || true
    if docker run \
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
fi

# Stop the incremental auto-save now that the scrape itself is done (success
# or not) -- the final wipe/rebuild block below is the authoritative save from
# here on, and shouldn't race with a background auto-save mid-commit.
echo "🛑 Stopping incremental auto-save..."
rm -f "$AUTOSAVE_FLAG"
kill "$AUTOSAVE_PID" 2>/dev/null || true
sleep 1
kill -9 "$AUTOSAVE_PID" 2>/dev/null || true
wait "$AUTOSAVE_PID" 2>/dev/null || true
echo "✅ Incremental auto-save stopped"

# Only replace existing data + rebuild the fallback tarball when the scrape
# actually succeeded (exit_code 0). A retry-exhausted failure (e.g. rate
# limiting, a block) can still leave a handful of jurisdiction/organization
# files on disk from before it died — COUNT_JSON alone can't tell that apart
# from a real successful scrape, and treating it as "good" wholesale-deletes
# real historical data and overwrites the nightly fallback release with the
# same partial output, destroying the safety net for future failed runs too.
JSON_DIR="_working/_data/${STATE}"
if [ -d "$JSON_DIR" ]; then
  COUNT_JSON=$(find "$JSON_DIR" -type f -name '*.json' | wc -l | tr -d ' ')
else
  COUNT_JSON=0
fi
echo "Found ${COUNT_JSON} JSON files in $JSON_DIR"

# exit_code == 0 only means the docker scraper itself didn't crash -- it does
# NOT mean this run produced a complete dataset. A run that gets cut short
# (e.g. cancelled by a newer trigger and replaced by a fresh, short-lived one;
# or a retry attempt within this same run that returns less than an earlier
# attempt already did) can still exit 0 with a handful of real files, which
# used to be enough to trigger the wipe below and silently replace a larger,
# good dataset with a smaller one -- confirmed happening for real on IL (a
# single run's last retry produced ~4k files after auto-save had already
# captured ~19k earlier in that same run) and FL (a fresh run, started after
# an in-progress 6-hour run got cancelled, "succeeded" with a fraction of a
# full scrape and overwrote the larger dataset the cancelled run had already
# saved). Comparing against what's already committed catches both: within a
# single run there's no legitimate reason a later retry has fewer real bills
# than an earlier one already did today, and across runs the existing count
# already reflects this run's own auto-saves, not stale history -- so a
# shrink here is always suspicious, never normal session growth (which only
# ever adds bills over time).
EXISTING_DIR="${OUTPUT_DIR}/_data/${STATE}"
if [ -d "$EXISTING_DIR" ]; then
  EXISTING_COUNT=$(find "$EXISTING_DIR" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
else
  EXISTING_COUNT=0
fi

if [ "$exit_code" -eq 0 ] && [ "$COUNT_JSON" -gt 0 ] && [ "$COUNT_JSON" -lt "$EXISTING_COUNT" ]; then
  echo "⚠️ Fresh scrape produced ${COUNT_JSON} files, fewer than the ${EXISTING_COUNT} already saved -- refusing to overwrite. Leaving existing data in place; this run's output is not being committed." >&2
  FAILURE_TYPE_OVERRIDE="P1_SHRINKING_OUTPUT"
  COUNT_JSON=0  # so the summary/downstream logic reports this as "nothing new," not a success
elif [ "$exit_code" -eq 0 ] && [ "$COUNT_JSON" -gt 0 ]; then
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

  # Also create tarball for artifacts/releases, built from the already-copied
  # output directory rather than $JSON_DIR. Two reasons: (1) $JSON_DIR is
  # written by the scraper Docker container as root, so chmod-ing it as the
  # non-root runner user fails with "Operation not permitted" and (under
  # set -e) silently kills the rest of the script -- the tarball, and every
  # downstream stat that depends on it, just vanishes even though the real
  # data already copied out fine. (2) Building from the copy also sidesteps
  # GNU tar's --mode flag, which macOS's built-in BSD tar (self-hosted Mac
  # runners) doesn't support and fails on silently -- same fix, one place.
  chmod -R 755 "${OUTPUT_DIR}/_data/${STATE}"
  tar zcf scrape-snapshot-nightly.tgz -C "${OUTPUT_DIR}/_data/${STATE}" .
  cp scrape-snapshot-nightly.tgz "${OUTPUT_DIR}/scrape-snapshot-nightly.tgz"
  echo "✅ Created local scrape tarball"
elif [ "$COUNT_JSON" -gt 0 ]; then
  echo "⚠️ Scrape failed (exit code ${exit_code}) despite ${COUNT_JSON} partial JSON file(s) on disk; discarding partial output and using nightly fallback."
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
BILL_COUNT=$(grep -E '^\s*bill:\s*[0-9]+' "$SCRAPE_LOG" 2>/dev/null | grep -oE '[0-9]+$' | tail -1 || echo "0")
VOTE_EVENT_COUNT=$(grep -E '^\s*vote_event:\s*[0-9]+' "$SCRAPE_LOG" 2>/dev/null | grep -oE '[0-9]+$' | tail -1 || echo "0")
EVENT_COUNT=$(grep -E '^\s*event:\s*[0-9]+' "$SCRAPE_LOG" 2>/dev/null | grep -oE '[0-9]+$' | tail -1 || echo "0")

# Metadata objects
JURISDICTION_COUNT=$(grep -E '^\s*jurisdiction:\s*[0-9]+' "$SCRAPE_LOG" 2>/dev/null | grep -oE '[0-9]+$' | tail -1 || echo "0")
ORG_COUNT=$(grep -E '^\s*organization:\s*[0-9]+' "$SCRAPE_LOG" 2>/dev/null | grep -oE '[0-9]+$' | tail -1 || echo "0")

# Extract duration from "duration: H:MM:SS" pattern (bills scrape)
DURATION=$(grep -A2 'bills scrape:' "$SCRAPE_LOG" 2>/dev/null | grep -oE 'duration:\s*[0-9:.]+' | grep -oE '[0-9:.]+$' | head -1 || echo "unknown")

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

if [ -n "${FAILURE_TYPE_OVERRIDE:-}" ]; then
  FAILURE_TYPE="$FAILURE_TYPE_OVERRIDE"
elif [ "$exit_code" -eq 0 ]; then
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

