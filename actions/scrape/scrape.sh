#!/usr/bin/env bash
set -euo pipefail

# Usage: scrape.sh <state> [DOCKER_IMAGE_TAG] [working_dir] [output_dir]
#   state: State abbreviation (e.g., "id", "il", "tx", "ny", or "usa")
#   DOCKER_IMAGE_TAG: Docker image tag to use (defaults to "latest")
#   working_dir: Optional working directory (defaults to current directory)
#   output_dir: Optional output directory for tarball (defaults to current directory)

STATE="${1:-}"
DOCKER_IMAGE_TAG="${2:-latest}"
WORKING_DIR="${3:-$(pwd)}"
OUTPUT_DIR="${4:-$(pwd)}"

if [ -z "$STATE" ]; then
  echo "Error: State argument is required" >&2
  exit 1
fi

cd "$WORKING_DIR"
mkdir -p _working/_data _working/_cache

echo "🕷️ Scraping ${STATE} (with retries + DNS override)..."
exit_code=1
for i in 1 2 3; do
  docker pull openstates/scrapers:${DOCKER_IMAGE_TAG} || true
  if docker run \
      --dns 8.8.8.8 --dns 1.1.1.1 \
      -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
      -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
      openstates/scrapers:${DOCKER_IMAGE_TAG} \
      ${STATE} bills --scrape --fastmode
  then
    exit_code=0
    break
  fi
  echo "⚠️ scrape attempt $i failed; sleeping 20s..."
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
  mkdir -p "${OUTPUT_DIR}/_data/${STATE}"
  
  # Copy all files from JSON_DIR to output directory
  if [ -d "$JSON_DIR" ]; then
    # Use rsync if available (more reliable), otherwise use cp with proper glob handling
    if command -v rsync >/dev/null 2>&1; then
      rsync -av "$JSON_DIR/" "${OUTPUT_DIR}/_data/${STATE}/"
    else
      # Use find to copy files reliably
      find "$JSON_DIR" -type f -exec cp {} "${OUTPUT_DIR}/_data/${STATE}/" \;
    fi
    
    # Verify files were copied
    COPIED_COUNT=$(find "${OUTPUT_DIR}/_data/${STATE}" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
    echo "✅ Copied ${COPIED_COUNT} scraped files to ${OUTPUT_DIR}/_data/${STATE}/"
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

exit $exit_code

