#!/usr/bin/env bash
set -euo pipefail

# California-specific scraper using MySQL dumps
# Usage: scrape-ca.sh <working_dir> <output_dir> <docker_image_tag> [session]
#   working_dir: Working directory for MySQL data
#   output_dir: Output directory for tarball
#   docker_image_tag: Docker image tag (defaults to 'latest')
#   session: Optional OpenStates session id (e.g. "20252026"); empty = OpenStates'
#            active sessions (see scrape.sh). CA has no separate votes scraper.

WORKING_DIR="${1:-$(pwd)}"
OUTPUT_DIR="${2:-$(pwd)}"
DOCKER_IMAGE_TAG="${3:-latest}"
SESSION="${4:-}"
STATE="ca"

# Lands inside a bash -c string below, so allow only what real session ids use.
if ! [[ "$SESSION" =~ ^[A-Za-z0-9._-]*$ ]]; then
  echo "Error: session '${SESSION}' may only contain letters, digits, '.', '_' and '-'" >&2
  exit 1
fi
SESSION_ARG="${SESSION:+ session=${SESSION}}"

cd "$WORKING_DIR"
mkdir -p _working/_data _working/_cache mysql_data

# Log file to capture output
SCRAPE_LOG="${OUTPUT_DIR}/scrape-output.log"
> "$SCRAPE_LOG"

echo "🕷️ Scraping California (MySQL-based)..." | tee -a "$SCRAPE_LOG"

# Start MariaDB container (matches OpenStates docker-compose config)
echo "🐬 Starting MariaDB container..." | tee -a "$SCRAPE_LOG"
MYSQL_CONTAINER="ca-mysql-$(date +%s)"
docker run -d \
  --name "$MYSQL_CONTAINER" \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=capublic \
  -v "$(pwd)/mysql_data":/var/lib/mysql \
  mariadb:10.5 2>&1 | tee -a "$SCRAPE_LOG"

# Wait for MySQL to be ready
echo "⏳ Waiting for MySQL to initialize..." | tee -a "$SCRAPE_LOG"
sleep 15

# Use standard scraper image and install sqlalchemy at runtime
echo "📥 Pulling scraper image..." | tee -a "$SCRAPE_LOG"
docker pull openstates/scrapers:${DOCKER_IMAGE_TAG} 2>&1 | tee -a "$SCRAPE_LOG" || true

# Step 1: Download CA MySQL data using the download module
echo "📥 Downloading California MySQL dumps (installing dependencies first)..." | tee -a "$SCRAPE_LOG"
if docker run --rm \
  --link "$MYSQL_CONTAINER":mysql \
  -e MYSQL_HOST=mysql \
  -e MYSQL_USER=root \
  -e MYSQL_PASSWORD="" \
  -e MYSQL_DATABASE=capublic \
  --entrypoint /bin/bash \
  openstates/scrapers:${DOCKER_IMAGE_TAG} \
  -c "apt-get update -qq && apt-get install -y -qq pkg-config default-libmysqlclient-dev build-essential && /root/.cache/pypoetry/virtualenvs/*/bin/pip install -q 'sqlalchemy<2.0' pymysql mysqlclient && poetry run python -m scrapers.ca.download" 2>&1 | tee -a "$SCRAPE_LOG"
then
  echo "✅ CA data downloaded and loaded into MySQL" | tee -a "$SCRAPE_LOG"
else
  echo "⚠️ CA data download failed, continuing anyway..." | tee -a "$SCRAPE_LOG"
fi

