#!/bin/bash
# Local testing script for IL Urbanist Witness Slip Notifier
# Usage: ./local_test.sh

set -e

echo "🚇🏘️ IL Urbanist Witness Slip Notifier - Local Test"
echo "=================================================="
echo ""

# Set default environment variables for testing
export USER_NAME="${USER_NAME:-Test Urbanist}"
export USER_EMAIL="${USER_EMAIL:-[email protected]}"
export USER_ORG="${USER_ORG:-Test Org}"

export TOPICS_TRANSPORTATION="${TOPICS_TRANSPORTATION:-Transportation,Public Transit,Roads,Highways,Bicycle,Pedestrian,Traffic}"
export TOPICS_HOUSING="${TOPICS_HOUSING:-Housing,Affordable Housing,Real Estate,Zoning,Land Use,Development}"

export RECIPIENTS_TRANSPORTATION="${RECIPIENTS_TRANSPORTATION:-[email protected]}"
export RECIPIENTS_HOUSING="${RECIPIENTS_HOUSING:-[email protected]}"

# Check if data directory exists and has files
if [ ! -d "data/il" ] || [ -z "$(ls -A data/il 2>/dev/null)" ]; then
    echo "📥 Downloading IL bill data via GitHub Contents API..."
    mkdir -p data/il

    # Use the GitHub Contents API — raw.githubusercontent.com has no directory index
    API_URL="https://api.github.com/repos/govbot-openstates-scrapers/il-legislation/contents/_data/il"
    echo "  Querying: $API_URL"

    python3 - <<'PYEOF'
import json, sys, urllib.request, os

api_url = "https://api.github.com/repos/govbot-openstates-scrapers/il-legislation/contents/_data/il"
req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        entries = json.load(resp)
except Exception as e:
    print(f"  ⚠️  API request failed: {e}")
    sys.exit(0)  # non-fatal; test-data may already exist

downloaded = 0
for entry in entries[:10]:  # grab up to 10 bills for local testing
    url = entry.get("download_url")
    if not url:
        continue
    name = entry.get("name", url.split("/")[-1])
    dest = os.path.join("data/il", name)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  ✅ {name}")
        downloaded += 1
    except Exception as e:
        print(f"  ⚠️  Failed {name}: {e}")

if downloaded == 0:
    print("  ⚠️  No bills downloaded. Check network or verify repo path.")
else:
    print(f"  Downloaded {downloaded} bill file(s) to data/il/")
PYEOF

    if [ -z "$(ls -A data/il 2>/dev/null)" ]; then
        echo "  ⚠️  data/il is still empty. Run 'python scripts/witness_slip_notifier.py --sample' to use temp files."
    fi
fi

echo ""
echo "🔧 Running notifier..."
echo ""

python scripts/witness_slip_notifier.py --mode local --data-dir data/il

echo ""
echo "✅ Test complete!"
echo ""
echo "Output files generated:"
echo "  - notifications_output.txt (plain text)"
echo "  - notifications_output.html (HTML email)"
echo "  - witness_slip_notifications.json (data)"
echo ""
echo "To customize, set environment variables before running:"
echo "  export USER_NAME='Your Name'"
echo "  export TOPICS_TRANSPORTATION='Transportation,Bicycle,Pedestrian'"
echo "  ./local_test.sh"
