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

# Check if data directory exists
if [ ! -d "data/il" ]; then
    echo "📥 Downloading sample IL data..."
    mkdir -p data/il
    
    # Try to download sample files from IL legislation repo
    echo "  Fetching bill data..."
    curl -s "https://api.github.com/repos/govbot-openstates-scrapers/il-legislation/contents/_data/il" | \
        grep -o '"download_url": "[^"]*\.json"' | \
        grep -o 'https://[^"]*' | \
        head -5 | \
        while read url; do
            filename=$(basename "$url")
            echo "    Downloading $filename..."
            curl -s -o "data/il/$filename" "$url"
        done
    
    if [ ! "$(ls -A data/il)" ]; then
        echo "  ⚠️  Could not download data. Create sample files or check network."
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