# Step 2: Install dependencies and run CA scraper
exit_code=0
echo "🔧 Installing sqlalchemy and running CA scraper..." | tee -a "$SCRAPE_LOG"
if docker run --rm \
  --link "$MYSQL_CONTAINER":mysql \
  -e MYSQL_HOST=mysql \
  -e MYSQL_USER=root \
  -e MYSQL_PASSWORD="" \
  -e MYSQL_DATABASE=capublic \
  -v "$(pwd)/_working/_data":/opt/openstates/openstates/_data \
  -v "$(pwd)/_working/_cache":/opt/openstates/openstates/_cache \
  --entrypoint /bin/bash \
  openstates/scrapers:${DOCKER_IMAGE_TAG} \
  -c "apt-get update -qq && apt-get install -y -qq pkg-config default-libmysqlclient-dev build-essential && /root/.cache/pypoetry/virtualenvs/*/bin/pip install -q 'sqlalchemy<2.0' pymysql mysqlclient && /root/.cache/pypoetry/virtualenvs/*/bin/os-update ca bills${SESSION_ARG} --scrape --fastmode" 2>&1 | tee -a "$SCRAPE_LOG"
then
  echo "✅ California scrape completed" | tee -a "$SCRAPE_LOG"
else
  exit_code=$?
  echo "⚠️ California scrape failed with exit code $exit_code" | tee -a "$SCRAPE_LOG"
fi

# Stop and remove MySQL container
echo "🧹 Cleaning up MySQL container..." | tee -a "$SCRAPE_LOG"
docker stop "$MYSQL_CONTAINER" 2>&1 | tee -a "$SCRAPE_LOG" || true
docker rm "$MYSQL_CONTAINER" 2>&1 | tee -a "$SCRAPE_LOG" || true

# Check if any files were scraped
JSON_DIR="_working/_data/${STATE}"
if [ -d "$JSON_DIR" ]; then
  COUNT_JSON=$(find "$JSON_DIR" -type f -name '*.json' | wc -l | tr -d ' ')
else
  COUNT_JSON=0
fi

echo "Found ${COUNT_JSON} JSON files for California" | tee -a "$SCRAPE_LOG"

if [ "$COUNT_JSON" -gt 0 ]; then
  # Copy files and create tarball (same as regular scrape.sh)
  mkdir -p "${OUTPUT_DIR}/_data/${STATE}"

  if command -v rsync >/dev/null 2>&1; then
    echo "🧹 Syncing scraped files (removing stale files)..."
    rsync -av --delete "$JSON_DIR/" "${OUTPUT_DIR}/_data/${STATE}/"
  else
    echo "🧹 Cleaning _data/${STATE}/ directory..."
    rm -rf "${OUTPUT_DIR}/_data/${STATE}"
    mkdir -p "${OUTPUT_DIR}/_data/${STATE}"
    find "$JSON_DIR" -type f -exec cp {} "${OUTPUT_DIR}/_data/${STATE}/" \;
  fi

  COPIED_COUNT=$(find "${OUTPUT_DIR}/_data/${STATE}" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
  echo "✅ ${COPIED_COUNT} scraped files in ${OUTPUT_DIR}/_data/${STATE}/"

  # Create tarball
  tar zcf scrape-snapshot-nightly.tgz --mode=755 -C "$JSON_DIR" .
  cp scrape-snapshot-nightly.tgz "${OUTPUT_DIR}/scrape-snapshot-nightly.tgz"
  echo "✅ Created local scrape tarball"
else
  echo "ℹ️ No files found; MySQL setup may need additional configuration."
fi

# Parse logs and create summary (simplified for now)
BILL_COUNT=$(grep -oP '^\s*bill:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")
VOTE_EVENT_COUNT=$(grep -oP '^\s*vote_event:\s*\K\d+' "$SCRAPE_LOG" 2>/dev/null | tail -1 || echo "0")

cat > "${OUTPUT_DIR}/scrape-summary.json" <<EOF
{
  "state": "ca",
  "exit_code": ${exit_code},
  "objects": {
    "bill": ${BILL_COUNT:-0},
    "vote_event": ${VOTE_EVENT_COUNT:-0},
    "event": 0
  },
  "metadata": {
    "jurisdiction": 0,
    "organization": 0
  },
  "json_files": ${COUNT_JSON:-0},
  "duration": "unknown",
  "error_count": 0,
  "errors": []
}
EOF

echo "📊 CA scrape summary written" | tee -a "$SCRAPE_LOG"

exit $exit_code

